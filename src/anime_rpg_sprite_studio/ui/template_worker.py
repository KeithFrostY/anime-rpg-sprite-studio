from threading import Event
from PySide6.QtCore import QObject, QRunnable, Signal
from ..animation.templates import demo_template, load_template, load_template_assets, check_cancel
from ..animation.walk import generate_walk


class TemplateSignals(QObject):
    finished = Signal(int, str, object, str)


class TemplateWorker(QRunnable):
    def __init__(self, job_id, operation, payload, cancel: Event):
        super().__init__()
        self.job_id = job_id
        self.operation = operation
        self.payload = payload
        self.cancel = cancel
        self.signals = TemplateSignals()

    def run(self):
        try:
            check_cancel(self.cancel)
            if self.operation == "demo":
                result = demo_template()
            elif self.operation == "load":
                result = load_template(self.payload, self.cancel)
            elif self.operation == "project":
                result = load_template_assets(*self.payload, self.cancel)
            elif self.operation == "generate":
                result = generate_walk(*self.payload, self.cancel)
            else:
                raise ValueError("Unknown template operation")
            check_cancel(self.cancel)
            self.signals.finished.emit(self.job_id, self.operation, result, "")
        except Exception as exc:
            # All errors returned to UI; workers never modify a project or log secrets.
            self.signals.finished.emit(self.job_id, self.operation, None, str(exc))
