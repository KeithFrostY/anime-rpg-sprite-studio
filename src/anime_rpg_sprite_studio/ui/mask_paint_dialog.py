"""Manual mask and repair editor; all edits remain a local candidate."""
from io import BytesIO

from PIL import Image, ImageChops
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget)

from ..rendering.mask_paint import PaintDocument, _read


def _qimage(image):
    image = image.convert('RGBA')
    return QImage(image.tobytes(), image.width, image.height, image.width*4, QImage.Format.Format_RGBA8888).copy()


class PaintCanvas(QWidget):
    def __init__(self, editor):
        super().__init__(); self.editor = editor; self.points = []; self.polygon = []
        self.pan_start = None; self.setMouseTracking(True); self.resize_for_zoom()

    def resize_for_zoom(self):
        w, h = self.editor.document.source.size; scale = self.editor.zoom.value()/100
        self.resize(max(1, round(w*scale)), max(1, round(h*scale))); self.update()

    def point(self, position):
        scale = self.editor.zoom.value()/100
        w, h = self.editor.document.source.size
        return max(0, min(w-1, int(position.x()/scale))), max(0, min(h-1, int(position.y()/scale)))

    def paintEvent(self, event):
        painter = QPainter(self)
        dirty = event.rect().intersected(self.rect())
        for y in range((dirty.top() // 16) * 16, dirty.bottom() + 1, 16):
            for x in range((dirty.left() // 16) * 16, dirty.right() + 1, 16):
                painter.fillRect(x, y, 16, 16, QColor('#d0d0d0' if (x//16+y//16)%2 else '#eeeeee'))
        d = self.editor.document
        if self.editor.show_source.isChecked():
            painter.setOpacity(.35); painter.drawImage(self.rect(), _qimage(d.source)); painter.setOpacity(1)
        painter.drawImage(self.rect(), _qimage(d.composite()))
        if self.editor.show_references.isChecked():
            for reference in self.editor.references:
                painter.setOpacity(.3); painter.drawImage(self.rect(), _qimage(reference)); painter.setOpacity(1)
        if self.editor.show_mask.isChecked():
            overlay = Image.new('RGBA', d.source.size, (255, 30, 30, 0))
            overlay.putalpha(d.mask.point(lambda a: a * 90 // 255))
            painter.drawImage(self.rect(), _qimage(overlay))
        scale = self.editor.zoom.value()/100
        painter.setPen(QPen(QColor('#00d8ff'), 2, Qt.PenStyle.DashLine))
        if self.polygon:
            points = QPolygonF([QPointF(x*scale, y*scale) for x,y in self.polygon])
            painter.drawPolyline(points)
            for p in points: painter.drawEllipse(p, 3, 3)
        if self.points:
            points = QPolygonF([QPointF(x*scale, y*scale) for x,y in self.points])
            painter.drawPolyline(points)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pan_start = event.globalPosition().toPoint(); return
        if event.button() != Qt.MouseButton.LeftButton: return
        point = self.point(event.position()); tool = self.editor.tool.currentData()
        if tool in ('polygon_add', 'polygon_erase'):
            self.polygon.append(point); self.update(); return
        if tool == 'pick':
            color = self.editor.document.pick(point, self.editor.sample_source.isChecked())
            if color is None: self.editor.status.setText('此處透明，沒有可吸取的顏色。')
            else:
                self.editor.color = QColor(*color); self.editor.color_button.setStyleSheet(f'background: {self.editor.color.name()}')
                self.editor.opacity.setValue(round(color[3]*100/255)); self.editor.status.setText('已吸取顏色。')
            return
        if tool == 'clone' and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.editor.clone_anchor = point; self.editor.status.setText(f'複製取樣點：{point}'); return
        if tool == 'clone' and self.editor.clone_anchor is None:
            self.editor.status.setText('先按住 Ctrl 點擊設定複製來源。'); return
        self.points = [point]; self.update()

    def mouseMoveEvent(self, event):
        if self.pan_start is not None:
            point = event.globalPosition().toPoint(); delta = point - self.pan_start; self.pan_start = point
            scroll = self.editor.scroll
            scroll.horizontalScrollBar().setValue(scroll.horizontalScrollBar().value()-delta.x())
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().value()-delta.y()); return
        if self.points:
            self.points.append(self.point(event.position())); self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pan_start = None; return
        if event.button() != Qt.MouseButton.LeftButton or not self.points: return
        self.points.append(self.point(event.position()))
        try:
            d = self.editor.document; tool = self.editor.tool.currentData()
            size = self.editor.brush_size.value(); alpha = round(self.editor.opacity.value()*255/100)
            if tool == 'clone': d.clone(self.editor.clone_anchor, self.points, size, alpha, self.editor.sample_source.isChecked())
            else: d.stroke(tool, self.points, size, (self.editor.color.red(), self.editor.color.green(), self.editor.color.blue(), alpha))
            self.editor.changed()
        except ValueError as exc: self.editor.status.setText(str(exc))
        self.points = []; self.update()


class MaskPaintDialog(QDialog):
    def __init__(self, source_bytes, mask_bytes=None, paint_bytes=None, references=None, parent=None):
        super().__init__(parent)
        self.document = PaintDocument(source_bytes, mask_bytes, paint_bytes)
        references = references or []
        if len(references) > 8: raise ValueError('最多提供 8 個參考圖層')
        self.references = [_read(reference) for reference in references]
        if any(image.size != self.document.source.size for image in self.references):
            raise ValueError('參考圖層必須與來源畫布相同')
        self.result_bytes = None; self.color = QColor(0,0,0); self.clone_anchor = None
        self.setWindowTitle('分件遮罩及補畫'); self.resize(1050, 780)
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.tool = QComboBox()
        for text, key in [('多邊形加入','polygon_add'), ('多邊形減去','polygon_erase'), ('遮罩筆','mask_add'), ('遮罩擦','mask_erase'), ('補畫筆','paint'), ('補畫擦','paint_erase'), ('吸色','pick'), ('複製筆','clone')]:
            self.tool.addItem(text, key)
        controls.addWidget(self.tool)
        finish = QPushButton('完成多邊形'); finish.clicked.connect(self.finish_polygon); controls.addWidget(finish)
        clear = QPushButton('取消多邊形'); clear.clicked.connect(self.clear_polygon); controls.addWidget(clear)
        controls.addWidget(QLabel('筆刷'))
        self.brush_size = QSpinBox(); self.brush_size.setRange(1,512); self.brush_size.setValue(12); controls.addWidget(self.brush_size)
        controls.addWidget(QLabel('補畫／複製不透明度 %'))
        self.opacity = QSpinBox(); self.opacity.setRange(0,100); self.opacity.setValue(100); controls.addWidget(self.opacity)
        self.tool.currentIndexChanged.connect(self.update_opacity_control)
        self.update_opacity_control()
        self.color_button = QPushButton('顏色'); self.color_button.clicked.connect(self.choose_color); controls.addWidget(self.color_button)
        layout.addLayout(controls)
        view = QHBoxLayout()
        self.show_source = QCheckBox('顯示原圖'); self.show_mask = QCheckBox('顯示遮罩')
        self.show_source.setChecked(self.document.mask.getbbox() is None)
        self.show_references = QCheckBox('顯示其他分件'); self.sample_source = QCheckBox('吸色／複製取樣來源（否則取合成分件）')
        for control in (self.show_source, self.show_mask, self.show_references, self.sample_source):
            view.addWidget(control); control.toggled.connect(lambda checked: self.canvas.update())
        view.addWidget(QLabel('縮放 %'))
        self.zoom = QSpinBox(); self.zoom.setRange(25,400); self.zoom.setValue(100); self.zoom.setSingleStep(25); view.addWidget(self.zoom)
        layout.addLayout(view)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(False)
        self.canvas = PaintCanvas(self); self.scroll.setWidget(self.canvas)
        self.zoom.valueChanged.connect(self.canvas.resize_for_zoom); layout.addWidget(self.scroll, 1)
        self.status = QLabel(f'拖曳繪製；中鍵拖動畫布；複製筆請先 Ctrl + 點擊取樣。撤銷上限：{self.document.limit} 次。')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        actions = QHBoxLayout()
        undo = QPushButton('撤銷'); undo.clicked.connect(self.undo); actions.addWidget(undo)
        redo = QPushButton('重做'); redo.clicked.connect(self.redo); actions.addWidget(redo)
        apply = QPushButton('套用到候選'); apply.clicked.connect(self.accept); actions.addWidget(apply)
        cancel = QPushButton('取消'); cancel.clicked.connect(self.reject); actions.addWidget(cancel)
        layout.addLayout(actions)

    def changed(self):
        self.status.setText(f'修改尚未套用；可撤銷 {len(self.document.undo_stack)} 次（上限 {self.document.limit}）。')
        self.canvas.update()

    def update_opacity_control(self, *args):
        self.opacity.setEnabled(self.tool.currentData() in ('paint', 'clone'))

    def choose_color(self):
        value = QColorDialog.getColor(self.color, self, '選擇補畫顏色')
        if value.isValid(): self.color = value; self.color_button.setStyleSheet(f'background: {value.name()}')

    def finish_polygon(self):
        try:
            tool = self.tool.currentData()
            if tool not in ('polygon_add', 'polygon_erase'): raise ValueError('請先選擇多邊形遮罩工具')
            self.document.polygon(self.canvas.polygon, add=tool == 'polygon_add')
            self.canvas.polygon = []; self.changed()
        except ValueError as exc: self.status.setText(str(exc))

    def clear_polygon(self): self.canvas.polygon = []; self.canvas.update()
    def undo(self): self.document.undo(); self.changed()
    def redo(self): self.document.redo(); self.changed()

    def accept(self):
        if self.canvas.polygon:
            self.status.setText('請先完成或取消多邊形。'); return
        try: self.result_bytes = self.document.result_bytes()
        except (OSError, ValueError, MemoryError) as exc:
            self.status.setText(f'無法合成：{exc}'); return
        super().accept()

    def reject(self):
        if (self.document.dirty or self.canvas.polygon) and QMessageBox.question(self, '尚未套用', '放棄未套用的遮罩和補畫嗎？') != QMessageBox.StandardButton.Yes:
            return
        super().reject()
