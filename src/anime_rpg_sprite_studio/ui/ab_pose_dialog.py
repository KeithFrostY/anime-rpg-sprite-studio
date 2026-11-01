"""Per-frame, constrained A/B pose editing on an isolated candidate."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..animation.ab_walk import load_ab_renderer, correction_from_joint

JOINTS = ('hip', 'knee', 'ankle', 'toe')


class PoseCanvas(QWidget):
    moved = Signal(str, str, float, float)

    def __init__(self):
        super().__init__()
        self.image = QPixmap(); self.pose = None; self.ground = 0
        self.active_leg = 'A'; self.dragging = None
        self.setMinimumSize(360, 360)

    def image_rect(self):
        if self.image.isNull(): return QRectF()
        scale = min(self.width()/self.image.width(), self.height()/self.image.height())
        w, h = self.image.width()*scale, self.image.height()*scale
        return QRectF((self.width()-w)/2, (self.height()-h)/2, w, h)

    def paintEvent(self, event):
        painter = QPainter(self)
        for y in range(0, self.height(), 16):
            for x in range(0, self.width(), 16):
                painter.fillRect(x, y, 16, 16, QColor('#d0d0d0' if (x//16+y//16)%2 else '#eeeeee'))
        rect = self.image_rect()
        if rect.isEmpty() or self.pose is None: return
        painter.drawPixmap(rect, self.image, QRectF(self.image.rect()))
        sx, sy = rect.width()/self.image.width(), rect.height()/self.image.height()
        for name, color in (('A', '#00c6c6'), ('B', '#ff9d25')):
            painter.setPen(QPen(QColor(color), 2))
            points = [QPointF(rect.x()+self.pose['legs'][name][key][0]*sx,
                              rect.y()+self.pose['legs'][name][key][1]*sy) for key in JOINTS]
            for a, b in zip(points, points[1:]): painter.drawLine(a, b)
            for key, point in zip(JOINTS, points):
                painter.drawEllipse(point, 4, 4); painter.drawText(point + QPointF(5, -5), f'{name} {key}')
        painter.setPen(QPen(QColor('red'), 1, Qt.PenStyle.DashLine))
        y = rect.y() + self.ground*sy
        painter.drawLine(QPointF(rect.x(), y), QPointF(rect.right(), y))

    def mousePressEvent(self, event):
        if self.pose is None or self.image.isNull() or event.button() != Qt.MouseButton.LeftButton: return
        rect = self.image_rect(); sx, sy = rect.width()/self.image.width(), rect.height()/self.image.height()
        other = 'B' if self.active_leg == 'A' else 'A'
        candidates = []
        for leg in (self.active_leg, other):
            for joint in JOINTS:
                x, y = self.pose['legs'][leg][joint]
                candidates.append(((event.position().x()-rect.x()-x*sx)**2 + (event.position().y()-rect.y()-y*sy)**2, leg, joint))
        distance, leg, joint = min(candidates, key=lambda value: value[0])
        if distance <= 144: self.dragging = (leg, joint)

    def mouseReleaseEvent(self, event):
        if self.dragging is None or self.image.isNull(): return
        leg, joint = self.dragging; self.dragging = None; rect = self.image_rect()
        x = max(0., min(self.image.width()-1., (event.position().x()-rect.x())*self.image.width()/rect.width()))
        y = max(0., min(self.image.height()-1., (event.position().y()-rect.y())*self.image.height()/rect.height()))
        self.moved.emit(leg, joint, x, y)


class FrameSignals(QObject):
    finished = Signal(int, object, str)


class FrameWorker(QRunnable):
    def __init__(self, job, rig, assets, index, cancel):
        super().__init__()
        self.job, self.rig, self.assets = job, deepcopy(rig), dict(assets)
        self.index, self.cancel = index, cancel
        self.signals = FrameSignals()

    def run(self):
        try:
            self.rig.validate()
            with TemporaryDirectory(prefix='sprite-ab-pose-') as temporary:
                root = Path(temporary).resolve()
                for ref in (self.rig.source, *self.rig.layers):
                    if self.cancel.is_set(): raise InterruptedError('已取消')
                    path = (root / ref.asset_path).resolve()
                    if not path.is_relative_to(root): raise ValueError('素材路徑超出範圍')
                    data = self.assets.get(ref.asset_path)
                    if not isinstance(data, bytes) or len(data) > 32 * 1024 * 1024: raise ValueError('素材缺失或過大')
                    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
                renderer = load_ab_renderer(self.rig, root)
                if self.cancel.is_set(): raise InterruptedError('已取消')
                pose = renderer.pose(self.index / self.rig.settings['frames'])
                frame, bounds = renderer._compose(pose)
                clipped = bool(bounds and (bounds[0] < 0 or bounds[1] < 0 or bounds[2] > frame.width or bounds[3] > frame.height))
                stream = BytesIO(); frame.save(stream, format='PNG')
                if self.cancel.is_set(): raise InterruptedError('已取消')
            self.signals.finished.emit(self.job, (renderer, pose, stream.getvalue(), clipped), '')
        except Exception as exc:
            self.signals.finished.emit(self.job, None, str(exc))


class ABPoseDialog(QDialog):
    def __init__(self, rig, assets, initial_frame=0, parent=None):
        super().__init__(parent)
        self.rig, self.assets = deepcopy(rig), dict(assets)
        self.rig.validate()
        self.index = max(0, min(int(initial_frame), self.rig.settings['frames'] - 1))
        self.result_rig = None; self.pose = None; self.renderer = None
        self.busy = False; self.worker = None; self.cancel = Event(); self.job = 0
        self.dirty = False; self._syncing = False; self._pending_close = None
        self._displayed_leg, self._displayed_joint = 'A', 'hip'
        self._requested_frame = None
        self.setWindowTitle('A／B 逐幀姿勢修正'); self.resize(900, 700)
        layout = QVBoxLayout(self)
        info = QLabel('拖動髖、膝、踝或腳尖可設定關鍵幀。插值各腿獨立循環；單一關鍵幀的位移會套用整個循環。膝彎方向會在關鍵幀切換，且不保證接地；身體不會自動跟隨，請檢查接縫。')
        info.setWordWrap(True); layout.addWidget(info)
        self.canvas = PoseCanvas(); self.canvas.moved.connect(self.move_joint); layout.addWidget(self.canvas, 1)
        navigation = QHBoxLayout()
        previous = QPushButton('上一幀'); previous.clicked.connect(lambda: self.frame.setValue((self.index-1) % self.rig.settings['frames']))
        navigation.addWidget(previous)
        navigation.addWidget(QLabel('影格（從 0 開始）'))
        self.frame = QSpinBox(); self.frame.setRange(0, self.rig.settings['frames']-1); self.frame.setValue(self.index)
        self.frame.valueChanged.connect(self.change_frame); navigation.addWidget(self.frame)
        following = QPushButton('下一幀'); following.clicked.connect(lambda: self.frame.setValue((self.index+1) % self.rig.settings['frames']))
        navigation.addWidget(following); layout.addLayout(navigation)
        interpolation = QHBoxLayout()
        self.interpolate_check = QCheckBox('循環插值')
        self.interpolate_check.setChecked(self.rig.interpolate)
        self.interpolate_check.toggled.connect(self.set_interpolation)
        interpolation.addWidget(self.interpolate_check)
        self.key_status = QLabel(); interpolation.addWidget(self.key_status)
        interpolation.addStretch(); layout.addLayout(interpolation)
        coordinates = QHBoxLayout()
        self.leg = QComboBox(); self.leg.addItems(['A', 'B']); self.leg.currentIndexChanged.connect(self.selection_changed)
        self.joint = QComboBox(); self.joint.addItems(JOINTS); self.joint.currentIndexChanged.connect(self.selection_changed)
        self.x, self.y = QDoubleSpinBox(), QDoubleSpinBox()
        for spin in (self.x, self.y):
            spin.setRange(-100000, 100000); spin.setDecimals(2)
            spin.editingFinished.connect(self.commit_if_changed)
        for widget in (QLabel('腿'), self.leg, QLabel('關節'), self.joint, QLabel('X'), self.x, QLabel('Y'), self.y): coordinates.addWidget(widget)
        apply_point = QPushButton('套用座標'); apply_point.clicked.connect(self.apply_coordinates); coordinates.addWidget(apply_point)
        layout.addLayout(coordinates)
        actions = QHBoxLayout()
        add_key = QPushButton('固定目前姿勢為關鍵幀'); add_key.clicked.connect(self.add_key); actions.addWidget(add_key)
        reset_leg = QPushButton('移除本幀選取腿關鍵幀'); reset_leg.clicked.connect(self.reset_leg); actions.addWidget(reset_leg)
        reset_frame = QPushButton('移除本幀全部關鍵幀'); reset_frame.clicked.connect(self.reset_frame); actions.addWidget(reset_frame)
        accept = QPushButton('套用姿勢到候選'); accept.clicked.connect(self.accept); actions.addWidget(accept)
        cancel = QPushButton('取消'); cancel.clicked.connect(self.reject); actions.addWidget(cancel)
        layout.addLayout(actions)
        self.status = QLabel('正在生成姿勢…'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.edit_controls = [self.canvas, self.frame, previous, following, self.leg, self.joint, self.x, self.y, apply_point, self.interpolate_check, add_key, reset_leg, reset_frame, accept]
        self.start_render()

    def set_busy(self, busy):
        self.busy = busy
        for widget in self.edit_controls: widget.setEnabled(not busy)

    def start_render(self):
        if self.busy: return
        self.job += 1; self.cancel = Event(); self.set_busy(True)
        self.status.setText('正在以 CPU 計算此幀…')
        self.worker = FrameWorker(self.job, self.rig, self.assets, self.index, self.cancel)
        self.worker.signals.finished.connect(self.render_finished)
        QThreadPool.globalInstance().start(self.worker)

    def render_finished(self, job, result, error):
        if job != self.job: return
        self.worker = None; self.set_busy(False)
        if self._pending_close is not None:
            result_code = self._pending_close; self._pending_close = None
            super().done(result_code); return
        if error:
            self.renderer = None; self.pose = None; self.canvas.pose = None; self.canvas.update()
            self.status.setText(f'計算失敗：{error}'); return
        self.renderer, self.pose, pixels, clipped = result
        self.canvas.image.loadFromData(pixels); self.canvas.pose = self.pose
        self.canvas.ground = self.rig.settings['ground_y']; self.canvas.update()
        warnings = [f'{leg} 腿目標不可達，接地可能失敗' for leg in ('A', 'B') if self.pose['legs'][leg]['limited']]
        if clipped: warnings.append('圖像超出畫布')
        self.status.setText('；'.join(warnings) if warnings else f'第 {self.index} 幀；拖動關節或修改座標。')
        self.show_coordinates()
        if self._requested_frame is not None:
            requested = self._requested_frame; self._requested_frame = None
            if requested != self.index:
                self.index = requested; self.frame.setValue(requested); self.start_render()

    def show_coordinates(self, *args):
        if self.pose is None: return
        self.canvas.active_leg = self.leg.currentText()
        self._displayed_leg, self._displayed_joint = self.leg.currentText(), self.joint.currentText()
        position = self.pose['legs'][self.leg.currentText()][self.joint.currentText()]
        self._syncing = True
        try: self.x.setValue(position[0]); self.y.setValue(position[1])
        finally: self._syncing = False
        self.update_key_status()

    def selection_changed(self, *args):
        if self.pose is not None and self.coordinates_pending():
            for control, value in ((self.leg, self._displayed_leg), (self.joint, self._displayed_joint)):
                control.blockSignals(True); control.setCurrentText(value); control.blockSignals(False)
            self.status.setText('請先套用或修正目前輸入的座標，再切換關節。')
            return
        self.show_coordinates()

    def update_key_status(self):
        leg = self.leg.currentText()
        if leg in self.rig.frame_overrides.get(str(self.index), {}):
            status = '關鍵幀'
        elif self.rig.interpolate and any(leg in entry for entry in self.rig.frame_overrides.values()):
            status = '插值'
        else:
            status = '原步態'
        self.key_status.setText(f'第 {self.index} 幀 · {leg} 腿：{status}')

    def coordinates_pending(self):
        if self.pose is None: return False
        position = self.pose['legs'][self._displayed_leg][self._displayed_joint]
        return abs(self.x.value() - position[0]) > .0051 or abs(self.y.value() - position[1]) > .0051

    def set_interpolation(self, enabled):
        if self.busy or self.coordinates_pending():
            self.interpolate_check.blockSignals(True)
            self.interpolate_check.setChecked(self.rig.interpolate)
            self.interpolate_check.blockSignals(False)
            self.status.setText('請先套用座標，再更改插值設定。')
            return
        if enabled == self.rig.interpolate: return
        self.rig.interpolate = enabled
        self.dirty = True
        self.update_key_status()
        self.start_render()

    def add_key(self):
        if self.busy or self.renderer is None or self.pose is None: return
        leg = self.leg.currentText()
        if leg in self.rig.frame_overrides.get(str(self.index), {}):
            self.status.setText('此腿在本幀已有關鍵幀。'); return
        if self.coordinates_pending():
            self.status.setText('請先套用座標，再固定目前姿勢。'); return
        self.move_joint(leg, 'hip', *self.pose['legs'][leg]['hip'])

    def commit_if_changed(self):
        if self._syncing or self.busy or self.pose is None: return False
        position = self.pose['legs'][self.leg.currentText()][self.joint.currentText()]
        if abs(self.x.value() - position[0]) > .0051 or abs(self.y.value() - position[1]) > .0051:
            return self.apply_coordinates()
        return True

    def change_frame(self, index):
        if self.busy:
            self._requested_frame = index; return
        if index == self.index: return
        if self.coordinates_pending():
            self.frame.blockSignals(True); self.frame.setValue(self.index); self.frame.blockSignals(False)
            self.status.setText('請先套用或修正目前輸入的座標，再切換影格。')
            return
        self.index = index; self.start_render()

    def apply_coordinates(self):
        return self.move_joint(self.leg.currentText(), self.joint.currentText(), self.x.value(), self.y.value())

    def move_joint(self, leg, joint, x, y):
        if self.busy or self.renderer is None: return False
        if self.coordinates_pending() and ((leg, joint) != (self._displayed_leg, self._displayed_joint)
                or abs(x - self.x.value()) > .0051 or abs(y - self.y.value()) > .0051):
            self.status.setText('請先套用或修正目前輸入的座標。'); return False
        try:
            correction = correction_from_joint(self.renderer, self.index, leg, joint, [x, y])
            candidate = deepcopy(self.rig)
            candidate.frame_overrides.setdefault(str(self.index), {})[leg] = correction
            candidate.validate()
        except (ValueError, KeyError, TypeError) as exc:
            self.status.setText(f'無法修改姿勢：{exc}'); return False
        self.rig = candidate; self.dirty = True
        self.leg.setCurrentText(leg); self.joint.setCurrentText(joint)
        self.start_render()
        return True

    def reset_leg(self):
        if self.busy: return
        if self.coordinates_pending():
            self.status.setText('請先套用或修正目前輸入的座標。'); return
        key = str(self.index); legs = self.rig.frame_overrides.get(key, {})
        if self.leg.currentText() not in legs: return
        del legs[self.leg.currentText()]
        if not legs: self.rig.frame_overrides.pop(key)
        self.dirty = True; self.start_render()

    def reset_frame(self):
        if self.busy or str(self.index) not in self.rig.frame_overrides: return
        if self.coordinates_pending():
            self.status.setText('請先套用或修正目前輸入的座標。'); return
        self.rig.frame_overrides.pop(str(self.index)); self.dirty = True; self.start_render()

    def accept(self):
        if self.busy or self.renderer is None: return
        if not self.commit_if_changed(): return
        if self.busy:
            self.status.setText('座標已更新，請檢查完成後再次按套用。'); return
        self.result_rig = deepcopy(self.rig)
        super().accept()

    def done(self, result):
        if result != QDialog.DialogCode.Accepted and (self.dirty or self.coordinates_pending()):
            if QMessageBox.question(self, '尚未套用', '放棄本次逐幀姿勢修改嗎？') != QMessageBox.StandardButton.Yes: return
        if self.busy:
            self._pending_close = result; self.cancel.set(); self.status.setText('正在取消計算…'); return
        super().done(result)
