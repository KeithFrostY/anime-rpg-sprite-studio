from threading import Event
from PySide6.QtCore import QObject, QRunnable, Signal


class AISignals(QObject):
    finished = Signal(int, str, object, str)


class AIWorker(QRunnable):
    def __init__(self, job, operation, function):
        super().__init__()
        self.job = job
        self.operation = operation
        self.function = function
        self.signals = AISignals()

    def run(self):
        try:
            result = self.function()
            self.signals.finished.emit(self.job, self.operation, result, "")
        except Exception:
            # Never expose raw server/transport/backend exception text to GUI/logs.
            self.signals.finished.emit(self.job, self.operation, None,
                "操作未完成，未自動重試。請檢查 Key、有效價格與帳本；未決費用保留。")
