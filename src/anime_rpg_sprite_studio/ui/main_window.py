from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QThreadPool, QSize
from PySide6.QtGui import QAction, QPixmap, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget,
    QPushButton, QLabel, QLineEdit, QTextEdit, QFormLayout, QComboBox,
    QSpinBox, QFileDialog, QMessageBox, QInputDialog, QCheckBox,
)
from ..core.models import Direction
from ..core.project_service import ProjectService
from ..ai.mock_provider import MockProvider
from ..ai.contracts import GenerationRequest
from .sprite_worker import SpriteWorker
from .preview import Preview


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.service = ProjectService()
        self._ai_session = None
        self.current_direction = Direction.FRONT
        self.resize(1100, 760)
        self._syncing = False
        self.frame_index = 0
        self.frame_pixmaps = {}
        self._epoch = 0
        self._workers = {}
        self._import_busy = False
        self.playback_timer = QTimer(self)
        self.playback_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.playback_timer.timeout.connect(self.advance_frame)
        menu = self.menuBar().addMenu("檔案")
        for text, callback, shortcut in [
            ("新建專案", self.new_project, "Ctrl+N"),
            ("開啟專案", self.open_project, "Ctrl+O"),
            ("儲存", self.save_project, "Ctrl+S"),
            ("另存新檔", lambda: self.save_project(save_as=True), "Ctrl+Shift+S"),
        ]:
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(lambda checked=False, fn=callback: fn())
            menu.addAction(action)
        self.export_action = menu.addAction("匯出 PNG／Sprite Sheet／JSON…")
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self.open_export_dialog)
        settings = self.menuBar().addMenu("設定")
        settings.addAction("fal.ai Key 設定", self.key_settings)
        settings.addAction("AI 候選／預算與請求紀錄", self.open_ai_dialog)
        self.menuBar().addMenu("說明").addAction("快速開始", self.show_help)
        center = QWidget()
        self.setCentralWidget(center)
        layout = QVBoxLayout(center)
        header = QHBoxLayout()
        self.project_label = QLabel()
        header.addWidget(self.project_label)
        header.addStretch()
        header.addWidget(QLabel("Provider：Mock · 離線 · US$0"))
        rename = QPushButton("重新命名專案")
        rename.clicked.connect(self.rename_project)
        header.addWidget(rename)
        self.export_button = QPushButton("匯出…")
        self.export_button.clicked.connect(self.open_export_dialog)
        header.addWidget(self.export_button)
        self.quality_button = QPushButton("一致性檢查")
        self.quality_button.clicked.connect(self.open_quality_dialog)
        header.addWidget(self.quality_button)
        ai_button = QPushButton("AI 候選／預算")
        ai_button.clicked.connect(self.open_ai_dialog)
        header.addWidget(ai_button)
        layout.addLayout(header)
        split = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("角色 / Walk"))
        self.characters = QListWidget()
        self.characters.currentRowChanged.connect(self.select_character)
        left_layout.addWidget(self.characters)
        add = QPushButton("新增角色")
        add.clicked.connect(self.add_character)
        left_layout.addWidget(add)
        split.addWidget(left)
        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        self.preview = Preview()
        middle_layout.addWidget(self.preview)
        middle_layout.addWidget(QLabel("256×256 RGBA · 腳底中心 Pivot · 紅色十字"))
        mock = QPushButton("顯示 Mock 測試占位圖")
        mock.clicked.connect(self.show_mock)
        middle_layout.addWidget(mock)
        self.mock_label = QLabel("Mock 圖不是 AI 成果，也不是 Walk 動畫")
        middle_layout.addWidget(self.mock_label)
        split.addWidget(middle)
        right = QWidget()
        form = QFormLayout(right)
        self.name_edit = QLineEdit()
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(160)
        self.fps = QSpinBox()
        self.fps.setRange(1, 60)
        self.fps.setValue(8)
        self.name_edit.textChanged.connect(self.edit_character)
        self.description_edit.textChanged.connect(self.edit_character)
        self.fps.valueChanged.connect(self.edit_character)
        form.addRow("角色名稱", self.name_edit)
        form.addRow("描述", self.description_edit)
        form.addRow("FPS", self.fps)
        form.addRow(QLabel("日系動漫 RPG\n3–4 頭身 · 2D 斜俯視\nFront / Left / Right / Back\n每方向 4 幀 · 共 16 幀"))
        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        form.addRow(self.validation_label)
        split.addWidget(right)
        split.setSizes([210, 530, 300])
        layout.addWidget(split, 1)
        controls = QHBoxLayout()
        self.direction = QComboBox()
        self.direction.addItems([d.value.title() for d in Direction])
        self.direction.currentIndexChanged.connect(self.change_direction)
        controls.addWidget(self.direction)
        self.play_button = QPushButton("播放")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.toggle_playback)
        controls.addWidget(self.play_button)
        self.baseline_check = QCheckBox("腳底線")
        self.baseline_check.setChecked(True)
        self.baseline_check.toggled.connect(self.preview.set_baseline)
        self.onion_check = QCheckBox("前後幀疊影")
        self.onion_check.toggled.connect(self.preview.set_onion)
        controls.addWidget(self.baseline_check)
        controls.addWidget(self.onion_check)
        self.import_button = QPushButton("匯入 PNG（1 或 4 張）")
        self.import_button.clicked.connect(self.import_dialog)
        controls.addWidget(self.import_button)
        self.template_button = QPushButton("分層模板／生成 Walk")
        self.template_button.clicked.connect(self.open_template_dialog)
        controls.addWidget(self.template_button)
        layout.addLayout(controls)
        slots = QHBoxLayout()
        self.slot_buttons = []
        for i in range(4):
            button = QPushButton(f"幀 {i}：空")
            button.setIconSize(QSize(64, 64))
            button.clicked.connect(lambda checked=False, index=i: self.select_frame(index))
            self.slot_buttons.append(button)
            slots.addWidget(button)
        layout.addLayout(slots)
        self.slots_label = QLabel()
        layout.addWidget(self.slots_label)
        self.statusBar().showMessage("離線就緒 · AI 預設 Mock · fal.ai 每次付費前需確認")
        self.refresh()

    def active_character(self):
        return next((c for c in self.service.project.characters if c.id == self.service.project.active_character_id), None)

    def refresh(self):
        self._syncing = True
        self.characters.clear()
        for c in self.service.project.characters:
            self.characters.addItem(c.name)
        active = self.active_character()
        if active:
            self.characters.setCurrentRow(self.service.project.characters.index(active))
        self._syncing = False
        self.load_fields()
        self.update_title()

    def update_title(self):
        self.setWindowTitle(f"{self.service.project.name}{' *' if self.service.dirty else ''} — Anime RPG Sprite Studio")
        self.project_label.setText(self.service.project.name)
        self.update_export_action()

    def update_export_action(self):
        c = self.active_character()
        enabled = bool(c and self.service.path is not None and not self._import_busy
                       and c.name.strip() and not c.clips[0].validate(complete=True))
        self.export_action.setEnabled(enabled)
        self.export_button.setEnabled(enabled)
        self.quality_button.setEnabled(enabled)

    def load_fields(self):
        self._syncing = True
        c = self.active_character()
        self.name_edit.setText(c.name if c else "")
        self.description_edit.setPlainText(c.description if c else "")
        self.fps.setValue(c.clips[0].fps if c else 8)
        for widget in (self.name_edit, self.description_edit, self.fps):
            widget.setEnabled(c is not None)
        self.preview.pixmap = QPixmap()
        self.preview.update()
        self._syncing = False
        self.change_direction(self.direction.currentIndex())

    def add_character(self):
        self.service.add_character()
        self.refresh()

    def select_character(self, index):
        if self._syncing or index < 0:
            return
        self.service.project.active_character_id = self.service.project.characters[index].id
        self.service.dirty = True
        self.load_fields()
        self.update_title()

    def edit_character(self, *args):
        c = self.active_character()
        if self._syncing or c is None:
            return
        c.name = self.name_edit.text()
        c.description = self.description_edit.toPlainText()
        c.clips[0].fps = self.fps.value()
        self.characters.currentItem().setText(c.name or "（名稱不可空白）")
        self.service.dirty = True
        self.playback_timer.setInterval(round(1000 / self.fps.value()))
        self.update_title()

    def change_direction(self, index):
        self.stop_playback()
        self.frame_index = 0
        self.frame_pixmaps = {}
        self._epoch += 1
        self.current_direction = list(Direction)[index]
        c = self.active_character()
        occupied = {f.index for f in c.clips[0].frames if f.direction == self.current_direction} if c else set()
        self.slots_label.setText("  ".join(f"[{i}: {'已登錄' if i in occupied else '空'}]" for i in range(4)))
        self.validation_label.setText("草稿：尚缺完整 16 幀" if c and c.clips[0].validate(complete=True) else "請新增角色" if not c else "幀資料完整；圖片驗證於 Phase 2")
        self.play_button.setEnabled(False)
        self.import_button.setEnabled(c is not None and not self._import_busy)
        self.template_button.setEnabled(c is not None and not self._import_busy)
        self.update_export_action()
        self.display_frame()
        if c and self.service.path:
            try:
                paths = {f.index: self.service.repository._asset(self.service.path.parent, f.asset_path)
                         for f in c.clips[0].frames if f.direction == self.current_direction}
                if paths:
                    self.start_worker("load", paths)
            except (OSError, ValueError) as exc:
                self.validation_label.setText(str(exc))

    def stop_playback(self):
        self.playback_timer.stop()
        self.play_button.setText("播放")

    def toggle_playback(self):
        if self.playback_timer.isActive():
            self.stop_playback()
        elif set(self.frame_pixmaps) == {0, 1, 2, 3}:
            self.playback_timer.start(round(1000 / self.fps.value()))
            self.play_button.setText("暫停")

    def advance_frame(self):
        self.frame_index = (self.frame_index + 1) % 4
        self.display_frame()

    def select_frame(self, index):
        self.stop_playback()
        self.frame_index = index
        self.display_frame()

    def display_frame(self):
        self.preview.pixmap = self.frame_pixmaps.get(self.frame_index, QPixmap())
        self.preview.set_neighbors(self.frame_pixmaps.get((self.frame_index - 1) % 4, QPixmap()),
                                   self.frame_pixmaps.get((self.frame_index + 1) % 4, QPixmap()))
        self.preview.update()
        for i, button in enumerate(self.slot_buttons):
            pixmap = self.frame_pixmaps.get(i)
            button.setIcon(QIcon(pixmap) if pixmap is not None else QIcon())
            button.setText(f"{'▶ ' if i == self.frame_index else ''}幀 {i}" + ("：空" if pixmap is None else ""))

    def start_worker(self, kind, paths):
        c = self.active_character()
        token = (self._epoch, id(self.service.project), c.id, self.current_direction,
                 str(self.service.path), kind)
        worker = SpriteWorker(token, paths)
        self._workers[id(worker)] = worker
        worker.signals.finished.connect(self.worker_finished)
        QThreadPool.globalInstance().start(worker)

    def worker_finished(self, token, images, error):
        for key, worker in list(self._workers.items()):
            if worker.token == token:
                del self._workers[key]
        if token[-1] == "import":
            self._import_busy = False
        c = self.active_character()
        current = (self._epoch, id(self.service.project), c.id if c else None,
                   self.current_direction, str(self.service.path))
        self.import_button.setEnabled(c is not None and not self._import_busy)
        self.template_button.setEnabled(c is not None and not self._import_busy)
        self.update_export_action()
        if token[:-1] != current:
            if token[-1] == "import":
                self.statusBar().showMessage("已切換專案、角色或方向；先前匯入結果已取消，原資料保留。")
            return
        if error:
            self.validation_label.setText(f"圖片載入失敗：{error}")
            if token[-1] == "import":
                QMessageBox.warning(self, "匯入失敗，原資料已保留", error)
            return
        if token[-1] == "import":
            try:
                self.service.import_frames(c.id, self.current_direction, images)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "匯入失敗，原資料已保留", str(exc))
                return
            self.update_title()
            self.change_direction(self.direction.currentIndex())
            return
        self.frame_pixmaps = {}
        for index, data in images.items():
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                self.frame_pixmaps[index] = pixmap
        self.play_button.setEnabled(set(self.frame_pixmaps) == {0, 1, 2, 3})
        self.validation_label.setText(f"{self.current_direction.value.title()}：{len(self.frame_pixmaps)}/4 幀可用")
        self.display_frame()

    def import_dialog(self):
        if self._import_busy or self.active_character() is None:
            return
        if self.service.path is None and not self.save_project():
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "選取 1 張或 4 張 PNG", "", "PNG (*.png)")
        if not paths:
            return
        if len(paths) not in (1, 4):
            QMessageBox.warning(self, "匯入", "請選擇 1 張或 4 張 PNG")
            return
        mapping = {self.frame_index: paths[0]} if len(paths) == 1 else dict(enumerate(paths))
        message = f"方向：{self.current_direction.value.title()}\n" + "\n".join(f"幀 {i} ← {Path(p).name}" for i, p in mapping.items())
        message += "\n將取代對應幀槽。是否繼續？"
        if QMessageBox.question(self, "確認匯入順序", message) != QMessageBox.StandardButton.Yes:
            return
        self.stop_playback()
        self._epoch += 1  # Ignore any earlier preview decode.
        self._import_busy = True
        self.import_button.setEnabled(False)
        self.template_button.setEnabled(False)
        self.update_export_action()
        self.start_worker("import", mapping)

    def open_export_dialog(self):
        from ..export.service import capture_export
        from .export_dialog import ExportDialog
        c = self.active_character()
        if self._import_busy or c is None or self.service.path is None:
            return
        try:
            snapshot = capture_export(c, self.service.path)
        except ValueError as exc:
            QMessageBox.warning(self, "無法匯出", str(exc))
            return
        self.stop_playback()
        self._epoch += 1
        dialog = ExportDialog(snapshot, self)
        dialog.exec()
        if dialog.result_path is not None:
            self.statusBar().showMessage(f"匯出完成：{dialog.result_path}")
        self.change_direction(self.direction.currentIndex())
        dialog.deleteLater()

    def open_template_dialog(self):
        from .template_dialog import TemplateDialog
        if self._import_busy or self.active_character() is None:
            return
        if self.service.path is None and not self.save_project():
            return
        self.stop_playback()
        self._epoch += 1
        dialog = TemplateDialog(self.service, self.active_character().id, self)
        dialog.exec()
        self.refresh()
        dialog.deleteLater()

    def show_mock(self):
        self.stop_playback()
        result = MockProvider().generate(GenerationRequest(prompt="placeholder"))
        self.preview.pixmap = QPixmap()
        self.preview.set_neighbors(QPixmap(), QPixmap())
        self.preview.pixmap.loadFromData(result.png)
        self.preview.update()

    def open_quality_dialog(self):
        from ..export.service import capture_export
        from .quality_dialog import QualityDialog
        c = self.active_character()
        if c is None or self.service.path is None or self._import_busy:
            return
        try:
            snapshot = capture_export(c, self.service.path)
        except ValueError:
            QMessageBox.warning(self, "無法檢查", "請先備妥四方向各四幀的完整 Walk。")
            return
        self.stop_playback()
        dialog = QualityDialog(snapshot=snapshot, parent=self)
        dialog.exec()
        dialog.deleteLater()

    def show_help(self):
        from PySide6.QtWidgets import QDialog, QTextEdit
        from ..runtime import resource_path
        dialog = QDialog(self)
        dialog.setWindowTitle("快速開始")
        dialog.resize(740, 600)
        layout = QVBoxLayout(dialog)
        text = QTextEdit()
        text.setReadOnly(True)
        try:
            text.setPlainText(resource_path("docs/quickstart.txt").read_text(encoding="utf-8"))
        except OSError:
            text.setPlainText("請參閱程式資料夾內的 START_HERE.txt 或 README.md。")
        layout.addWidget(text)
        dialog.exec()
        dialog.deleteLater()

    def key_settings(self):
        from .credentials_dialog import CredentialsDialog
        session = self.ai_session()
        if session is not None:
            dialog = CredentialsDialog(session, self)
            dialog.exec()
            dialog.deleteLater()

    def ai_session(self):
        if self._ai_session is None:
            from PySide6.QtCore import QStandardPaths
            from ..ai.session import AISession
            try:
                self._ai_session = AISession(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "ai")
            except Exception:
                QMessageBox.warning(self, "AI 資料不可用", "無法開啟本機預算帳本；付費功能保持停用。")
                return None
        return self._ai_session

    def open_ai_dialog(self):
        from .ai_dialog import AIDialog
        session = self.ai_session()
        if session is not None:
            self.stop_playback()
            dialog = AIDialog(session, self)
            dialog.exec()
            dialog.deleteLater()

    def rename_project(self):
        name, ok = QInputDialog.getText(self, "專案名稱", "名稱", text=self.service.project.name)
        if ok and name.strip():
            self.service.project.name = name.strip()
            self.service.dirty = True
            self.update_title()

    def confirm_discard(self):
        if not self.service.dirty:
            return True
        answer = QMessageBox.warning(self, "未儲存變更", "是否先儲存專案？",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_project()
        return answer == QMessageBox.StandardButton.Discard

    def new_project(self):
        if self.confirm_discard():
            self.service.new()
            self.refresh()

    def open_project(self):
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "開啟專案", "", "Project JSON (*.json)")
        if not path:
            return
        try:
            self.service.load(Path(path))
            self.refresh()
            missing = self.service.repository.missing_assets(self.service.project, Path(path))
            if missing:
                QMessageBox.warning(self, "缺失素材", "\n".join(missing))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "無法開啟", str(exc))

    def save_project(self, save_as=False):
        if save_as and self._import_busy:
            QMessageBox.information(self, "正在匯入", "請等待匯入完成後再另存專案。")
            return False
        original_path = self.service.path
        path = self.service.path
        if path is None or save_as:
            selected, _ = QFileDialog.getSaveFileName(self, "儲存專案", "project.json", "Project JSON (*.json)")
            if not selected:
                return False
            path = Path(selected)
        try:
            self.service.save(path)
            self.update_title()
            if self.service.path != original_path:
                self.change_direction(self.direction.currentIndex())
            return True
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "無法儲存", str(exc))
            return False

    def closeEvent(self, event):
        if self.confirm_discard():
            self.stop_playback()
            self._epoch += 1
            event.accept()
        else:
            event.ignore()
