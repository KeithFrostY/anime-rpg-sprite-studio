from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget


class Preview(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 320)
        self.pixmap = QPixmap()
        self.previous = QPixmap()
        self.following = QPixmap()
        self.show_onion = False
        self.show_baseline = True

    def set_neighbors(self, previous, following):
        self.previous, self.following = previous, following
        self.update()

    def set_onion(self, enabled):
        self.show_onion = bool(enabled)
        self.update()

    def set_baseline(self, enabled):
        self.show_baseline = bool(enabled)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        for y in range(0, self.height(), 16):
            for x in range(0, self.width(), 16):
                painter.fillRect(x, y, 16, 16, QColor("#d0d0d0" if (x // 16 + y // 16) % 2 else "#eeeeee"))
        x, y = (self.width() - 256) // 2, (self.height() - 256) // 2
        if self.show_onion:
            painter.setOpacity(0.2)
            for neighbor in (self.previous, self.following):
                if not neighbor.isNull():
                    painter.drawPixmap(x, y, neighbor)
            painter.setOpacity(1.0)
        if not self.pixmap.isNull():
            painter.drawPixmap(x, y, self.pixmap)
        else:
            painter.setPen(QColor("#333333"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "尚無動畫素材")
        if self.show_baseline:
            painter.setPen(QPen(QColor("#d23d50"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(x, y + 255, x + 255, y + 255)
        painter.setPen(QColor("#d23d50"))
        painter.drawLine(x + 120, y + 255, x + 136, y + 255)
        painter.drawLine(x + 128, y + 247, x + 128, y + 263)
