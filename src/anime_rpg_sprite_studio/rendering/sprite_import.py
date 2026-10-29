"""CPU PNG validation; returns detached, normalized bytes, never Qt objects."""
from io import BytesIO
from pathlib import Path
from PIL import Image, UnidentifiedImageError

MAX_FILE_BYTES = 8 * 1024 * 1024


def decode_png(path: Path) -> bytes:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("PNG 檔案不可超過 8 MiB")
    return normalize_png(path.read_bytes())


def normalize_png(data: bytes) -> bytes:
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("PNG 檔案不可超過 8 MiB")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format != "PNG" or source.size != (256, 256) or getattr(source, "n_frames", 1) != 1:
                raise ValueError("必須是單幀 256×256 PNG；不會自動縮放")
            source.load()
            image = source.convert("RGBA")
            output = BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("無法解碼 PNG 圖片") from exc
