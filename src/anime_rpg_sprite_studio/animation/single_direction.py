"""Independent grid animation workflow; preserves input pixels and background."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from PIL import Image


def crop_boxes(image, boxes):
    if not boxes or len(boxes) > 128:
        raise ValueError('請選取 1 至 128 個切割框')
    frames = []
    for left, top, right, bottom in boxes:
        if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
            raise ValueError('切割框超出圖片')
        frames.append(image.crop((left, top, right, bottom)).convert('RGBA'))
    return frames


def normalize_frames(frames, offsets):
    if not frames or len(frames) != len(offsets):
        raise ValueError('影格或位置設定無效')
    width = max(frame.width for frame in frames)
    height = max(frame.height for frame in frames)
    positions = [((width - frame.width) // 2 + dx, height - frame.height + dy)
                 for frame, (dx, dy) in zip(frames, offsets)]
    min_x = min(0, *(x for x, _ in positions))
    min_y = min(0, *(y for _, y in positions))
    max_x = max(width, *(x + f.width for f, (x, _) in zip(frames, positions)))
    max_y = max(height, *(y + f.height for f, (_, y) in zip(frames, positions)))
    if (max_x - min_x) * (max_y - min_y) * len(frames) > 64_000_000:
        raise ValueError('輸出畫布太大，請縮小切割範圍或位移')
    result = []
    for frame, (x, y) in zip(frames, positions):
        canvas = Image.new('RGBA', (max_x - min_x, max_y - min_y))
        canvas.paste(frame.convert('RGBA'), (x - min_x, y - min_y))
        result.append(canvas)
    return result


def split_grid(image: Image.Image, columns: int, rows: int, bounds=None) -> list[Image.Image]:
    if columns < 1 or rows < 1 or columns * rows > 128:
        raise ValueError('網格數量無效（最多 128 幀）')
    left, top, right, bottom = bounds or (0, 0, image.width, image.height)
    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
        raise ValueError('切割範圍超出圖片')
    width, height = right - left, bottom - top
    if width % columns or height % rows or columns > width or rows > height:
        raise ValueError('圖片尺寸必須可以被欄數及列數整除')
    w, h = width // columns, height // rows
    rgba = image.crop((left, top, right, bottom)).convert('RGBA')
    return [rgba.crop((x*w, y*h, (x+1)*w, (y+1)*h)) for y in range(rows) for x in range(columns)]


def export_animation(frames, destination, animation, direction, fps, loop):
    if not frames or len(frames) > 128 or animation not in ('walk', 'attack') or direction not in ('front', 'left', 'right', 'back') or not 1 <= fps <= 60:
        raise ValueError('動畫設定無效')
    w, h = frames[0].size
    if any(frame.size != (w, h) for frame in frames):
        raise ValueError('所有影格尺寸必須相同')
    target = Path(destination) / f'{animation}-{uuid4().hex}'
    with TemporaryDirectory(prefix='.sprite-export-', dir=destination) as tmp:
        stage = Path(tmp) / 'output'
        stage.mkdir()
        sheet = Image.new('RGBA', (w * len(frames), h))
        entries = []
        for index, frame in enumerate(frames):
            image = frame.convert('RGBA')
            name = f'{animation}_{index:03}.png'
            image.save(stage / name)
            sheet.paste(image, (index * w, 0))
            entries.append({'file': name, 'x': index * w, 'y': 0, 'width': w, 'height': h})
        sheet.save(stage / 'sheet.png')
        (stage / 'animation.json').write_text(json.dumps({'format_version': 1, 'animation': animation, 'direction': direction, 'fps': fps, 'loop': bool(loop), 'sheet': 'sheet.png', 'frames': entries}, ensure_ascii=False, indent=2), encoding='utf-8')
        stage.rename(target)
    return target
