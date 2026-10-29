"""Immutable export snapshots and transactional Windows directory publication."""
from copy import deepcopy
from dataclasses import dataclass
from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from typing import Callable
from uuid import uuid4

from PIL import Image

from ..core.models import Character, Direction, validate_asset_path
from ..rendering.sprite_import import decode_png

Progress = Callable[[int, str], None]


class ExportCancelled(ValueError):
    pass


def check_cancel(cancel: Event | None):
    if cancel is not None and cancel.is_set():
        raise ExportCancelled("已取消；未建立新的匯出資料夾。")


def report(progress: Progress | None, percent: int, message: str):
    if progress is not None:
        progress(percent, message)


@dataclass(frozen=True)
class FrameSource:
    direction: Direction
    index: int
    asset_path: str


@dataclass(frozen=True)
class ExportSnapshot:
    character_id: str
    character_name: str
    fps: int
    loop: bool
    root: Path
    sources: tuple[FrameSource, ...]


@dataclass(frozen=True)
class ExportImage:
    direction: Direction
    index: int
    png: bytes

    @property
    def filename(self):
        return f"frames/walk_{self.direction.value}_{self.index}.png"


@dataclass(frozen=True)
class ExportBundle:
    snapshot: ExportSnapshot
    images: tuple[ExportImage, ...]


def capture_export(character: Character, project_path: Path) -> ExportSnapshot:
    character = deepcopy(character)
    if not isinstance(character.name, str) or not character.name.strip():
        raise ValueError("請先填寫角色名稱")
    if not character.clips:
        raise ValueError("缺少 Walk 動畫")
    clip = character.clips[0]
    errors = clip.validate(complete=True)
    if errors:
        raise ValueError("四方向必須各有 4 幀才能匯出：\n" + "\n".join(errors))
    sources = tuple(FrameSource(direction, index, next(
        f.asset_path for f in clip.frames if f.direction == direction and f.index == index))
        for direction in Direction for index in range(4))
    return ExportSnapshot(character.id, character.name, clip.fps, clip.loop,
                          Path(project_path).resolve().parent, sources)


def prepare_export(snapshot: ExportSnapshot, cancel: Event | None = None,
                   progress: Progress | None = None) -> ExportBundle:
    images = []
    for number, source in enumerate(snapshot.sources, 1):
        check_cancel(cancel)
        validate_asset_path(source.asset_path)
        path = (snapshot.root / source.asset_path).resolve()
        if not path.is_relative_to(snapshot.root):
            raise ValueError("素材路徑超出專案目錄")
        data = decode_png(path)
        images.append(ExportImage(source.direction, source.index, data))
        report(progress, number * 100 // 16, f"驗證素材 {number}/16")
    check_cancel(cancel)
    return ExportBundle(snapshot, tuple(images))


def build_metadata(bundle: ExportBundle) -> dict:
    snapshot = bundle.snapshot
    return {
        "format": "anime-rpg-sprite-studio-walk",
        "format_version": 1,
        "character": {"id": snapshot.character_id, "name": snapshot.character_name},
        "animation": {
            "name": "Walk", "fps": snapshot.fps, "loop": snapshot.loop,
            "frames_per_direction": 4,
            "frame_duration_seconds": {"numerator": 1, "denominator": snapshot.fps},
        },
        "frame_size": {"width": 256, "height": 256},
        "pivot": {"x": 0.5, "y": 0.0, "normalized": True, "coordinate_origin": "bottom_left"},
        "sheet": {
            "file": "walk_sheet.png", "width": 1024, "height": 1024,
            "columns": 4, "rows": 4, "coordinate_origin": "top_left",
            "row_order": [direction.value for direction in Direction],
        },
        "directions": [
            {"name": direction.value, "frames": [
                {"index": index, "file": f"frames/walk_{direction.value}_{index}.png",
                 "rect": {"x": index * 256, "y": row * 256, "width": 256, "height": 256}}
                for index in range(4)]}
            for row, direction in enumerate(Direction)
        ],
    }


def write_file(path: Path, data: bytes):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def publish_directory(staging: Path, destination: Path):
    # Windows os.rename refuses ANY existing destination, including empty folders.
    # Explicit check also catches broken links and provides a useful error message.
    if os.path.lexists(destination):
        raise FileExistsError(f"匯出資料夾已存在：{destination}")
    os.rename(staging, destination)


def validate_output(root: Path, bundle: ExportBundle, metadata: dict, cancel):
    actual = json.loads((root / "animation.json").read_text(encoding="utf-8"))
    if actual != metadata:
        raise ValueError("匯出 JSON 驗證失敗")
    with Image.open(root / "walk_sheet.png") as sheet:
        sheet.load()
        if sheet.size != (1024, 1024) or sheet.mode != "RGBA":
            raise ValueError("Sprite Sheet 規格錯誤")
        for image in bundle.images:
            check_cancel(cancel)
            x, y = image.index * 256, list(Direction).index(image.direction) * 256
            with Image.open(root / image.filename) as frame:
                frame.load()
                if frame.mode != "RGBA" or frame.size != (256, 256):
                    raise ValueError("獨立 PNG 規格錯誤")
                with Image.open(BytesIO(image.png)) as source:
                    expected = source.tobytes()
                if frame.tobytes() != expected or sheet.crop((x, y, x + 256, y + 256)).tobytes() != expected:
                    raise ValueError("匯出圖片像素不一致")


def export_bundle(bundle: ExportBundle, parent: Path, cancel: Event | None = None,
                  progress: Progress | None = None) -> Path:
    check_cancel(cancel)
    parent = Path(parent).resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("請選擇現有輸出資料夾")
    if len(bundle.images) != 16 or {(i.direction, i.index) for i in bundle.images} != {
            (direction, index) for direction in Direction for index in range(4)}:
        raise ValueError("匯出需要完整 16 幀")
    destination = parent / f"walk-{uuid4().hex}"
    with TemporaryDirectory(prefix=".sprite-export-", dir=parent) as temporary:
        staging = Path(temporary)
        (staging / "frames").mkdir()
        sheet = Image.new("RGBA", (1024, 1024))
        for number, frame in enumerate(bundle.images, 1):
            check_cancel(cancel)
            write_file(staging / frame.filename, frame.png)
            with Image.open(BytesIO(frame.png)) as image:
                # No mask: preserve alpha exactly, without applying it a second time.
                sheet.paste(image, (frame.index * 256, list(Direction).index(frame.direction) * 256))
            report(progress, number * 80 // 16, f"寫入 PNG {number}/16")
        check_cancel(cancel)
        buffer = BytesIO()
        sheet.save(buffer, format="PNG")
        write_file(staging / "walk_sheet.png", buffer.getvalue())
        report(progress, 85, "Sprite Sheet 已建立")
        check_cancel(cancel)
        metadata = build_metadata(bundle)
        write_file(staging / "animation.json", json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
        report(progress, 90, "動畫 JSON 已建立，正在驗證輸出")
        validate_output(staging, bundle, metadata, cancel)
        report(progress, 99, "驗證完成，正在發布完整匯出")
        check_cancel(cancel)
        publish_directory(staging, destination)
        # Commit boundary: late cancellation must not report that published files vanished.
    return destination
