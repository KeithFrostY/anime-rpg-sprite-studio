from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QWidget


class CropEditor(QWidget):
    changed = Signal()
    selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(240)
        self.image = None
        self.boxes = []
        self.current = -1
        self.mode = None
        self.origin = None
        self.original = None
        self.draw_new = False
        self.cursor_point = None

    def set_image(self, image):
        self.image = image
        self.boxes = []
        self.current = -1
        self.update()

    def geometry_for_image(self):
        if not self.image:
            return QRectF()
        scale = min(self.width() / self.image.width(), self.height() / self.image.height())
        w, h = self.image.width() * scale, self.image.height() * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def source_point(self, position):
        rect = self.geometry_for_image()
        return QPointF(max(0, min(self.image.width(), (position.x() - rect.x()) * self.image.width() / rect.width())),
                       max(0, min(self.image.height(), (position.y() - rect.y()) * self.image.height() / rect.height())))

    def paintEvent(self, event):
        painter = QPainter(self)
        if not self.image: return
        rect = self.geometry_for_image()
        painter.drawPixmap(rect, self.image, QRectF(self.image.rect()))
        sx, sy = rect.width() / self.image.width(), rect.height() / self.image.height()
        for i, (left, top, right, bottom) in enumerate(self.boxes):
            box = QRectF(rect.x() + left * sx, rect.y() + top * sy, (right-left)*sx, (bottom-top)*sy)
            painter.setPen(QPen(QColor('yellow' if i == self.current else 'red'), 2))
            painter.drawRect(box)
            painter.drawText(box.topLeft() + QPointF(3, 14), str(i + 1))
            if i == self.current:
                painter.fillRect(QRectF(box.right()-5, box.bottom()-5, 10, 10), QColor('yellow'))
        if self.mode == 'draw' and self.cursor_point is not None:
            a, b = self.origin, self.cursor_point
            painter.setPen(QPen(QColor('cyan'), 2, Qt.PenStyle.DashLine))
            painter.drawRect(QRectF(QPointF(rect.x()+a.x()*sx, rect.y()+a.y()*sy),
                                    QPointF(rect.x()+b.x()*sx, rect.y()+b.y()*sy)).normalized())

    def mousePressEvent(self, event):
        if not self.image or event.button() != Qt.MouseButton.LeftButton or not self.geometry_for_image().contains(event.position()): return
        p = self.source_point(event.position())
        self.origin = p
        if self.draw_new:
            self.draw_new = False
            if len(self.boxes) < 128: self.mode = 'draw'
            return
        if self.current >= 0:
            l, t, r, b = self.boxes[self.current]
            scale = self.geometry_for_image().width() / self.image.width()
            if abs(p.x()-r)*scale <= 10 and abs(p.y()-b)*scale <= 10:
                self.mode, self.original = 'resize', self.boxes[self.current]
                return
        for i in reversed(range(len(self.boxes))):
            l, t, r, b = self.boxes[i]
            if l <= p.x() <= r and t <= p.y() <= b:
                self.current = i; self.selected.emit(i)
                self.mode, self.original = 'move', self.boxes[i]
                self.update(); return
        if len(self.boxes) >= 128: return
        self.mode = 'draw'

    def mouseMoveEvent(self, event):
        if self.mode == 'draw' and self.image:
            self.cursor_point = self.source_point(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        if not self.mode or not self.image: return
        p = self.source_point(event.position())
        if self.mode == 'draw':
            l, r = sorted((round(self.origin.x()), round(p.x())))
            t, b = sorted((round(self.origin.y()), round(p.y())))
            if r > l and b > t:
                self.boxes.append((l, t, r, b)); self.current = len(self.boxes)-1
                self.changed.emit(); self.selected.emit(self.current)
        else:
            l, t, r, b = self.original
            if self.mode == 'move':
                dx = max(-l, min(self.image.width()-r, round(p.x()-self.origin.x())))
                dy = max(-t, min(self.image.height()-b, round(p.y()-self.origin.y())))
                self.boxes[self.current] = (l+dx, t+dy, r+dx, b+dy)
            else:
                self.boxes[self.current] = (l, t, max(l+1, round(p.x())), max(t+1, round(p.y())))
            self.changed.emit()
        self.mode = None
        self.cursor_point = None
        self.update()
