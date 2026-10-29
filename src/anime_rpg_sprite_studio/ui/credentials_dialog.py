from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton
from .ai_worker import AIWorker


class CredentialsDialog(QDialog):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._worker = None
        self._pending_close = None
        self.setWindowTitle("fal.ai 安全憑證")
        self.resize(600, 310)
        layout = QVBoxLayout(self)
        label = QLabel("Key 僅保存於 Windows Credential Manager，不存入專案或 JSON。\n"
                       "測試只查詢官方價格，不會執行生圖。價格可用一般 API 權限；\n"
                       "帳單核對需要額外讀取權限，程式不會自動擴權。")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("輸入新的 fal.ai Key（不顯示已有 Key）")
        layout.addWidget(self.key_input)
        self.save_button = QPushButton("新增／更換 Key")
        self.save_button.clicked.connect(self.save_key)
        self.test_button = QPushButton("測試已保存的 Key（只查價格）")
        self.test_button.clicked.connect(self.test_key)
        self.delete_button = QPushButton("刪除已保存的 Key")
        self.delete_button.clicked.connect(self.delete_key)
        for button in (self.save_button, self.test_button, self.delete_button):
            layout.addWidget(button)
        self.status = QLabel("尚未讀取憑證。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        close = QPushButton("關閉")
        close.clicked.connect(self.reject)
        layout.addWidget(close)

    def save_key(self):
        try:
            self.session.credentials.set_key("fal", self.key_input.text())
            self.status.setText("Key 已保存於安全後端。")
        except Exception:
            self.status.setText("無法保存 Key；未改用明文。")
        finally:
            self.key_input.clear()

    def delete_key(self):
        try:
            self.session.credentials.delete_key("fal")
            self.status.setText("已刪除本機保存的 Key；不會撤銷供應商端 Key。")
        except Exception:
            self.status.setText("無法刪除安全憑證。")
        self.key_input.clear()

    def test_key(self):
        if self._worker is not None:
            return
        self.status.setText("正在查詢官方價格；不會生圖…")
        for b in (self.save_button, self.test_button, self.delete_button):
            b.setEnabled(False)
        self._worker = AIWorker(1, "test", self.session.fal.test_key)
        self._worker.signals.finished.connect(self.test_finished)
        QThreadPool.globalInstance().start(self._worker)

    def test_finished(self, job, operation, result, error):
        self._worker = None
        self.status.setText(error or result)
        for b in (self.save_button, self.test_button, self.delete_button):
            b.setEnabled(True)
        if self._pending_close is not None:
            super().done(self._pending_close)

    def done(self, result):
        self.key_input.clear()
        if self._worker is not None:
            self._pending_close = result
            self.status.setText("等待只讀查詢完成或逾時後關閉。")
            return
        super().done(result)
