from threading import Event
from PySide6.QtCore import QObject, QRunnable, Signal

from ..export.service import prepare_export, export_bundle, ExportCancelled


class ExportSignals(QObject):
    progress = Signal(int, int, str)
    finished = Signal(int, str, object, str, bool)


class ExportWorker(QRunnable):
    def __init__(self, job_id, operation, payload, cancel: Event):
        super().__init__()
        self.job_id = job_id
        self.operation = operation
        self.payload = payload
        self.cancel = cancel
        self.signals = ExportSignals()

    def run(self):
        def progress(percent, message):
            self.signals.progress.emit(self.job_id, percent, message)
        try:
            if self.operation == "prepare":
                result = prepare_export(self.payload, self.cancel, progress)
            elif self.operation == "export":
                result = export_bundle(*self.payload, self.cancel, progress)
            else:
                raise ValueError("Unknown export operation")
            # No late cancel check: a successfully published export stays successful.
            self.signals.finished.emit(self.job_id, self.operation, result, "", False)
        except ExportCancelled as exc:
            self.signals.finished.emit(self.job_id, self.operation, None, str(exc), True)
        except Exception as exc:
            self.signals.finished.emit(self.job_id, self.operation, None, str(exc), False)
