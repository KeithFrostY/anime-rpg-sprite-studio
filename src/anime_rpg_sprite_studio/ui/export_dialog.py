from pathlib import Path
from threading import Event

from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QProgressBar, QFileDialog,
)

from .export_worker import ExportWorker


class ExportDialog(QDialog):
    """Export is prepared and published in background; closing waits for settlement."""
    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self.snapshot = snapshot
        self.ready = None
        self.result_path = None
        self.busy = False
        self._job_id = 0
        self._worker = None
        self._cancel = Event()
        self._pending_close = None
        self.setWindowTitle("匯出 PNG／Sprite Sheet／JSON")
        self.resize(680, 410)
        layout = QVBoxLayout(self)
        title = QLabel(f"角色：{snapshot.character_name}")
        title.setWordWrap(True)
        layout.addWidget(title)
        summary = QLabel(
            f"Walk · {snapshot.fps} FPS · {'循環' if snapshot.loop else '不循環'}\n"
            "16 張 256×256 RGBA PNG\n"
            "1 張 1024×1024 RGBA Sprite Sheet\n"
            "1 份動畫 JSON（方向、幀順序、FPS、矩形、腳底 Pivot）\n"
            "Sheet 由上至下：Front、Left、Right、Back；每列幀 0–3。")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        layout.addWidget(QLabel("輸出至下列位置的新 walk-… 資料夾；保留既有匯出。"))
        folder = QHBoxLayout()
        self.folder_edit = QLineEdit(str(snapshot.root))
        self.folder_edit.setReadOnly(True)
        self.folder_edit.textChanged.connect(self.update_controls)
        self.browse_button = QPushButton("選擇資料夾…")
        self.browse_button.clicked.connect(self.choose_parent)
        folder.addWidget(self.folder_edit)
        folder.addWidget(self.browse_button)
        layout.addLayout(folder)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.status = QLabel("正在驗證全部素材…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.revalidate_button = QPushButton("重新驗證")
        self.revalidate_button.clicked.connect(self.start_prepare)
        self.export_button = QPushButton("匯出全部檔案")
        self.export_button.clicked.connect(self.start_export)
        self.cancel_button = QPushButton("取消工作")
        self.cancel_button.clicked.connect(self.cancel_work)
        self.open_button = QPushButton("開啟輸出資料夾")
        self.open_button.clicked.connect(self.open_output)
        for button in (self.revalidate_button, self.export_button, self.cancel_button, self.open_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        close = QPushButton("關閉")
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.start_prepare()

    def update_controls(self, *args):
        if not hasattr(self, "export_button"):
            return
        self.export_button.setEnabled(not self.busy and self.ready is not None)
        self.cancel_button.setEnabled(self.busy and not self._cancel.is_set())
        self.browse_button.setEnabled(not self.busy)
        self.revalidate_button.setEnabled(not self.busy)
        self.open_button.setEnabled(not self.busy and self.result_path is not None)

    def choose_parent(self):
        path = QFileDialog.getExistingDirectory(self, "選擇輸出資料夾", self.folder_edit.text())
        if path:
            self.folder_edit.setText(path)

    def start_prepare(self):
        if self.busy:
            return
        self.ready = None
        self.start_worker("prepare", self.snapshot)

    def start_export(self):
        if self.busy or self.ready is None:
            return
        self.start_worker("export", (self.ready, Path(self.folder_edit.text())))

    def start_worker(self, operation, payload):
        self.busy = True
        self._job_id += 1
        self._cancel = Event()
        self.progress.setValue(0)
        self.status.setText("正在驗證全部 16 幀…" if operation == "prepare" else "正在背景建立完整匯出…")
        self.update_controls()
        worker = ExportWorker(self._job_id, operation, payload, self._cancel)
        self._worker = worker
        worker.signals.progress.connect(self.work_progress)
        worker.signals.finished.connect(self.work_finished)
        QThreadPool.globalInstance().start(worker)

    def work_progress(self, job_id, percent, message):
        if job_id != self._job_id or self._cancel.is_set():
            return
        self.progress.setValue(percent)
        self.status.setText(message)

    def work_finished(self, job_id, operation, result, error, cancelled):
        if job_id != self._job_id:
            return
        self.busy = False
        self._worker = None
        if error:
            self.progress.setValue(0)
            self.status.setText("已取消，原專案與既有匯出保留。" if cancelled else f"工作失敗，原專案與既有匯出保留：{error}")
        elif operation == "prepare":
            self.ready = result
            self.progress.setValue(100)
            self.status.setText("16 幀驗證通過，可匯出。使用目前角色與 FPS 的快照，不會儲存或修改專案。")
        else:
            self.result_path = result
            self.progress.setValue(100)
            self.status.setText(f"已完成：16 張 PNG、Sprite Sheet、動畫 JSON\n{result}")
        self.update_controls()
        if self._pending_close is not None:
            code = self._pending_close
            self._pending_close = None
            super().done(code)

    def cancel_work(self):
        if self.busy:
            self._cancel.set()
            self.status.setText("正在取消並清理暫存檔；若完整匯出已發布，會回報完成。")
            self.update_controls()

    def open_output(self):
        if self.result_path is not None and not self.busy:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result_path))):
                self.status.setText(f"無法開啟資料夾，請手動前往：{self.result_path}")

    def done(self, result):
        if self.busy:
            self._pending_close = result
            self.cancel_work()
            return
        super().done(result)
