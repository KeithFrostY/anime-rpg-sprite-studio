from pathlib import Path
from PySide6.QtCore import QObject, QRunnable, Signal
from ..rendering.sprite_import import decode_png


class Signals(QObject):
    finished = Signal(object, object, str)


class SpriteWorker(QRunnable):
    def __init__(self, token, paths):
        super().__init__()
        self.token = token
        self.paths = paths
        self.signals = Signals()

    def run(self):
        try:
            images = {i: decode_png(Path(path)) for i, path in self.paths.items()}
            self.signals.finished.emit(self.token, images, "")
        except (OSError, ValueError) as exc:
            self.signals.finished.emit(self.token, {}, str(exc))
