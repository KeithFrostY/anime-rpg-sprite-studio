from copy import deepcopy
from io import BytesIO
from threading import Event

from PIL import Image


def source(tmp_path):
    from anime_rpg_sprite_studio.core.project_service import ProjectService
    from anime_rpg_sprite_studio.core.models import Direction
    service = ProjectService()
    c = service.add_character()
    service.save(tmp_path / "project.json")
    stream = BytesIO()
    Image.new("RGBA", (256, 256), (60, 80, 100, 90)).save(stream, format="PNG")
    for direction in Direction:
        service.import_frames(c.id, direction, {i: stream.getvalue() for i in range(4)})
    return service, c


def test_dialog_validates_exports_and_opens_on_click(qtbot, tmp_path, monkeypatch):
    from anime_rpg_sprite_studio.export.service import capture_export
    from anime_rpg_sprite_studio.ui.export_dialog import ExportDialog
    from PySide6.QtGui import QDesktopServices
    service, c = source(tmp_path)
    original = deepcopy(service.project)
    d = ExportDialog(capture_export(c, service.path))
    qtbot.addWidget(d)
    d.show()
    assert not d.export_button.isEnabled()
    qtbot.waitUntil(lambda: d.export_button.isEnabled(), timeout=10000)
    assert d.ready is not None and not d.open_button.isEnabled()
    d.start_export()
    qtbot.waitUntil(lambda: not d.busy, timeout=10000)
    assert d.result_path is not None and d.progress.value() == 100
    assert len(list(d.result_path.rglob("*.png"))) == 17
    assert service.project == original
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    assert opened == []
    d.open_output()
    assert opened[0].toLocalFile().replace("\\", "/") == d.result_path.as_posix()
    d.reject()


def test_invalid_source_never_enables_export(qtbot, tmp_path):
    from anime_rpg_sprite_studio.export.service import capture_export
    from anime_rpg_sprite_studio.ui.export_dialog import ExportDialog
    service, c = source(tmp_path)
    (service.path.parent / c.clips[0].frames[0].asset_path).write_bytes(b"bad")
    d = ExportDialog(capture_export(c, service.path))
    qtbot.addWidget(d)
    qtbot.waitUntil(lambda: not d.busy, timeout=10000)
    assert not d.export_button.isEnabled() and d.ready is None
    d.reject()


def test_close_during_work_waits_for_cancellation(qtbot, tmp_path, monkeypatch):
    from anime_rpg_sprite_studio.export.service import capture_export, ExportCancelled
    from anime_rpg_sprite_studio.ui.export_dialog import ExportDialog
    import anime_rpg_sprite_studio.ui.export_worker as module
    started = Event()
    def wait_for_cancel(snapshot, cancel, progress):
        started.set()
        cancel.wait(5)
        raise ExportCancelled("cancelled")
    monkeypatch.setattr(module, "prepare_export", wait_for_cancel)
    service, c = source(tmp_path)
    d = ExportDialog(capture_export(c, service.path))
    qtbot.addWidget(d)
    d.show()
    qtbot.waitUntil(started.is_set)
    d.reject()
    qtbot.waitUntil(lambda: not d.busy and not d.isVisible(), timeout=10000)
    assert d.result_path is None and not list(tmp_path.glob("walk-*"))


def test_main_export_action_requires_complete_saved_clip(qtbot, tmp_path):
    from anime_rpg_sprite_studio.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    assert not w.export_action.isEnabled()
    w.service, c = source(tmp_path)
    w.refresh()
    w.service.dirty = False
    assert w.export_action.isEnabled()
    w._import_busy = True
    w.update_export_action()
    assert not w.export_action.isEnabled()


def test_close_after_commit_still_receives_completed_result(qtbot, tmp_path, monkeypatch):
    from anime_rpg_sprite_studio.export.service import capture_export
    from anime_rpg_sprite_studio.ui.export_dialog import ExportDialog
    import anime_rpg_sprite_studio.ui.export_worker as module
    published, release = Event(), Event()
    export = module.export_bundle
    def pause_after_commit(bundle, parent, cancel, progress):
        result = export(bundle, parent, cancel, progress)
        published.set()
        release.wait(5)
        return result
    monkeypatch.setattr(module, "export_bundle", pause_after_commit)
    service, c = source(tmp_path)
    d = ExportDialog(capture_export(c, service.path))
    qtbot.addWidget(d)
    d.show()
    qtbot.waitUntil(lambda: d.export_button.isEnabled(), timeout=10000)
    d.start_export()
    qtbot.waitUntil(published.is_set, timeout=10000)
    d.reject()
    release.set()
    qtbot.waitUntil(lambda: not d.busy and not d.isVisible(), timeout=10000)
    assert d.result_path.is_dir() and d.progress.value() == 100
