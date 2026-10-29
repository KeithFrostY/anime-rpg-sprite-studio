from threading import Event
from PySide6.QtCore import QObject, QRunnable, Signal, QThreadPool
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTextEdit, QTableWidget, QTableWidgetItem,
    QPushButton, QAbstractItemView, QHeaderView,
)
from ..animation.quality import analyze_frames
from ..export.service import prepare_export


class QualitySignals(QObject):
    finished = Signal(object, str)


class QualityWorker(QRunnable):
    def __init__(self, snapshot, frames, cancel):
        super().__init__()
        self.snapshot, self.frames, self.cancel = snapshot, frames, cancel
        self.signals = QualitySignals()

    def run(self):
        try:
            frames = self.frames
            if self.snapshot is not None:
                bundle = prepare_export(self.snapshot, self.cancel)
                frames = {}
                for image in bundle.images:
                    frames.setdefault(image.direction, {})[image.index] = image.png
            result = analyze_frames(frames, self.cancel)
            self.signals.finished.emit(result, "")
        except Exception:
            self.signals.finished.emit(None, "檢查取消或素材無法讀取。請確認 16 幀 PNG 的尺寸、格式、路徑與檔案是否完整。")


class QualityDialog(QDialog):
    def __init__(self, snapshot=None, frames=None, parent=None):
        super().__init__(parent)
        self.busy = True
        self.report = None
        self._pending_close = None
        self._cancel = Event()
        self.setWindowTitle("16 幀一致性檢查（只讀）")
        self.resize(830, 650)
        layout = QVBoxLayout(self)
        heading = QLabel("輪廓檢查只能提示可能的抖動、背景或裁切；無法判斷角色身份或美術品質。\n不會修正或覆蓋任何圖片。")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["方向／幀", "可見邊界（左上原點）", "可見像素", "背景"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setPlainText("正在背景檢查 16 幀…")
        self.summary.setMaximumHeight(220)
        layout.addWidget(self.summary)
        close = QPushButton("關閉／取消檢查")
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self._worker = QualityWorker(snapshot, frames, self._cancel)
        self._worker.signals.finished.connect(self.work_finished)
        QThreadPool.globalInstance().start(self._worker)

    def work_finished(self, report, error):
        self.busy = False
        self._worker = None
        self.report = report
        if report is not None:
            self.table.setRowCount(len(report.frames))
            for row, item in enumerate(report.frames):
                values = [f"{item.direction.value.title()} / {item.index}", str(item.bounds) if item.bounds else "全透明",
                          str(item.visible_pixels), "完全不透明" if item.opaque else "含透明像素"]
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(value))
            self.summary.setPlainText("\n".join(w.message for w in report.warnings) if report.warnings else "未觸發輪廓警告；這不代表角色一致性或落腳品質已獲保證，仍需人工預覽。")
        else:
            self.summary.setPlainText(error)
        if self._pending_close is not None:
            super().done(self._pending_close)

    def done(self, result):
        if self.busy:
            self._pending_close = result
            self._cancel.set()
            self.summary.setPlainText("正在停止檢查…")
            return
        super().done(result)
