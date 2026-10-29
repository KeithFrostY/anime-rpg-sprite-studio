from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from threading import Event

import pytest
from PIL import Image


@pytest.fixture
def export_source(tmp_path):
    from anime_rpg_sprite_studio.core.project_service import ProjectService
    from anime_rpg_sprite_studio.core.models import Direction
    service = ProjectService()
    c = service.add_character()
    c.name = "角色 / 測試"
    c.clips[0].fps = 12
    c.clips[0].loop = False
    service.save(tmp_path / "project/project.json")
    for row, direction in enumerate(Direction):
        images = {}
        for i in range(4):
            image = Image.new("RGBA", (256, 256), (row * 50, i * 50, 120, 80 + i))
            stream = BytesIO()
            image.save(stream, format="PNG")
            images[i] = stream.getvalue()
        service.import_frames(c.id, direction, images)
    return service, c


def test_export_pixels_metadata_and_source_unchanged(export_source, tmp_path):
    from anime_rpg_sprite_studio.export.service import capture_export, prepare_export, export_bundle
    service, c = export_source
    before = deepcopy(service.project)
    snapshot = capture_export(c, service.path)
    ready = prepare_export(snapshot)
    parent = tmp_path / "output"
    parent.mkdir()
    result = export_bundle(ready, parent)
    files = list(result.rglob("*.*"))
    assert len(files) == 18
    metadata = json.loads((result / "animation.json").read_text(encoding="utf-8"))
    assert metadata["format_version"] == 1
    assert metadata["animation"]["fps"] == 12
    assert metadata["animation"]["loop"] is False
    assert metadata["animation"]["frame_duration_seconds"] == {"numerator": 1, "denominator": 12}
    assert metadata["pivot"] == {"x": 0.5, "y": 0.0, "normalized": True, "coordinate_origin": "bottom_left"}
    assert metadata["sheet"]["coordinate_origin"] == "top_left"
    with Image.open(result / "walk_sheet.png") as sheet:
        assert sheet.size == (1024, 1024) and sheet.mode == "RGBA"
        for row, direction in enumerate(metadata["directions"]):
            for i, frame in enumerate(direction["frames"]):
                assert frame["rect"] == {"x": i * 256, "y": row * 256, "width": 256, "height": 256}
                with Image.open(result / frame["file"]) as image:
                    assert image.mode == "RGBA" and image.size == (256, 256)
                    assert image.tobytes() == sheet.crop((i * 256, row * 256, (i + 1) * 256, (row + 1) * 256)).tobytes()
                    assert image.getpixel((0, 0)) == (row * 50, i * 50, 120, 80 + i)
    assert service.project == before and service.dirty
    text = (result / "animation.json").read_text(encoding="utf-8")
    assert str(service.path) not in text and "asset_path" not in text


@pytest.mark.parametrize("problem", ["missing", "corrupt", "size", "escape"])
def test_prepare_rejects_bad_source(export_source, problem):
    from anime_rpg_sprite_studio.export.service import capture_export, prepare_export
    service, c = export_source
    frame = c.clips[0].frames[0]
    path = service.path.parent / frame.asset_path
    if problem == "missing":
        path.unlink()
    elif problem == "corrupt":
        path.write_bytes(b"bad")
    elif problem == "size":
        Image.new("RGBA", (128, 256)).save(path)
    else:
        frame.asset_path = "../secret.png"
    with pytest.raises((ValueError, OSError)):
        prepare_export(capture_export(c, service.path))


def test_capture_rejects_incomplete_and_freezes_metadata(export_source):
    from anime_rpg_sprite_studio.export.service import capture_export, prepare_export
    service, c = export_source
    snapshot = capture_export(c, service.path)
    c.name = "changed"
    c.clips[0].fps = 30
    ready = prepare_export(snapshot)
    assert ready.snapshot.character_name == "角色 / 測試" and ready.snapshot.fps == 12
    c.clips[0].frames.pop()
    with pytest.raises(ValueError):
        capture_export(c, service.path)


def test_cancel_before_and_during_export(export_source, tmp_path):
    from anime_rpg_sprite_studio.export.service import capture_export, prepare_export, export_bundle, ExportCancelled
    service, c = export_source
    ready = prepare_export(capture_export(c, service.path))
    parent = tmp_path / "exports"
    parent.mkdir()
    sentinel = parent / "keep.txt"
    sentinel.write_text("keep")
    cancel = Event()
    cancel.set()
    with pytest.raises(ExportCancelled):
        export_bundle(ready, parent, cancel)
    cancel.clear()
    def progress(percent, message):
        if percent >= 20:
            cancel.set()
    with pytest.raises(ExportCancelled):
        export_bundle(ready, parent, cancel, progress)
    assert list(parent.iterdir()) == [sentinel]


@pytest.mark.parametrize("failure", ["write", "rename"])
def test_failure_cleans_staging_preserves_existing(export_source, tmp_path, monkeypatch, failure):
    import anime_rpg_sprite_studio.export.service as module
    service, c = export_source
    ready = module.prepare_export(module.capture_export(c, service.path))
    parent = tmp_path / "exports"
    parent.mkdir()
    previous = module.export_bundle(ready, parent)
    saved = {p.relative_to(previous): p.read_bytes() for p in previous.rglob("*") if p.is_file()}
    def fail(*args, **kwargs):
        raise OSError("disk failed")
    monkeypatch.setattr(module, "write_file" if failure == "write" else "publish_directory", fail)
    with pytest.raises(OSError):
        module.export_bundle(ready, parent)
    assert list(parent.iterdir()) == [previous]
    assert saved == {p.relative_to(previous): p.read_bytes() for p in previous.rglob("*") if p.is_file()}


def test_existing_publish_destination_is_never_replaced(tmp_path):
    from anime_rpg_sprite_studio.export.service import publish_directory
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "a.txt").write_text("new")
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        publish_directory(staging, existing)
    assert staging.exists() and list(existing.iterdir()) == []


def test_cancellation_after_publication_reports_success(export_source, tmp_path, monkeypatch):
    import anime_rpg_sprite_studio.export.service as module
    service, c = export_source
    ready = module.prepare_export(module.capture_export(c, service.path))
    cancel = Event()
    original = module.publish_directory
    def publish_then_cancel(source, dest):
        original(source, dest)
        cancel.set()
    monkeypatch.setattr(module, "publish_directory", publish_then_cancel)
    result = module.export_bundle(ready, tmp_path, cancel)
    assert result.is_dir() and (result / "animation.json").is_file()
