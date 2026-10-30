from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QIcon
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSpinBox, QComboBox, QCheckBox, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox)

from ..animation.single_direction import split_grid, export_animation, crop_boxes, normalize_frames
from .crop_editor import CropEditor


def pixmap(image):
    image = image.convert('RGBA')
    data = image.tobytes('raw', 'RGBA')
    return QPixmap.fromImage(QImage(data, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888).copy())


class SingleDirectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('單方向動畫：切割及預覽')
        self.resize(900, 720)
        self.source = None
        self.frames = []
        self.offsets = []
        self._changing_offset = False
        self.index = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        button = QPushButton('選擇圖片')
        button.clicked.connect(self.choose_image)
        top.addWidget(button)
        self.mode = QComboBox(); self.mode.addItems(['平均網格', '自訂切割'])
        self.mode.currentIndexChanged.connect(self.change_mode)
        top.addWidget(self.mode)
        self.columns = QSpinBox(); self.columns.setRange(1, 32); self.columns.setValue(3)
        self.rows = QSpinBox(); self.rows.setRange(1, 32); self.rows.setValue(2)
        top.addWidget(QLabel('欄')); top.addWidget(self.columns)
        top.addWidget(QLabel('列')); top.addWidget(self.rows)
        split = QPushButton('切割'); split.clicked.connect(self.resplit); top.addWidget(split)
        layout.addLayout(top)
        margin_layout = QHBoxLayout()
        self.margins = []
        for label in ('左邊距', '上邊距', '右邊距', '下邊距'):
            margin_layout.addWidget(QLabel(label))
            spin = QSpinBox(); spin.setRange(0, 32768); self.margins.append(spin)
            margin_layout.addWidget(spin)
        layout.addLayout(margin_layout)
        self.grid_preview = QLabel('選擇圖片後檢查切割線；原背景會保留')
        self.grid_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.grid_preview)
        self.crop_editor = CropEditor()
        self.crop_editor.hide()
        self.crop_editor.changed.connect(self.refresh_manual)
        self.crop_editor.selected.connect(self.listing_select)
        layout.addWidget(self.crop_editor)
        self.manual_controls = QHBoxLayout()
        self.add_box_button = QPushButton('新增框（拖曳）')
        self.add_box_button.clicked.connect(self.start_new_box)
        self.delete_box_button = QPushButton('刪除選取框')
        self.delete_box_button.clicked.connect(self.delete_box)
        self.manual_controls.addWidget(self.add_box_button)
        self.manual_controls.addWidget(self.delete_box_button)
        layout.addLayout(self.manual_controls)
        self.add_box_button.hide(); self.delete_box_button.hide()
        self.preview = QLabel('動畫預覽')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(220)
        layout.addWidget(self.preview)
        self.listing = QListWidget()
        self.listing.setFlow(QListWidget.Flow.LeftToRight)
        self.listing.setMaximumHeight(110)
        self.listing.setIconSize(QSize(64, 64))
        self.listing.currentRowChanged.connect(self.show_frame)
        layout.addWidget(self.listing)
        ordering = QHBoxLayout()
        for label, delta in [('往前', -1), ('往後', 1)]:
            b = QPushButton(label); b.clicked.connect(lambda checked=False, d=delta: self.move_frame(d)); ordering.addWidget(b)
        layout.addLayout(ordering)
        alignment = QHBoxLayout()
        self.offset_x = QSpinBox(); self.offset_x.setRange(-32768, 32768)
        self.offset_y = QSpinBox(); self.offset_y.setRange(-32768, 32768)
        self.offset_x.valueChanged.connect(self.offset_changed)
        self.offset_y.valueChanged.connect(self.offset_changed)
        alignment.addWidget(QLabel('選取幀水平位移')); alignment.addWidget(self.offset_x)
        alignment.addWidget(QLabel('垂直位移')); alignment.addWidget(self.offset_y)
        layout.addLayout(alignment)
        controls = QHBoxLayout()
        self.kind = QComboBox(); self.kind.addItems(['行走', '攻擊'])
        self.loop = QCheckBox('循環'); self.loop.setChecked(True)
        self.kind.currentIndexChanged.connect(lambda i: self.loop.setChecked(i == 0))
        self.direction = QComboBox(); self.direction.addItems(['Front', 'Left', 'Right', 'Back']); self.direction.setCurrentText('Right')
        self.fps = QSpinBox(); self.fps.setRange(1, 60); self.fps.setValue(8)
        for widget in (self.kind, self.direction, QLabel('FPS'), self.fps, self.loop): controls.addWidget(widget)
        play = QPushButton('播放／暫停'); play.clicked.connect(self.toggle_play); controls.addWidget(play)
        export = QPushButton('匯出…'); export.clicked.connect(self.export); controls.addWidget(export)
        layout.addLayout(controls)
        layout.addWidget(QLabel('背景會保留；請檢查人物、武器或特效有否被切割線截斷。'))

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(self, '選擇圖片', '', '圖片 (*.png *.jpg *.jpeg *.webp)')
        if path:
            try: self.load_image(path)
            except (OSError, ValueError) as exc: QMessageBox.warning(self, '無法載入', str(exc))

    def load_image(self, path):
        with Image.open(path) as image:
            if image.width * image.height > 32_000_000 or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('圖片過大或包含多張影格')
            self.source = ImageOps.exif_transpose(image).convert('RGBA')
        for margin in self.margins: margin.setValue(0)
        self.crop_editor.set_image(pixmap(self.source))
        if self.mode.currentIndex():
            self.frames = []; self.offsets = []; self.refresh_list(-1)
        else: self.resplit()

    def change_mode(self, index):
        if not hasattr(self, 'crop_editor'): return
        self.timer.stop()
        self.grid_preview.setVisible(index == 0)
        self.crop_editor.setVisible(index == 1)
        self.add_box_button.setVisible(index == 1); self.delete_box_button.setVisible(index == 1)
        self.frames = []; self.offsets = []; self.crop_editor.boxes = []; self.crop_editor.current = -1
        self.refresh_list(-1)
        if index == 0: self.resplit()

    def start_new_box(self):
        self.crop_editor.draw_new = True

    def listing_select(self, index):
        if hasattr(self, 'listing'): self.listing.setCurrentRow(index)

    def delete_box(self):
        i = self.listing.currentRow()
        if self.mode.currentIndex() and 0 <= i < len(self.crop_editor.boxes):
            self.crop_editor.boxes.pop(i)
            if i < len(self.offsets): self.offsets.pop(i)
            self.crop_editor.current = min(i, len(self.crop_editor.boxes)-1)
            self.refresh_manual()

    def refresh_manual(self):
        if self.source is None: return
        self.timer.stop()
        boxes = self.crop_editor.boxes
        self.frames = crop_boxes(self.source, boxes) if boxes else []
        self.offsets = (self.offsets + [(0, 0)] * len(self.frames))[:len(self.frames)]
        self.refresh_list(self.crop_editor.current)
        self.crop_editor.update()

    def normalized(self):
        return normalize_frames(self.frames, self.offsets)

    def offset_changed(self):
        if self._changing_offset: return
        i = self.listing.currentRow()
        if 0 <= i < len(self.offsets):
            old = self.offsets[i]
            self.offsets[i] = (self.offset_x.value(), self.offset_y.value())
            try: self.normalized()
            except ValueError as exc:
                self.offsets[i] = old
                QMessageBox.warning(self, '位移無效', str(exc))
            self.show_frame(i)

    def resplit(self):
        if self.source is None: return
        if self.mode.currentIndex(): return
        left, top, right_margin, bottom_margin = [spin.value() for spin in self.margins]
        right, bottom = self.source.width - right_margin, self.source.height - bottom_margin
        try: frames = split_grid(self.source, self.columns.value(), self.rows.value(), (left, top, right, bottom))
        except ValueError as exc:
            QMessageBox.warning(self, '無法切割', str(exc)); return
        self.timer.stop(); self.frames = frames; self.offsets = [(0, 0)] * len(frames)
        grid = pixmap(self.source)
        painter = QPainter(grid); painter.setPen(QPen(QColor('red'), 3))
        painter.drawRect(left, top, right - left - 1, bottom - top - 1)
        for x in range(1, self.columns.value()):
            px = left + x * (right - left) // self.columns.value()
            painter.drawLine(px, top, px, bottom)
        for y in range(1, self.rows.value()):
            py = top + y * (bottom - top) // self.rows.value()
            painter.drawLine(left, py, right, py)
        painter.end()
        self.grid_preview.setPixmap(grid.scaled(650, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.refresh_list(0)

    def refresh_list(self, selected):
        self.listing.clear()
        for i, frame in enumerate(self.frames):
            self.listing.addItem(QListWidgetItem(QIcon(pixmap(frame)), str(i + 1)))
        self.listing.setCurrentRow(selected)

    def show_frame(self, index):
        if 0 <= index < len(self.frames):
            self.index = index
            self._changing_offset = True
            self.offset_x.setValue(self.offsets[index][0]); self.offset_y.setValue(self.offsets[index][1])
            self._changing_offset = False
            if self.mode.currentIndex(): self.crop_editor.current = index; self.crop_editor.update()
            self.preview.setPixmap(pixmap(self.normalized()[index]).scaled(500, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def move_frame(self, delta):
        index = self.listing.currentRow(); other = index + delta
        if 0 <= index < len(self.frames) and 0 <= other < len(self.frames):
            self.frames[index], self.frames[other] = self.frames[other], self.frames[index]
            self.offsets[index], self.offsets[other] = self.offsets[other], self.offsets[index]
            if self.mode.currentIndex():
                boxes = self.crop_editor.boxes
                boxes[index], boxes[other] = boxes[other], boxes[index]
            self.refresh_list(other)

    def toggle_play(self):
        if self.timer.isActive(): self.timer.stop(); return
        if not self.frames: return
        if not self.loop.isChecked() and self.index == len(self.frames) - 1: self.listing.setCurrentRow(0)
        self.timer.start(max(1, 1000 // self.fps.value()))

    def advance(self):
        if self.index + 1 >= len(self.frames):
            if not self.loop.isChecked(): self.timer.stop(); return
            self.listing.setCurrentRow(0)
        else: self.listing.setCurrentRow(self.index + 1)

    def export(self):
        if not self.frames: return
        destination = QFileDialog.getExistingDirectory(self, '選擇匯出位置')
        if not destination: return
        try:
            path = export_animation(self.normalized(), Path(destination), 'walk' if self.kind.currentIndex() == 0 else 'attack', self.direction.currentText().lower(), self.fps.value(), self.loop.isChecked())
            QMessageBox.information(self, '匯出完成', f'已匯出至：\n{path}')
        except (OSError, ValueError) as exc: QMessageBox.warning(self, '匯出失敗', str(exc))

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)
