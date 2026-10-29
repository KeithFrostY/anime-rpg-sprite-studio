from copy import deepcopy
from pathlib import Path
from threading import Event
from PySide6.QtCore import Qt, QThreadPool, QTimer, QSize
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QSpinBox, QComboBox, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QCheckBox,
)
from ..core.models import Direction
from ..core.rig import WalkParameters
from .preview import Preview
from .template_worker import TemplateWorker


class TemplateDialog(QDialog):
    """Modal snapshot editor: nothing is persisted until explicit candidate apply."""
    def __init__(self, service, character_id, parent=None):
        super().__init__(parent)
        self.service = service
        self.character_id = character_id
        self.project = service.project
        self.project_path = service.path
        self.template = None
        self.assets = {}
        self.candidate = None
        self.candidate_template = None
        self.frame_index = 0
        self.job_id = 0
        self._busy = False
        self._closed = False
        self._workers = {}
        self._cancel = Event()
        self._updating = False
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.advance_frame)
        self.setWindowTitle("分層模板 · CPU Walk 候選預覽")
        self.resize(1000, 810)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("四方向 × 六層 · 256×256 RGBA · 關節與繪製順序由模板 JSON 定義"))
        sources = QHBoxLayout()
        self.demo_button = QPushButton("載入離線測試模板")
        self.demo_button.clicked.connect(self.load_demo)
        self.load_button = QPushButton("載入模板 JSON")
        self.load_button.clicked.connect(self.load_manifest)
        sources.addWidget(self.demo_button)
        sources.addWidget(self.load_button)
        layout.addLayout(sources)
        self.template_label = QLabel("尚未載入模板；測試人偶為功能驗證素材，非 AI 成果")
        self.template_label.setWordWrap(True)
        layout.addWidget(self.template_label)
        middle = QHBoxLayout()
        self.preview = Preview()
        middle.addWidget(self.preview, 1)
        form = QFormLayout()
        self.arm_swing = QSpinBox()
        self.arm_swing.setRange(0, 30)
        self.arm_swing.setValue(12)
        self.arm_swing.setSuffix(" °")
        self.leg_swing = QSpinBox()
        self.leg_swing.setRange(0, 25)
        self.leg_swing.setValue(10)
        self.leg_swing.setSuffix(" °")
        self.bob = QSpinBox()
        self.bob.setRange(0, 6)
        self.bob.setValue(2)
        self.bob.setSuffix(" px")
        for label, spin in (("手臂擺幅", self.arm_swing), ("腿部擺幅", self.leg_swing), ("身體起伏", self.bob)):
            form.addRow(label, spin)
            spin.valueChanged.connect(self.parameters_changed)
        self.fps = QSpinBox()
        self.fps.setRange(1, 60)
        character = self.character()
        self.fps.setValue(character.clips[0].fps)
        self.fps.valueChanged.connect(lambda value: self.timer.setInterval(round(1000 / value)))
        form.addRow("預覽 FPS（套用時保存）", self.fps)
        self.generate_button = QPushButton("生成 16 幀候選")
        self.generate_button.clicked.connect(self.generate)
        form.addRow(self.generate_button)
        self.cancel_button = QPushButton("取消背景工作")
        self.cancel_button.clicked.connect(self.cancel_work)
        form.addRow(self.cancel_button)
        self.quality_button = QPushButton("檢查候選一致性")
        self.quality_button.clicked.connect(self.check_quality)
        form.addRow(self.quality_button)
        middle.addLayout(form)
        layout.addLayout(middle, 1)
        navigation = QHBoxLayout()
        self.direction = QComboBox()
        self.direction.addItems([d.value.title() for d in Direction])
        self.direction.currentIndexChanged.connect(self.direction_changed)
        navigation.addWidget(self.direction)
        self.play_button = QPushButton("播放候選")
        self.play_button.clicked.connect(self.toggle_playback)
        navigation.addWidget(self.play_button)
        self.baseline_check = QCheckBox("腳底線")
        self.baseline_check.setChecked(True)
        self.baseline_check.toggled.connect(self.preview.set_baseline)
        self.onion_check = QCheckBox("前後幀疊影")
        self.onion_check.toggled.connect(self.preview.set_onion)
        navigation.addWidget(self.baseline_check)
        navigation.addWidget(self.onion_check)
        self.slots = []
        for i in range(4):
            button = QPushButton(str(i))
            button.setIconSize(QSize(48, 48))
            button.clicked.connect(lambda checked=False, index=i: self.select_frame(index))
            self.slots.append(button)
            navigation.addWidget(button)
        layout.addLayout(navigation)
        self.layers_table = QTableWidget(0, 3)
        self.layers_table.setHorizontalHeaderLabels(["繪製順序 / 圖層", "旋轉關節 (x,y)", "素材路徑"])
        self.layers_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.layers_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.layers_table.horizontalHeader().setStretchLastSection(True)
        self.layers_table.setMaximumHeight(210)
        layout.addWidget(self.layers_table)
        self.status = QLabel("候選不會改動原有 Walk；確認套用後才取代。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.apply_button = QPushButton("套用候選，取代 Walk")
        self.apply_button.clicked.connect(self.apply_candidate)
        close = QPushButton("關閉／放棄候選")
        close.clicked.connect(self.reject)
        actions.addWidget(self.apply_button)
        actions.addWidget(close)
        layout.addLayout(actions)
        self.update_controls()
        if character.template is not None:
            self.start_work("project", (deepcopy(character.template), service.path.parent))

    def character(self):
        return next(c for c in self.service.project.characters if c.id == self.character_id)

    def update_controls(self):
        self.generate_button.setEnabled(self.template is not None and not self._busy)
        self.apply_button.setEnabled(self.candidate is not None and not self._busy)
        self.play_button.setEnabled(self.candidate is not None and not self._busy)
        self.quality_button.setEnabled(self.candidate is not None and not self._busy)
        self.cancel_button.setEnabled(self._busy)
        for widget in (self.demo_button, self.load_button, self.arm_swing, self.leg_swing, self.bob):
            widget.setEnabled(not self._busy)

    def clear_candidate(self):
        self.timer.stop()
        self.play_button.setText("播放候選")
        self.candidate = None
        self.candidate_template = None
        self.frame_index = 0
        self.display_frame()
        self.update_controls()

    def parameters_changed(self):
        if self._updating:
            return
        self.clear_candidate()
        self.status.setText("參數已改變，請重新生成候選。")

    def load_demo(self):
        self.start_work("demo", None)

    def load_manifest(self):
        path, _ = QFileDialog.getOpenFileName(self, "載入四方向六層模板", "", "Template JSON (*.json)")
        if path:
            self.start_work("load", Path(path))

    def start_work(self, operation, payload):
        self._cancel.set()
        self.job_id += 1
        self._cancel = Event()
        self.clear_candidate()
        self._busy = True
        self.status.setText("正在以 CPU 生成 16 幀候選…" if operation == "generate" else "正在驗證模板與 24 張圖層…")
        self.update_controls()
        worker = TemplateWorker(self.job_id, operation, payload, self._cancel)
        self._workers[self.job_id] = worker
        worker.signals.finished.connect(self.work_finished)
        QThreadPool.globalInstance().start(worker)

    def generate(self):
        if self.template is None or self._busy:
            return
        snapshot = deepcopy(self.template)
        snapshot.parameters = WalkParameters(self.arm_swing.value(), self.leg_swing.value(), self.bob.value())
        self.start_work("generate", (snapshot, dict(self.assets)))
        self.candidate_template = snapshot

    def cancel_work(self):
        self._cancel.set()
        self.job_id += 1
        self._busy = False
        self.clear_candidate()
        self.status.setText("已取消；原模板與動畫保持不變。")

    def work_finished(self, job_id, operation, result, error):
        self._workers.pop(job_id, None)
        if self._closed or job_id != self.job_id:
            return
        self._busy = False
        if error:
            self.candidate_template = None
            self.status.setText(f"工作失敗，原動畫保留：{error}")
        elif operation == "generate":
            self.candidate = result
            self.status.setText("候選已生成，尚未套用。" + ("\n" + "\n".join(result.warnings) if result.warnings else " 未偵測到畫布裁切。"))
        else:
            self.template, self.assets = result
            self.template_label.setText(self.template.name)
            self._updating = True
            self.arm_swing.setValue(self.template.parameters.arm_swing)
            self.leg_swing.setValue(self.template.parameters.leg_swing)
            self.bob.setValue(self.template.parameters.bob)
            self._updating = False
            self.status.setText("模板驗證完成。可調整參數並生成候選；原動畫未變更。")
        self.direction_changed()
        self.update_controls()

    def direction_changed(self, *args):
        self.timer.stop()
        self.play_button.setText("播放候選")
        self.frame_index = 0
        self.layers_table.setRowCount(0)
        if self.template:
            direction = list(Direction)[self.direction.currentIndex()]
            view = next(v for v in self.template.views if v.direction == direction)
            self.layers_table.setRowCount(6)
            for row, layer in enumerate(view.layers):
                for column, text in enumerate((f"{row}: {layer.part}", str(layer.joint), layer.asset_path)):
                    self.layers_table.setItem(row, column, QTableWidgetItem(text))
        self.display_frame()

    def display_frame(self):
        batch = self.candidate.frames[list(Direction)[self.direction.currentIndex()]] if self.candidate else {}
        self.preview.pixmap = QPixmap()
        pixmaps = {}
        for i, button in enumerate(self.slots):
            pixmap = QPixmap()
            if i in batch:
                pixmap.loadFromData(batch[i])
            pixmaps[i] = pixmap
            button.setIcon(QIcon(pixmap))
            button.setText(f"{'▶ ' if i == self.frame_index else ''}{i}")
            if i == self.frame_index:
                self.preview.pixmap = pixmap
        self.preview.set_neighbors(pixmaps[(self.frame_index - 1) % 4], pixmaps[(self.frame_index + 1) % 4])
        self.preview.update()

    def check_quality(self):
        if self.candidate is None or self._busy:
            return
        from .quality_dialog import QualityDialog
        self.timer.stop()
        self.play_button.setText("播放候選")
        dialog = QualityDialog(frames=self.candidate.frames, parent=self)
        dialog.exec()
        dialog.deleteLater()

    def toggle_playback(self):
        if self.timer.isActive():
            self.timer.stop()
            self.play_button.setText("播放候選")
        elif self.candidate is not None:
            self.timer.start(round(1000 / self.fps.value()))
            self.play_button.setText("暫停")

    def advance_frame(self):
        self.frame_index = (self.frame_index + 1) % 4
        self.display_frame()

    def select_frame(self, index):
        self.timer.stop()
        self.play_button.setText("播放候選")
        self.frame_index = index
        self.display_frame()

    def apply_candidate(self):
        if self.candidate is None or self._busy:
            return
        if self.service.project is not self.project or self.service.path != self.project_path:
            self.cancel_work()
            self.status.setText("專案已改變，請重新開啟模板視窗。")
            return
        if QMessageBox.question(self, "套用 16 幀候選", "將取代此角色的四方向 Walk 與模板，是否套用？") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.apply_walk(self.character_id, self.candidate_template, self.assets, self.candidate.frames)
            self.character().clips[0].fps = self.fps.value()
        except (OSError, ValueError) as exc:
            self.status.setText(f"套用失敗，原動畫保留：{exc}")
            return
        self.accept()

    def done(self, result):
        self._closed = True
        self._cancel.set()
        self.job_id += 1
        self.timer.stop()
        super().done(result)
