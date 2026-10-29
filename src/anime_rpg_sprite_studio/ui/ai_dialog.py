from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTextEdit, QSpinBox, QMessageBox, QFileDialog, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView,
)

from ..ai.contracts import GenerationRequest, JobHandle
from ..ai.fal_provider import MODEL
from .ai_worker import AIWorker
from .credentials_dialog import CredentialsDialog


class AIDialog(QDialog):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.busy = False
        self.candidate = None
        self.quote = None
        self._worker = None
        self._job = 0
        self._pending_close = None
        self.setWindowTitle("AI 候選素材 · 憑證與預算")
        self.resize(1040, 860)
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.provider = QComboBox()
        self.provider.addItems(["Mock · 離線免費", "fal.ai · FLUX.1 Schnell（付費）"])
        self.provider.currentIndexChanged.connect(self.invalidate_quote)
        controls.addWidget(self.provider)
        self.key_button = QPushButton("Key 設定")
        self.key_button.clicked.connect(self.key_settings)
        controls.addWidget(self.key_button)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2147483647)
        self.seed.valueChanged.connect(self.invalidate_quote)
        controls.addWidget(QLabel("Seed"))
        controls.addWidget(self.seed)
        layout.addLayout(controls)
        self.prompt = QTextEdit()
        self.prompt.setPlaceholderText("描述單張候選角色素材；不自動產生四方向或分層。")
        self.prompt.setMaximumHeight(100)
        self.prompt.textChanged.connect(self.invalidate_quote)
        layout.addWidget(self.prompt)
        layout.addWidget(QLabel("每次一張 256×256 PNG · AI 生圖與動畫引擎獨立 · 不自動匯入動畫幀"))
        self.budget_label = QLabel()
        layout.addWidget(self.budget_label)
        self.quote_label = QLabel("Mock 無需 Key 或網路。")
        self.quote_label.setWordWrap(True)
        layout.addWidget(self.quote_label)
        buttons = QHBoxLayout()
        self.mock_button = QPushButton("產生 Mock 候選")
        self.mock_button.clicked.connect(self.generate_mock)
        self.quote_button = QPushButton("取得官方報價（不生圖）")
        self.quote_button.clicked.connect(self.get_quote)
        self.submit_button = QPushButton("確認本次費用並提交一張")
        self.submit_button.clicked.connect(self.submit_paid)
        for b in (self.mock_button, self.quote_button, self.submit_button):
            buttons.addWidget(b)
        layout.addLayout(buttons)
        self.preview = QLabel("尚無候選素材")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(190)
        self.preview.setMaximumHeight(270)
        layout.addWidget(self.preview, 1)
        self.candidate_label = QLabel("尚無候選素材")
        self.candidate_label.setWordWrap(True)
        layout.addWidget(self.candidate_label)
        self.save_button = QPushButton("另存候選 PNG（不改動畫）")
        self.save_button.clicked.connect(self.save_candidate)
        layout.addWidget(self.save_button)
        self.history = QTableWidget(0, 7)
        self.history.setHorizontalHeaderLabels(["本機 ID", "UTC 月", "估算 USD", "保留 USD", "實際 USD", "狀態", "供應商 ID"])
        self.history.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.setMaximumHeight(180)
        self.history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.history.itemSelectionChanged.connect(self.update_controls)
        layout.addWidget(self.history)
        recovery = QHBoxLayout()
        self.recovery_buttons = []
        for text, action in (("查詢狀態", "status"), ("取得候選", "result"),
                             ("請求取消", "cancel"), ("核對帳單", "billing"), ("釋放未送出保留", "release")):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, op=action: self.recover(op))
            self.recovery_buttons.append((button, action))
            recovery.addWidget(button)
        layout.addLayout(recovery)
        warning = QLabel("每月預算 US$5，程式停止門檻 US$4.50；這不是供應商帳單硬上限。\n"
                         "未知費用保留且禁止新生成。取消不保證免費；不自動重試或切換模型。")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.status = QLabel("離線就緒。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        close = QPushButton("關閉")
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.refresh_history()

    def request(self):
        return GenerationRequest(self.prompt.toPlainText(), MODEL if self.provider.currentIndex() else "mock-placeholder", seed=self.seed.value())

    def invalidate_quote(self, *args):
        self.quote = None
        if hasattr(self, "quote_label"):
            self.quote_label.setText("參數或 Provider 已改變；付費前需重新報價。" if self.provider.currentIndex() else "Mock 無需 Key 或網路。")
            self.update_controls()

    def update_controls(self):
        if not hasattr(self, "recovery_buttons"):
            return
        fal = self.provider.currentIndex() == 1
        self.mock_button.setEnabled(not self.busy and not fal)
        self.quote_button.setEnabled(not self.busy and fal)
        self.submit_button.setEnabled(not self.busy and fal and self.quote is not None)
        self.save_button.setEnabled(not self.busy and self.candidate is not None)
        for widget in (self.provider, self.prompt, self.seed, self.key_button):
            widget.setEnabled(not self.busy)
        row = self.selected()
        for button, operation in self.recovery_buttons:
            allowed = row is not None and (row["state"] == "RESERVED" if operation == "release" else bool(row["provider_request_id"]))
            button.setEnabled(not self.busy and allowed)

    def refresh_history(self):
        rows = self.session.budget.list_requests()
        self.history.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = [row["id"][:8], row["month"], row["estimate"], row["reserved"],
                      ((row["actual"] + ("（待重核）" if row["billing_unresolved"] else "")) if row["actual"] is not None else "未決"), row["state"], row["provider_request_id"] or "尚無 ID"]
            for j, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                self.history.setItem(i, j, item)
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        summary = self.session.budget.get_month_summary(month)
        self.budget_label.setText(f"UTC {month} · 已確認 ${summary.confirmed} · 未決保留 ${summary.pending_reservations} · 安全可用 ${summary.available}")
        self.update_controls()

    def selected(self):
        row = self.history.currentRow()
        item = self.history.item(row, 0) if row >= 0 else None
        return self.session.budget.get(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def start_work(self, operation, function):
        if self.busy:
            return
        self.busy = True
        self._job += 1
        self.status.setText("正在處理；每次只提交一筆，不會自動重試…")
        self.update_controls()
        self._worker = AIWorker(self._job, operation, function)
        self._worker.signals.finished.connect(self.work_finished)
        QThreadPool.globalInstance().start(self._worker)

    def generate_mock(self):
        if self.provider.currentIndex() != 0:
            return
        request = self.request()
        self.start_work("candidate", lambda: self.session.mock.generate(request))

    def get_quote(self):
        if self.provider.currentIndex() != 1:
            return
        request = self.request()
        self.quote = None
        self.start_work("quote", lambda: self.session.fal.estimate(request))

    def submit_paid(self):
        if self.busy or self.quote is None or self.provider.currentIndex() != 1:
            return
        quote = self.quote
        request = self.request()
        try:
            self.session.budget.validate_quote(quote)
        except ValueError:
            self.invalidate_quote()
            self.status.setText("報價失效，請重新取得官方價格。")
            return
        summary = self.session.budget.get_month_summary(datetime.now(timezone.utc).strftime("%Y-%m"))
        message = (f"模型：{MODEL}\n尺寸：256×256 · 張數：1\n"
                   f"本次估算／保留：US${quote.reservation_cost}\n"
                   f"目前安全可用：US${summary.available}（提交時再次檢查）\n"
                   f"單位：{quote.pricing_unit}（保守計一整單位）\n來源：{quote.source}\n"
                   f"有效至：{quote.expires_at.isoformat()}\n"
                   "這次可能收費；確認只授權這一筆，不含重試。是否提交？")
        if QMessageBox.question(self, "明確確認本次付費請求", message,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            token = self.session.budget.confirm_quote(quote.id)
        except ValueError:
            self.invalidate_quote()
            return
        self.quote = None
        self.start_work("submit", lambda: self.session.submit(request, quote, token))

    def recover(self, operation):
        row = self.selected()
        if row is None or self.busy:
            return
        rid = row["id"]
        if operation == "release":
            try:
                self.session.budget.release_unsubmitted(rid)
            except ValueError:
                self.status.setText("狀態已變更，未釋放保留額。")
            self.refresh_history()
            return
        handle = JobHandle("fal", row["provider_request_id"], row["state"])
        if operation == "cancel" and QMessageBox.question(self, "取消原請求", "將向供應商要求取消；不代表免費，也不釋放未決額。是否繼續？") != QMessageBox.StandardButton.Yes:
            return
        actions = {"status": lambda: self.session.fal.get_status(handle),
                   "result": lambda: self.session.fal.fetch_result(handle),
                   "cancel": lambda: self.session.fal.cancel(handle),
                   "billing": lambda: self.session.fal.sync_billing(rid)}
        self.start_work("candidate" if operation == "result" else operation, actions[operation])

    def work_finished(self, job, operation, result, error):
        if job != self._job:
            return
        self.busy = False
        self._worker = None
        if error:
            self.status.setText(error)
        elif operation == "quote":
            self.quote = result
            self.quote_label.setText(f"估算／保留 US${result.reservation_cost} · 每 {result.pricing_unit} 官方單價 · 有效至 {result.expires_at.isoformat()}\n{result.source}")
            self.status.setText("官方報價已取得；尚未提交生圖。")
        elif operation == "candidate":
            self.candidate = result
            pixmap = QPixmap()
            pixmap.loadFromData(result.png)
            self.preview.setPixmap(pixmap.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.candidate_label.setText(result.label)
            self.status.setText(result.label)
        elif operation == "submit":
            self.status.setText("已提交一筆。請選取紀錄查詢狀態／取得候選；費用仍待核對。")
        elif operation == "billing":
            self.status.setText("已核對實際費用。" if result else "尚未找到逐筆帳單，保留未決額，不當作零。")
        else:
            self.status.setText(f"原請求狀態：{result.state}；不自動重新生成。")
        self.refresh_history()
        if self._pending_close is not None:
            super().done(self._pending_close)

    def key_settings(self):
        dialog = CredentialsDialog(self.session, self)
        dialog.exec()
        self.invalidate_quote()
        dialog.deleteLater()

    def save_candidate(self):
        if self.candidate is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "另存候選素材", "candidate.png", "PNG (*.png)")
        if path:
            try:
                from ..core.assets import write_asset
                write_asset(Path(path), self.candidate.png)
                self.status.setText("候選已另存；未更改動畫。")
            except OSError:
                self.status.setText("候選保存失敗。")

    def done(self, result):
        if self.busy:
            self._pending_close = result
            self.status.setText("等待目前操作完成或逾時後關閉；不會撤銷已送出的生圖或釋放未知費用。")
            return
        super().done(result)
