"""CPU-only, non-destructive mask and paint operations."""
from io import BytesIO
from math import ceil, hypot

from PIL import Image, ImageChops, ImageDraw, UnidentifiedImageError

MAX_PIXELS = 4_000_000
HISTORY_BYTES = 64 * 1024 * 1024


def _png(image):
    stream = BytesIO(); image.save(stream, format='PNG'); return stream.getvalue()


def _read(blob, mode=None):
    if not isinstance(blob, bytes) or len(blob) > 32 * 1024 * 1024:
        raise ValueError('PNG 資料缺失或過大')
    try:
        with Image.open(BytesIO(blob)) as image:
            if image.format != 'PNG' or max(image.width, image.height) > 8192 or image.width * image.height > MAX_PIXELS or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('圖片必須是單張 PNG，最多 400 萬像素及每邊 8192 像素')
            if mode == 'L' and image.mode != 'L': raise ValueError('遮罩必須是灰階 PNG')
            return image.convert(mode or 'RGBA')
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError('無法讀取 PNG') from exc


def _points(points):
    points = list(points)
    if not points: return
    yield tuple(map(int, points[0]))
    for a, b in zip(points, points[1:]):
        count = max(1, ceil(hypot(b[0]-a[0], b[1]-a[1])))
        for step in range(1, count+1):
            yield (round(a[0]+(b[0]-a[0])*step/count), round(a[1]+(b[1]-a[1])*step/count))


class PaintDocument:
    def __init__(self, source_bytes, mask_bytes=None, paint_bytes=None):
        self.source_bytes = source_bytes
        self.source = _read(source_bytes)
        self.mask = _read(mask_bytes, 'L') if mask_bytes is not None else Image.new('L', self.source.size, 255)
        self.paint = _read(paint_bytes) if paint_bytes is not None else Image.new('RGBA', self.source.size)
        if self.mask.size != self.source.size or self.paint.size != self.source.size:
            raise ValueError('遮罩及補畫尺寸必須與來源相同')
        self.limit = max(1, min(20, HISTORY_BYTES // (self.source.width * self.source.height * 5)))
        self.undo_stack, self.redo_stack = [], []
        self.dirty = False

    def _save(self):
        self.undo_stack.append((self.mask.copy(), self.paint.copy()))
        if len(self.undo_stack) > self.limit: self.undo_stack.pop(0)
        self.redo_stack.clear(); self.dirty = True

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append((self.mask.copy(), self.paint.copy()))
            self.mask, self.paint = self.undo_stack.pop(); self.dirty = True

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append((self.mask.copy(), self.paint.copy()))
            self.mask, self.paint = self.redo_stack.pop(); self.dirty = True

    def composite(self):
        base = self.source.copy()
        base.putalpha(ImageChops.multiply(base.getchannel('A'), self.mask))
        return Image.alpha_composite(base, self.paint)

    def polygon(self, points, add=True):
        if len(points) < 3: raise ValueError('多邊形至少需要三個點')
        self._save(); ImageDraw.Draw(self.mask).polygon(points, fill=255 if add else 0)

    def stroke(self, tool, points, size=10, color=(0,0,0,255)):
        if tool not in ('mask_add', 'mask_erase', 'paint', 'paint_erase') or not 1 <= size <= 512:
            raise ValueError('筆刷設定無效')
        points = list(_points(points))
        if not points: return
        self._save()
        coverage = Image.new('L', self.source.size)
        draw = ImageDraw.Draw(coverage)
        for x, y in points:
            left, top = x - (size-1)//2, y - (size-1)//2
            if size == 1: draw.point((left, top), fill=255)
            else: draw.ellipse((left, top, left+size-1, top+size-1), fill=255)
        if tool == 'mask_add': self.mask = ImageChops.lighter(self.mask, coverage)
        elif tool == 'mask_erase': self.mask = ImageChops.darker(self.mask, ImageChops.invert(coverage))
        elif tool == 'paint_erase':
            self.paint.putalpha(ImageChops.multiply(self.paint.getchannel('A'), ImageChops.invert(coverage)))
        else:
            overlay = Image.new('RGBA', self.source.size, color)
            overlay.putalpha(coverage.point(lambda value: value * color[3] // 255))
            self.paint = Image.alpha_composite(self.paint, overlay)

    def pick(self, point, sample_source=False):
        x, y = map(int, point)
        if not (0 <= x < self.source.width and 0 <= y < self.source.height): return None
        color = (self.source if sample_source else self.composite()).getpixel((x, y))
        return color if color[3] else None

    def clone(self, source_point, points, size=10, opacity=255, sample_source=False):
        points = list(_points(points))
        if not points: return
        sx, sy = map(int, source_point)
        if not (0 <= sx < self.source.width and 0 <= sy < self.source.height): raise ValueError('取樣點超出畫布')
        if not 1 <= size <= 512 or not 0 <= opacity <= 255: raise ValueError('筆刷設定無效')
        # Freeze the sample before drawing to avoid feedback and preserve original pixels.
        reference = self.source.copy() if sample_source else self.composite(); self._save()
        coverage = Image.new('L', self.source.size); draw = ImageDraw.Draw(coverage)
        offset_x, offset_y = sx - points[0][0], sy - points[0][1]
        for x, y in points:
            left, top = x - (size-1)//2, y - (size-1)//2
            if size == 1: draw.point((left, top), fill=opacity)
            else: draw.ellipse((left, top, left+size-1, top+size-1), fill=opacity)
        overlay = Image.new('RGBA', self.source.size)
        overlay.paste(reference, (-offset_x, -offset_y))
        overlay.putalpha(ImageChops.multiply(overlay.getchannel('A'), coverage))
        self.paint = Image.alpha_composite(self.paint, overlay)

    def result_bytes(self):
        return self.source_bytes, _png(self.mask), _png(self.paint), _png(self.composite())
