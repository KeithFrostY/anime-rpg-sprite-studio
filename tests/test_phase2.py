from io import BytesIO
from pathlib import Path
import pytest
from PIL import Image


def png(color=(10, 20, 30, 80), size=(256, 256), mode="RGBA", fmt="PNG"):
    stream = BytesIO()
    Image.new(mode, size, color).save(stream, format=fmt)
    return stream.getvalue()


def setup_project(tmp_path):
    from anime_rpg_sprite_studio.core.project_service import ProjectService
    service = ProjectService()
    character = service.add_character()
    service.save(tmp_path / "source/project.json")
    return service, character


def test_decoder_preserves_alpha_and_converts_rgb(tmp_path):
    from anime_rpg_sprite_studio.rendering.sprite_import import decode_png
    path = tmp_path / "角色.png"
    path.write_bytes(png())
    assert Image.open(BytesIO(decode_png(path))).getpixel((0, 0)) == (10, 20, 30, 80)
    path.write_bytes(png((1, 2, 3), mode="RGB"))
    assert Image.open(BytesIO(decode_png(path))).mode == "RGBA"


@pytest.mark.parametrize("payload", [b"bad", png(size=(512, 256)), png((0, 0, 0), mode="RGB", fmt="JPEG")])
def test_decoder_rejects_invalid(tmp_path, payload):
    from anime_rpg_sprite_studio.rendering.sprite_import import decode_png
    path = tmp_path / "bad.png"
    path.write_bytes(payload)
    with pytest.raises(ValueError):
        decode_png(path)


def test_import_and_relocate(tmp_path):
    from anime_rpg_sprite_studio.core.models import Direction
    service, c = setup_project(tmp_path)
    service.import_frames(c.id, Direction.FRONT, {i: png() for i in range(4)})
    assert len(c.clips[0].frames) == 4 and service.dirty
    assert service.frame_bytes(c.id, Direction.FRONT).keys() == {0, 1, 2, 3}
    service.save(tmp_path / "destination/project.json")
    for frame in service.project.characters[0].clips[0].frames:
        assert (service.path.parent / frame.asset_path).is_file()
    service.load(service.path)
    assert len(service.frame_bytes(c.id, Direction.FRONT)) == 4


def test_failed_import_keeps_original_frames(tmp_path, monkeypatch):
    from anime_rpg_sprite_studio.core.models import Direction
    import anime_rpg_sprite_studio.core.project_service as module
    service, c = setup_project(tmp_path)
    service.import_frames(c.id, Direction.FRONT, {0: png()})
    original = list(c.clips[0].frames)
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(module, "write_asset", fail)
    with pytest.raises(OSError):
        service.import_frames(c.id, Direction.FRONT, {0: png(), 1: png()})
    assert c.clips[0].frames == original


def test_playback_and_direction_reset(qtbot, tmp_path):
    from anime_rpg_sprite_studio.ui.main_window import MainWindow
    from anime_rpg_sprite_studio.core.models import Direction
    w = MainWindow()
    qtbot.addWidget(w)
    w.add_character()
    w.service.save(tmp_path / "project.json")
    c = w.active_character()
    w.service.import_frames(c.id, Direction.FRONT, {i: png((i * 40, 20, 30, 255)) for i in range(4)})
    w.refresh()
    qtbot.waitUntil(lambda: w.play_button.isEnabled())
    w.toggle_playback()
    assert w.playback_timer.isActive()
    w.advance_frame()
    assert w.frame_index == 1
    w.fps.setValue(10)
    assert w.playback_timer.interval() == 100
    w.direction.setCurrentIndex(1)
    assert not w.playback_timer.isActive() and w.frame_index == 0
    assert not w.play_button.isEnabled()
    w.service.dirty = False


def test_save_as_failure_preserves_original_project(tmp_path, monkeypatch):
    from anime_rpg_sprite_studio.core.models import Direction
    service, c = setup_project(tmp_path)
    service.import_frames(c.id, Direction.FRONT, {0: png()})
    original_path = service.path
    original_asset = c.clips[0].frames[0].asset_path
    def fail(*args):
        raise OSError("write failure")
    monkeypatch.setattr(service.repository, "save", fail)
    with pytest.raises(OSError):
        service.save(tmp_path / "dest/project.json")
    assert service.path == original_path
    assert c.clips[0].frames[0].asset_path == original_asset
    assert not list((tmp_path / "dest").rglob("*.png"))
    assert service.dirty


def test_import_dialog_maps_four_frames(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from anime_rpg_sprite_studio.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    w.add_character()
    w.service.save(tmp_path / "project/project.json")
    paths = []
    for i in range(4):
        path = tmp_path / f"{i}.png"
        path.write_bytes(png((i * 60, 0, 0, 255)))
        paths.append(str(path))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a: (paths, ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    w.import_dialog()
    qtbot.waitUntil(lambda: w.play_button.isEnabled())
    for i, pixmap in w.frame_pixmaps.items():
        assert pixmap.toImage().pixelColor(0, 0).red() == i * 60
    assert w.template_button.isEnabled()
    w.service.dirty = False


def test_stale_worker_result_ignored(qtbot, tmp_path):
    from anime_rpg_sprite_studio.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    w.add_character()
    w.service.save(tmp_path / "project.json")
    token = (w._epoch, id(w.service.project), w.active_character().id,
             w.current_direction, str(w.service.path), "load")
    w.direction.setCurrentIndex(1)
    w.worker_finished(token, {i: png() for i in range(4)}, "")
    assert not w.frame_pixmaps and not w.play_button.isEnabled()
    w.service.dirty = False


def test_mock_does_not_replace_cached_animation_frame(qtbot, tmp_path):
    from anime_rpg_sprite_studio.ui.main_window import MainWindow
    from anime_rpg_sprite_studio.core.models import Direction
    w = MainWindow()
    qtbot.addWidget(w)
    w.add_character()
    w.service.save(tmp_path / "project.json")
    w.service.import_frames(w.active_character().id, Direction.FRONT, {i: png((255, 0, 0, 255)) for i in range(4)})
    w.refresh()
    qtbot.waitUntil(lambda: w.play_button.isEnabled())
    w.service.dirty = False
    w.show_mock()
    w.select_frame(0)
    assert w.preview.pixmap.toImage().pixelColor(0, 0).red() == 255
    assert w.preview.pixmap.toImage().pixelColor(0, 0).alpha() == 255
    w.service.dirty = False


def test_normal_save_preserves_pending_import(qtbot, tmp_path):
    from anime_rpg_sprite_studio.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    w.add_character()
    w.service.save(tmp_path / "project.json")
    token = (w._epoch, id(w.service.project), w.active_character().id,
             w.current_direction, str(w.service.path), "import")
    w._import_busy = True
    assert w.save_project()
    w.worker_finished(token, {0: png()}, "")
    assert len(w.active_character().clips[0].frames) == 1
    w.service.dirty = False
