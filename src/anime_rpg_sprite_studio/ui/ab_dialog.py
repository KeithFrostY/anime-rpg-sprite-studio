"""Offline candidate editor for a single right-facing A/B walk."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from uuid import uuid4

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Qt, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QComboBox, QDoubleSpinBox, QSpinBox, QFileDialog,
    QMessageBox, QListWidget, QWidget, QStackedWidget)

from ..core.ab_rig import ABAsset, ABLayer, ABWalk
from ..animation.ab_walk import load_ab_renderer
from ..export.ab_export import export_ab, ABExportCancelled

SEGMENTS = ('B.upper', 'B.lower', 'B.foot', 'A.upper', 'A.lower', 'A.foot', 'body')
JOINTS = ('hip', 'knee', 'ankle', 'toe')


class SkeletonEditor(QWidget):
    joint_moved = Signal(str, str, float, float)

    def __init__(self):
        super().__init__(); self.rig = None; self.image = QPixmap(); self.dragging = None; self.active_leg = 'A'
        self.setMinimumSize(320, 280)

    def image_rect(self):
        if self.image.isNull(): return QRectF()
        scale = min(self.width() / self.image.width(), self.height() / self.image.height())
        w, h = self.image.width() * scale, self.image.height() * scale
        return QRectF((self.width()-w)/2, (self.height()-h)/2, w, h)

    def paintEvent(self, event):
        painter = QPainter(self); rect = self.image_rect()
        if rect.isEmpty() or self.rig is None: return
        painter.drawPixmap(rect, self.image, QRectF(self.image.rect()))
        sx, sy = rect.width()/self.rig.canvas[0], rect.height()/self.rig.canvas[1]
        for leg, color in (('A', '#00c6c6'), ('B', '#ff9d25')):
            painter.setPen(QPen(QColor(color), 2))
            pts = [QPointF(rect.x()+self.rig.legs[leg][joint][0]*sx, rect.y()+self.rig.legs[leg][joint][1]*sy) for joint in JOINTS]
            for a, b in zip(pts, pts[1:]): painter.drawLine(a, b)
            for joint, p in zip(JOINTS, pts):
                painter.drawEllipse(p, 4, 4); painter.drawText(p + QPointF(5, -5), f'{leg} {joint}')
        painter.setPen(QPen(QColor('red'), 1, Qt.PenStyle.DashLine))
        y = rect.y() + self.rig.settings['ground_y'] * sy
        painter.drawLine(QPointF(rect.x(), y), QPointF(rect.right(), y))

    def mousePressEvent(self, event):
        if self.rig is None or self.image.isNull() or event.button() != Qt.MouseButton.LeftButton: return
        rect = self.image_rect()
        sx, sy = rect.width()/self.rig.canvas[0], rect.height()/self.rig.canvas[1]
        candidates = []
        for leg in (self.active_leg, 'B' if self.active_leg == 'A' else 'A'):
            for joint in JOINTS:
                x, y = self.rig.legs[leg][joint]
                candidates.append(((event.position().x()-rect.x()-x*sx)**2 + (event.position().y()-rect.y()-y*sy)**2, leg, joint))
        distance, leg, joint = min(candidates, key=lambda item: item[0])
        if distance <= 144: self.dragging = (leg, joint)

    def mouseReleaseEvent(self, event):
        if self.dragging is None: return
        rect = self.image_rect(); leg, joint = self.dragging; self.dragging = None
        x = max(0., min(self.rig.canvas[0]-1., (event.position().x()-rect.x()) * self.rig.canvas[0]/rect.width()))
        y = max(0., min(self.rig.canvas[1]-1., (event.position().y()-rect.y()) * self.rig.canvas[1]/rect.height()))
        self.joint_moved.emit(leg, joint, x, y)


class PreviewSignals(QObject):
    finished = Signal(int, object, str)


class PreviewWorker(QRunnable):
    def __init__(self, job, rig, assets, cancel):
        super().__init__()
        self.job, self.rig, self.assets, self.cancel = job, deepcopy(rig), dict(assets), cancel
        self.signals = PreviewSignals()

    def run(self):
        try:
            with TemporaryDirectory(prefix='sprite-ab-') as folder:
                root = Path(folder)
                for ref in (self.rig.source, *self.rig.layers):
                    if self.cancel.is_set(): raise InterruptedError('已取消')
                    path = root / ref.asset_path
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(self.assets[ref.asset_path])
                renderer = load_ab_renderer(self.rig, root)
                frames, warnings = [], []
                for i in range(self.rig.settings['frames']):
                    if self.cancel.is_set(): raise InterruptedError('已取消')
                    pose = renderer.pose(i / self.rig.settings['frames'])
                    frame, bounds = renderer._compose(pose)
                    for leg in ('A', 'B'):
                        if pose['legs'][leg]['limited']: warnings.append(f'幀 {i + 1}：{leg} 腿目標不可達，接地可能失敗')
                    if bounds and (bounds[0] < 0 or bounds[1] < 0 or bounds[2] > frame.width or bounds[3] > frame.height):
                        warnings.append(f'幀 {i + 1}：素材超出畫布')
                    stream = BytesIO(); frame.save(stream, format='PNG'); frames.append(stream.getvalue())
            self.signals.finished.emit(self.job, (frames, warnings), '')
        except Exception as exc:
            self.signals.finished.emit(self.job, None, str(exc))


class ABExportWorker(QRunnable):
    def __init__(self, job, rig, assets, destination, cancel):
        super().__init__()
        self.job, self.rig, self.assets = job, deepcopy(rig), dict(assets)
        self.destination, self.cancel = destination, cancel
        self.signals = PreviewSignals()

    def run(self):
        try:
            result = export_ab(self.rig, self.assets, self.destination, self.cancel)
            self.signals.finished.emit(self.job, result, '')
        except ABExportCancelled:
            self.signals.finished.emit(self.job, None, '已取消；未產生輸出')
        except Exception as exc:
            self.signals.finished.emit(self.job, None, str(exc))


class ABDialog(QDialog):
    def __init__(self, service, character_id, parent=None):
        super().__init__(parent)
        self.service, self.character_id = service, character_id
        self.project_identity, self.project_path = service.project, service.path
        self.rig, self.assets, self.frames = None, {}, []
        self.busy, self.job, self.worker, self.cancel = False, 0, None, Event()
        self.candidate_dirty = False
        self.result_path = None
        self._syncing_joint = False
        self.index = 0
        self.timer = QTimer(self); self.timer.timeout.connect(self.advance)
        self.setWindowTitle('A／B 單角色行走'); self.resize(1000, 750)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('右向 · A/B 身份固定 · 全畫布透明 PNG 分件 · 隱藏部位須先補畫'))
        buttons = QHBoxLayout()
        source_button = QPushButton('匯入原圖 PNG'); source_button.clicked.connect(self.choose_source); buttons.addWidget(source_button)
        part_button = QPushButton('匯入／更換選取分件'); part_button.clicked.connect(self.choose_layer); buttons.addWidget(part_button)
        edit_button = QPushButton('編輯選取分件'); edit_button.clicked.connect(lambda: self.open_mask_editor(False)); buttons.addWidget(edit_button)
        cut_button = QPushButton('從原圖建立分件'); cut_button.clicked.connect(lambda: self.open_mask_editor(True)); buttons.addWidget(cut_button)
        repair_button = QPushButton('切換選取分件待補畫狀態'); repair_button.clicked.connect(self.toggle_repair); buttons.addWidget(repair_button)
        layout.addLayout(buttons)
        middle = QHBoxLayout()
        self.parts = QListWidget(); self.parts.addItems(SEGMENTS); self.parts.setCurrentRow(0)
        part_controls = QVBoxLayout(); part_controls.addWidget(self.parts)
        back = QPushButton('圖層往後'); back.clicked.connect(lambda: self.move_layer(-1)); part_controls.addWidget(back)
        front = QPushButton('圖層往前'); front.clicked.connect(lambda: self.move_layer(1)); part_controls.addWidget(front)
        middle.addLayout(part_controls)
        self.preview = QLabel('請先匯入原圖及七個分件'); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(320, 280)
        self.skeleton = SkeletonEditor(); self.skeleton.joint_moved.connect(self.move_joint)
        self.views = QStackedWidget(); self.views.addWidget(self.preview); self.views.addWidget(self.skeleton)
        middle.addWidget(self.views, 1)
        form = QFormLayout()
        self.leg = QComboBox(); self.leg.addItems(['A', 'B'])
        self.joint = QComboBox(); self.joint.addItems(JOINTS)
        self.joint_x = QDoubleSpinBox(); self.joint_y = QDoubleSpinBox()
        for spin in (self.joint_x, self.joint_y): spin.setRange(-100000, 100000); spin.setDecimals(1)
        self.joint_x.valueChanged.connect(self.update_joint); self.joint_y.valueChanged.connect(self.update_joint)
        self.leg.currentIndexChanged.connect(self.show_joint); self.joint.currentIndexChanged.connect(self.show_joint)
        form.addRow('腿身份', self.leg); form.addRow('關節', self.joint)
        form.addRow('關節 X', self.joint_x); form.addRow('關節 Y', self.joint_y)
        joint_button = QPushButton('更新關節'); joint_button.clicked.connect(self.update_joint); form.addRow(joint_button)
        self.sole = QDoubleSpinBox(); self.sole.setRange(-100000, 100000)
        self.bend = QComboBox(); self.bend.addItems(['1', '-1'])
        self.sole.valueChanged.connect(self.update_sole); self.bend.currentIndexChanged.connect(self.update_sole)
        form.addRow('腳底 Y', self.sole); form.addRow('膝彎方向', self.bend)
        sole_button = QPushButton('更新腳底／膝彎'); sole_button.clicked.connect(self.update_sole); form.addRow(sole_button)
        self.parameters = {}
        for key, label in [('stride','步幅'), ('lift','抬腳'), ('bob','起伏'), ('hip_drop','身體下移'), ('ground_y','地面 Y'), ('stance_fraction','支撐比例'), ('fps','FPS')]:
            spin = QDoubleSpinBox(); spin.setRange(-100000, 100000); spin.setDecimals(3)
            spin.valueChanged.connect(self.settings_changed); self.parameters[key] = spin; form.addRow(label, spin)
        self.frame_count = QSpinBox(); self.frame_count.setRange(2, 240); self.frame_count.valueChanged.connect(self.frame_count_changed)
        form.addRow('影格數', self.frame_count)
        middle.addLayout(form); layout.addLayout(middle)
        actions = QHBoxLayout()
        source_view = QPushButton('查看／拖動來源骨架'); source_view.clicked.connect(self.show_source); actions.addWidget(source_view)
        generate = QPushButton('生成預覽'); generate.clicked.connect(self.generate_preview); actions.addWidget(generate)
        cancel = QPushButton('取消生成'); cancel.clicked.connect(lambda: self.cancel.set()); actions.addWidget(cancel)
        play = QPushButton('播放／暫停'); play.clicked.connect(self.toggle_play); actions.addWidget(play)
        previous = QPushButton('上一幀'); previous.clicked.connect(lambda: self.select_frame(self.index - 1)); actions.addWidget(previous)
        following = QPushButton('下一幀'); following.clicked.connect(lambda: self.select_frame(self.index + 1)); actions.addWidget(following)
        self.apply_button = QPushButton('套用 A／B 候選'); self.apply_button.clicked.connect(self.apply_candidate); actions.addWidget(self.apply_button)
        export_button = QPushButton('匯出 A／B…'); export_button.clicked.connect(self.export_candidate); actions.addWidget(export_button)
        layout.addLayout(actions)
        self.pose_button = QPushButton('逐幀姿勢修正…')
        self.pose_button.clicked.connect(self.open_pose_editor)
        layout.addWidget(self.pose_button)
        self.status = QLabel('候選未套用；需要逐件準備並檢查接縫、遮擋和缺失像素。'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.refresh_parts()
        character = next(c for c in service.project.characters if c.id == character_id)
        if character.ab_walk is not None and service.path:
            self.rig = deepcopy(character.ab_walk)
            missing = False
            refs = [self.rig.source, *self.rig.layers]
            for layer in self.rig.layers:
                if layer.edit is not None: refs.extend((layer.edit.source, layer.edit.mask, layer.edit.paint))
            for ref in refs:
                try: self.assets[ref.asset_path] = self.read_png(service.repository._asset(service.path.parent, ref.asset_path))
                except (OSError, ValueError): missing = True
            self.load_controls(); self.refresh_parts()
            if missing:
                self.status.setText('已存的 A/B 素材缺失，請重新匯入。')

    def invalidate(self):
        self.timer.stop(); self.frames = []; self.index = 0
        if self.busy: self.cancel.set()

    def refresh_parts(self):
        for i, segment in enumerate(SEGMENTS):
            matches = [n for n, layer in enumerate(self.rig.layers) if layer.segment == segment and layer.asset_path in self.assets] if self.rig else []
            if matches:
                layer = self.rig.layers[matches[0]]
                self.parts.item(i).setText(f'{segment}：順序 {matches[0]+1} · {"待補畫" if layer.needs_repair else "已檢查"}')
            else: self.parts.item(i).setText(f'{segment}：未匯入')

    def toggle_repair(self):
        if self.rig is None or self.parts.currentRow() < 0: return
        segment = SEGMENTS[self.parts.currentRow()]
        matches = [layer for layer in self.rig.layers if layer.segment == segment]
        if len(matches) != 1:
            self.status.setText('此部件不存在或有多個圖層，無法切換狀態。'); return
        self.invalidate(); self.candidate_dirty = True
        matches[0].needs_repair = not matches[0].needs_repair; self.refresh_parts()

    def move_layer(self, delta):
        if self.rig is None or self.parts.currentRow() < 0: return
        segment = SEGMENTS[self.parts.currentRow()]
        positions = [i for i, layer in enumerate(self.rig.layers) if layer.segment == segment]
        if len(positions) != 1: return
        index = positions[0]; other = index + delta
        if 0 <= other < len(self.rig.layers):
            self.invalidate(); self.candidate_dirty = True
            self.rig.layers[index], self.rig.layers[other] = self.rig.layers[other], self.rig.layers[index]
            self.refresh_parts()

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, '選擇原圖', '', 'PNG (*.png)')
        if path:
            if self.rig is not None and self.rig.source.asset_path not in self.assets:
                try: self.restore_source(path)
                except (OSError, ValueError) as exc: QMessageBox.warning(self, '匯入失敗', str(exc))
                return
            if self.rig is not None and QMessageBox.question(self, '更換原圖', '更換原圖會清除目前候選的分件和骨架設定，繼續嗎？') != QMessageBox.StandardButton.Yes:
                return
            try: self.set_source(path)
            except (OSError, ValueError) as exc: QMessageBox.warning(self, '匯入失敗', str(exc))

    def choose_layer(self):
        path, _ = QFileDialog.getOpenFileName(self, '選擇全畫布分件', '', 'PNG (*.png)')
        if path:
            if self.rig is not None and self.parts.currentRow() >= 0:
                selected = [layer for layer in self.rig.layers if layer.segment == SEGMENTS[self.parts.currentRow()]]
                if len(selected) == 1 and selected[0].edit is not None and QMessageBox.question(self, '更換分件', '更換此分件會移除候選中的遮罩和補畫設定，繼續嗎？') != QMessageBox.StandardButton.Yes:
                    return
            try: self.set_layer(SEGMENTS[self.parts.currentRow()], path)
            except (OSError, ValueError) as exc: QMessageBox.warning(self, '匯入失敗', str(exc))

    def open_mask_editor(self, start_from_source=False):
        from ..core.ab_rig import ABEdit
        from .mask_paint_dialog import MaskPaintDialog
        if self.busy or self.rig is None or self.parts.currentRow() < 0:
            self.status.setText('請先匯入原圖並選擇分件。'); return
        segment = SEGMENTS[self.parts.currentRow()]
        matches = [i for i, layer in enumerate(self.rig.layers) if layer.segment == segment]
        if len(matches) > 1:
            self.status.setText('同一部件有多個圖層，請先於原始專案處理。'); return
        layer = self.rig.layers[matches[0]] if matches else None
        if start_from_source and layer is not None and QMessageBox.question(
                self, '重新建立分件', '這會取代目前候選的分件及其遮罩／補畫設定，繼續嗎？') != QMessageBox.StandardButton.Yes:
            return
        if not start_from_source and layer is None:
            self.status.setText('此部件尚未匯入；可選擇從原圖建立分件。'); return
        try:
            edit = layer.edit if layer is not None and not start_from_source else None
            source_key = self.rig.source.asset_path if start_from_source else (edit.source.asset_path if edit else layer.asset_path)
            source = self.assets[source_key]
            with Image.open(BytesIO(source)) as image:
                mismatch = image.size != tuple(self.rig.canvas)
            if mismatch:
                path, _ = QFileDialog.getOpenFileName(self, '來源尺寸不同：選擇與骨架同尺寸的參考圖', '', 'PNG (*.png)')
                if not path: return
                source = self.read_png(path)
                with Image.open(BytesIO(source)) as image:
                    if image.size != tuple(self.rig.canvas):
                        raise ValueError('參考圖必須與骨架畫布尺寸相同。')
            if self.rig.canvas[0] * self.rig.canvas[1] > 4_000_000:
                raise ValueError('遮罩編輯器最多支援 400 萬像素。')
            if start_from_source:
                stream = BytesIO(); Image.new('L', self.rig.canvas, 0).save(stream, format='PNG'); mask = stream.getvalue()
            else: mask = self.assets[edit.mask.asset_path] if edit else None
            paint = self.assets[edit.paint.asset_path] if edit else None
            other_layers = [other for other in self.rig.layers if other is not layer and other.asset_path in self.assets]
            references = []
            if other_layers:
                merged = Image.new('RGBA', self.rig.canvas)
                for other in other_layers:
                    with Image.open(BytesIO(self.assets[other.asset_path])) as image:
                        if image.size != tuple(self.rig.canvas): raise ValueError('參考分件尺寸不正確')
                        merged.alpha_composite(image.convert('RGBA'))
                stream = BytesIO(); merged.save(stream, format='PNG'); references = [stream.getvalue()]
            dialog = MaskPaintDialog(source, mask, paint, references=references, parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted: return
            result = dialog.result_bytes
            if not isinstance(result, tuple) or len(result) != 4: raise ValueError('編輯結果無效')
            for data, mode in zip(result, (None, 'L', 'RGBA', 'RGBA')):
                if not isinstance(data, bytes) or len(data) > 32 * 1024 * 1024: raise ValueError('編輯結果過大')
                with Image.open(BytesIO(data)) as image:
                    if image.format != 'PNG' or image.size != tuple(self.rig.canvas) or (mode is not None and image.mode != mode):
                        raise ValueError('編輯圖層尺寸或格式無效')
                    image.load()
            keys = [f'mask-edit-{uuid4().hex}.png' for _ in range(4)]
            new_layer = ABLayer(asset_path=keys[3], segment=segment, needs_repair=True,
                                edit=ABEdit(source=ABAsset(keys[0]), mask=ABAsset(keys[1]), paint=ABAsset(keys[2])))
            self.invalidate(); self.candidate_dirty = True
            self.assets.update(dict(zip(keys, result)))
            if matches: self.rig.layers[matches[0]] = new_layer
            else: self.rig.layers.append(new_layer)
            self.refresh_parts()
            self.status.setText('分件已更新至候選；請預覽、確認補畫狀態，再套用及儲存。')
        except (OSError, ValueError, KeyError) as exc:
            self.status.setText(f'無法編輯分件：{exc}')

    def set_source(self, path):
        data = self.read_png(path)
        with Image.open(BytesIO(data)) as image:
            if image.format != 'PNG' or image.width * image.height > 8_000_000 or getattr(image, 'n_frames', 1) != 1: raise ValueError('請選擇單張 PNG')
            w, h = image.size; image.load()
        self.invalidate(); self.candidate_dirty = True
        points = {'hip':[w*.5,h*.45], 'knee':[w*.5,h*.65], 'ankle':[w*.5,h*.85], 'toe':[w*.6,h*.85], 'sole_y':h*.9, 'bend':1}
        self.rig = ABWalk(canvas=(w,h), source=ABAsset('source.png'), layers=[],
            legs={'A':deepcopy(points), 'B':deepcopy(points)},
            settings={'frames':8, 'fps':10, 'stride':w*.1, 'lift':h*.03, 'bob':2, 'hip_drop':0, 'ground_y':h*.9, 'stance_fraction':.6})
        self.assets = {'source.png':data}; self.load_controls(); self.refresh_parts()
        self.show_source()
        self.status.setText('新原圖已載入；請逐一匯入七個分件，再調整 A/B 關節。')

    def restore_source(self, path):
        data = self.read_png(path)
        self.invalidate(); self.candidate_dirty = True
        key = f'source-{uuid4().hex}.png'
        self.assets[key] = data; self.rig.source.asset_path = key
        self.show_source(); self.status.setText('原圖已重新匯入，原有骨架與分件設定已保留。')

    def set_layer(self, segment, path):
        if self.rig is None: raise ValueError('請先匯入原圖')
        matching = [i for i, layer in enumerate(self.rig.layers) if layer.segment == segment]
        if len(matching) > 1: raise ValueError('此部件有多個圖層，請先於原始專案處理')
        data = self.read_png(path)
        with Image.open(BytesIO(data)) as image:
            if image.format != 'PNG' or image.size != tuple(self.rig.canvas) or ('A' not in image.getbands() and 'transparency' not in image.info) or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('分件必須是與原圖同尺寸的單張透明 PNG')
            image.load()
        self.invalidate(); self.candidate_dirty = True
        key = f'layer-{uuid4().hex}.png'; self.assets[key] = data
        if matching:
            self.rig.layers[matching[0]] = ABLayer(asset_path=key, segment=segment, needs_repair=True)
        else:
            self.rig.layers.append(ABLayer(asset_path=key, segment=segment, needs_repair=True))
        self.refresh_parts()

    def load_controls(self):
        for key, spin in self.parameters.items(): spin.blockSignals(True); spin.setValue(self.rig.settings[key]); spin.blockSignals(False)
        self.frame_count.blockSignals(True); self.frame_count.setValue(self.rig.settings['frames']); self.frame_count.blockSignals(False)
        self.show_joint()

    def show_joint(self, *args):
        if self.rig is None: return
        self.skeleton.active_leg = self.leg.currentText()
        leg = self.rig.legs[self.leg.currentText()]
        self._syncing_joint = True
        try:
            x, y = leg[self.joint.currentText()]; self.joint_x.setValue(x); self.joint_y.setValue(y)
            self.sole.setValue(leg['sole_y']); self.bend.setCurrentText(str(leg['bend']))
        finally: self._syncing_joint = False

    def update_joint(self, *args):
        if self.rig is None or self._syncing_joint: return
        self.invalidate(); self.candidate_dirty = True; self.rig.legs[self.leg.currentText()][self.joint.currentText()] = [self.joint_x.value(), self.joint_y.value()]
        self.skeleton.update()

    def show_source(self):
        if self.rig is None: return
        self.skeleton.rig = self.rig
        self.skeleton.image.loadFromData(self.assets.get(self.rig.source.asset_path, b''))
        self.views.setCurrentWidget(self.skeleton); self.skeleton.update()

    def move_joint(self, leg, joint, x, y):
        self.invalidate(); self.candidate_dirty = True; self.rig.legs[leg][joint] = [x, y]
        self.leg.setCurrentText(leg); self.joint.setCurrentText(joint)
        self.show_joint(); self.skeleton.update()

    def update_sole(self, *args):
        if self.rig is None or self._syncing_joint: return
        self.invalidate(); self.candidate_dirty = True; leg = self.rig.legs[self.leg.currentText()]; leg['sole_y'] = self.sole.value(); leg['bend'] = int(self.bend.currentText())

    def settings_changed(self, *args):
        if self.rig is None: return
        self.invalidate(); self.candidate_dirty = True
        for key, spin in self.parameters.items(): self.rig.settings[key] = spin.value()
        self.rig.settings['frames'] = self.frame_count.value()
        self.skeleton.update()

    def frame_count_changed(self, value):
        if self.rig is None: return
        old = self.rig.settings['frames']
        if value != old and self.rig.frame_overrides:
            answer = QMessageBox.question(self, '更改影格數', '更改影格數會改變每幀相位。是否清除所有逐幀修正並繼續？')
            if answer != QMessageBox.StandardButton.Yes:
                self.frame_count.blockSignals(True); self.frame_count.setValue(old); self.frame_count.blockSignals(False)
                return
            self.rig.frame_overrides.clear()
        self.settings_changed()

    def generate_preview(self):
        if self.busy or self.rig is None: return
        try:
            self.rig.validate()
            for ref in (self.rig.source, *self.rig.layers):
                if ref.asset_path not in self.assets: raise ValueError('請先匯入全部分件')
        except ValueError as exc:
            self.status.setText(str(exc)); return
        self.invalidate(); self.cancel = Event(); self.job += 1; self.busy = True
        self.worker = PreviewWorker(self.job, self.rig, self.assets, self.cancel)
        self.worker.signals.finished.connect(self.preview_finished)
        self.status.setText('正在以 CPU 生成預覽…')
        QThreadPool.globalInstance().start(self.worker)

    def open_pose_editor(self):
        from .ab_pose_dialog import ABPoseDialog
        if self.busy or self.rig is None: return
        try:
            self.rig.validate()
            if any(ref.asset_path not in self.assets for ref in (self.rig.source, *self.rig.layers)):
                raise ValueError('請先匯入全部素材')
        except ValueError as exc:
            self.status.setText(str(exc)); return
        self.timer.stop()
        editor = ABPoseDialog(self.rig, self.assets, self.index, self)
        result = editor.exec()
        candidate = editor.result_rig
        editor.deleteLater()
        if result != QDialog.DialogCode.Accepted or candidate is None: return
        try: candidate.validate()
        except ValueError as exc:
            self.status.setText(f'姿勢未套用：{exc}'); return
        self.invalidate(); self.rig = deepcopy(candidate); self.candidate_dirty = True
        self.status.setText('逐幀姿勢已套用至候選；請重新生成預覽，並套用及儲存專案。')

    def preview_finished(self, job, result, error):
        if job != self.job: return
        self.busy = False; self.worker = None
        if self.cancel.is_set(): self.status.setText('生成已取消；候選未套用'); return
        if error: self.status.setText(f'生成失敗：{error}'); return
        self.frames, warnings = result
        self.status.setText('；'.join(warnings[:8]) if warnings else '預覽已生成；請人工檢查接地、接縫與遮擋。')
        self.select_frame(0)

    def select_frame(self, index):
        if not self.frames: return
        self.index = index % len(self.frames)
        pm = QPixmap(); pm.loadFromData(self.frames[self.index])
        self.preview.setPixmap(pm.scaled(420, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.views.setCurrentWidget(self.preview)

    def advance(self): self.select_frame(self.index + 1)

    def toggle_play(self):
        if self.timer.isActive(): self.timer.stop()
        elif self.frames: self.timer.start(max(1, round(1000 / self.rig.settings['fps'])))

    def apply_candidate(self):
        if self.busy or self.rig is None: return
        if self.service.project is not self.project_identity or self.service.path != self.project_path:
            self.status.setText('專案已變更，候選未套用。'); return
        try:
            self.service.apply_ab_walk(self.character_id, self.rig, self.assets)
            self.candidate_dirty = False
            self.status.setText('A/B 候選已套用；請儲存專案。')
        except (ValueError, OSError, StopIteration) as exc: self.status.setText(f'套用失敗：{exc}')

    def export_candidate(self):
        if self.busy or self.rig is None: return
        try:
            self.rig.validate()
            if any(ref.asset_path not in self.assets for ref in (self.rig.source, *self.rig.layers)):
                raise ValueError('請先匯入全部素材')
        except ValueError as exc:
            self.status.setText(str(exc)); return
        destination = QFileDialog.getExistingDirectory(self, '選擇 A／B 匯出位置')
        if not destination: return
        self.timer.stop(); self.cancel = Event(); self.job += 1; self.busy = True; self.result_path = None
        self.worker = ABExportWorker(self.job, self.rig, self.assets, Path(destination), self.cancel)
        self.worker.signals.finished.connect(self.export_finished)
        self.status.setText('正在背景匯出目前候選快照；不會自動套用或儲存專案。')
        QThreadPool.globalInstance().start(self.worker)

    def export_finished(self, job, result, error):
        if job != self.job: return
        self.busy = False; self.worker = None
        if error:
            self.status.setText(f'匯出未完成：{error}'); return
        self.result_path = result
        self.status.setText(f'匯出完成：{result}')

    def closeEvent(self, event):
        self.timer.stop()
        if self.busy:
            self.cancel.set(); self.status.setText('正在取消，完成後可關閉。'); event.ignore(); return
        if not self.confirm_discard(): event.ignore(); return
        self.candidate_dirty = False
        super().closeEvent(event)

    def reject(self):
        if self.busy:
            self.cancel.set(); self.status.setText('正在取消，完成後可關閉。'); return
        if not self.confirm_discard(): return
        super().reject()

    def confirm_discard(self):
        return not self.candidate_dirty or QMessageBox.question(self, '尚未套用', '目前 A/B 候選有未套用的修改，確定放棄嗎？') == QMessageBox.StandardButton.Yes

    @staticmethod
    def read_png(path):
        with Path(path).open('rb') as stream:
            data = stream.read(32 * 1024 * 1024 + 1)
        if len(data) > 32 * 1024 * 1024: raise ValueError('圖片過大')
        try:
            with Image.open(BytesIO(data)) as image:
                if image.format != 'PNG' or image.width * image.height > 32_000_000 or getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('請選擇單張 PNG')
                image.verify()
        except (OSError, Image.DecompressionBombError) as exc:
            raise ValueError('無法讀取 PNG 素材') from exc
        return data
