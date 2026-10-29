from copy import deepcopy


def make_dialog(qtbot, tmp_path):
    from anime_rpg_sprite_studio.core.project_service import ProjectService
    from anime_rpg_sprite_studio.ui.template_dialog import TemplateDialog
    service = ProjectService()
    c = service.add_character()
    service.save(tmp_path / "project.json")
    dialog = TemplateDialog(service, c.id)
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog, service, c


def test_candidate_preview_then_apply(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    d, service, c = make_dialog(qtbot, tmp_path)
    d.load_demo()
    qtbot.waitUntil(lambda: d.generate_button.isEnabled(), timeout=10000)
    original = deepcopy(c)
    d.generate()
    qtbot.waitUntil(lambda: d.apply_button.isEnabled(), timeout=15000)
    assert c == original and not service.dirty
    d.toggle_playback()
    qtbot.waitUntil(lambda: d.frame_index != 0, timeout=1000)
    d.direction.setCurrentIndex(3)
    assert d.frame_index == 0 and not d.timer.isActive()
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    d.apply_candidate()
    assert len(c.clips[0].frames) == 16 and c.template is not None and service.dirty


def test_parameter_change_invalidates_candidate_and_cancel_preserves(qtbot, tmp_path):
    d, service, c = make_dialog(qtbot, tmp_path)
    d.load_demo()
    qtbot.waitUntil(lambda: d.generate_button.isEnabled(), timeout=10000)
    d.generate()
    qtbot.waitUntil(lambda: d.apply_button.isEnabled(), timeout=15000)
    d.arm_swing.setValue(20)
    assert d.candidate is None and not d.apply_button.isEnabled()
    d.generate()
    d.cancel_work()
    assert not d.apply_button.isEnabled()
    d.reject()
    assert c.template is None and not c.clips[0].frames and not service.dirty


def test_stale_generation_result_is_ignored(qtbot, tmp_path):
    from anime_rpg_sprite_studio.animation.templates import demo_template
    d, service, c = make_dialog(qtbot, tmp_path)
    token = d.job_id
    d.cancel_work()
    d.work_finished(token, "load", demo_template(), "")
    assert not d.generate_button.isEnabled() and d.candidate is None


def test_failed_png_import_restores_template_button(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from anime_rpg_sprite_studio.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    w.add_character()
    w.service.save(tmp_path / "project.json")
    token = (w._epoch, id(w.service.project), w.active_character().id,
             w.current_direction, str(w.service.path), "import")
    w._import_busy = True
    w.template_button.setEnabled(False)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: QMessageBox.StandardButton.Ok)
    w.service.dirty = False
    w.worker_finished(token, {}, "Bad PNG")
    assert w.template_button.isEnabled()


def test_saved_template_loads_and_failed_load_keeps_it(qtbot, tmp_path):
    from anime_rpg_sprite_studio.core.project_service import ProjectService
    from anime_rpg_sprite_studio.animation.templates import demo_template
    from anime_rpg_sprite_studio.ui.template_dialog import TemplateDialog
    from anime_rpg_sprite_studio.core.models import Direction
    service = ProjectService()
    c = service.add_character()
    service.save(tmp_path / "project.json")
    template, assets = demo_template()
    template.parameters.arm_swing = 17
    one_image = next(iter(assets.values()))
    frames = {direction: {i: one_image for i in range(4)} for direction in Direction}
    service.apply_walk(c.id, template, assets, frames)
    service.save(service.path)
    dialog = TemplateDialog(service, c.id)
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: dialog.generate_button.isEnabled(), timeout=10000)
    assert dialog.arm_swing.value() == 17
    original = deepcopy(c)
    dialog.start_work("load", tmp_path / "missing.json")
    qtbot.waitUntil(lambda: not dialog._busy, timeout=10000)
    assert c == original and dialog.generate_button.isEnabled()
    dialog.reject()
