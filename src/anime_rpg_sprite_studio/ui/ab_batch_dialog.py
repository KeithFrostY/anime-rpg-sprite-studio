from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QProgressBar, QFileDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView)

from ..export.ab_batch import capture_batch, export_batch


class BatchSignals(QObject):
    progress = Signal(int, int, str)
    result = Signal(int, object)
    finished = Signal(str)


class BatchWorker(QRunnable):
    def __init__(self, snapshot, destination, cancel):
        super().__init__(); self.snapshot = snapshot; self.destination = destination; self.cancel = cancel
        self.signals = BatchSignals()

    def run(self):
        try:
            export_batch(self.snapshot, self.destination, self.cancel,
                         self.signals.progress.emit, self.signals.result.emit)
            self.signals.finished.emit('')
        except Exception as exc:
            self.signals.finished.emit(str(exc))


class ABBatchDialog(QDialog):
    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service; self.busy = False; self.worker = None
        self.cancel = Event(); self.rows = []; self.pending_close = None
        self.setWindowTitle('A／B 多角色批量輸出'); self.resize(820, 540)
        layout = QVBoxLayout(self)
        label = QLabel('勾選角色。使用目前已套用的 A/B 設定；未套用的編輯器候選不會輸出。每個角色獨立建立資料夾。')
        label.setWordWrap(True); layout.addWidget(label)
        self.table = QTableWidget(len(service.project.characters), 3)
        self.table.setHorizontalHeaderLabels(['角色（勾選）', '狀態', '輸出位置／錯誤'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for row, character in enumerate(service.project.characters):
            item = QTableWidgetItem(character.name); item.setData(Qt.ItemDataRole.UserRole, character.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if character.ab_walk is not None else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, item)
            self.table.setItem(row, 1, QTableWidgetItem('等待' if character.ab_walk else '沒有 A/B 設定'))
            self.table.setItem(row, 2, QTableWidgetItem(''))
        layout.addWidget(self.table)
        folder = QHBoxLayout(); self.destination = QLineEdit(str(service.path.parent) if service.path else '')
        self.destination.setReadOnly(True); folder.addWidget(self.destination)
        self.browse = QPushButton('選擇資料夾…'); self.browse.clicked.connect(self.choose_folder); folder.addWidget(self.browse)
        layout.addLayout(folder)
        self.progress = QProgressBar(); self.progress.setRange(0, 100); layout.addWidget(self.progress)
        self.status = QLabel('尚未開始'); self.status.setWordWrap(True); layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.start = QPushButton('開始批量輸出'); self.start.clicked.connect(self.start_export); actions.addWidget(self.start)
        self.cancel_button = QPushButton('取消'); self.cancel_button.clicked.connect(self.cancel_work); self.cancel_button.setEnabled(False); actions.addWidget(self.cancel_button)
        close = QPushButton('關閉'); close.clicked.connect(self.reject); actions.addWidget(close)
        layout.addLayout(actions)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, '選擇輸出資料夾', self.destination.text())
        if path: self.destination.setText(path)

    def start_export(self):
        if self.busy: return
        self.rows = [row for row in range(self.table.rowCount()) if self.table.item(row, 0).checkState() == Qt.CheckState.Checked]
        try:
            snapshot = capture_batch(self.service, [self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) for row in self.rows])
            destination = Path(self.destination.text())
            if not destination.is_dir(): raise ValueError('請選擇有效輸出資料夾')
        except ValueError as exc:
            self.status.setText(str(exc)); return
        for row in self.rows:
            self.table.item(row, 1).setText('等待'); self.table.item(row, 2).setText('')
        self.cancel = Event(); self.busy = True; self.progress.setValue(0)
        self.start.setEnabled(False); self.browse.setEnabled(False); self.table.setEnabled(False); self.cancel_button.setEnabled(True)
        self.worker = BatchWorker(snapshot, destination, self.cancel)
        self.worker.signals.progress.connect(self.work_progress)
        self.worker.signals.result.connect(self.work_result)
        self.worker.signals.finished.connect(self.work_finished)
        QThreadPool.globalInstance().start(self.worker)

    def work_progress(self, percent, index, message):
        self.progress.setValue(percent)
        self.status.setText(f'角色 {index + 1}/{len(self.rows)}：{message}')

    def work_result(self, index, result):
        row = self.rows[index]
        self.table.item(row, 1).setText({'success':'成功', 'failed':'失敗', 'cancelled':'已取消'}[result.status])
        self.table.item(row, 2).setText(str(result.output) if result.output else result.message)

    def work_finished(self, error):
        self.busy = False; self.worker = None
        self.start.setEnabled(True); self.browse.setEnabled(True); self.table.setEnabled(True); self.cancel_button.setEnabled(False)
        self.status.setText(f'批量工作失敗：{error}' if error else '批量工作已結束；請查看每個角色的結果。')
        if self.pending_close is not None:
            result = self.pending_close; self.pending_close = None; super().done(result)

    def cancel_work(self):
        if self.busy:
            self.cancel.set(); self.cancel_button.setEnabled(False)
            self.status.setText('正在取消；已完成的角色會保留，未完成的角色會標示取消。')

    def done(self, result):
        if self.busy:
            self.pending_close = result; self.cancel_work(); return
        super().done(result)
