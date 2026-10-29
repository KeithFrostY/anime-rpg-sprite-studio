def test_project_edit_and_direction(qtbot, tmp_path):
    from anime_rpg_sprite_studio.ui.main_window import MainWindow
    from anime_rpg_sprite_studio.core.models import Direction
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    w.add_character()
    w.name_edit.setText("魔法使")
    assert w.service.project.characters[0].name == "魔法使"
    assert w.service.dirty
    w.direction.setCurrentIndex(3)
    assert w.current_direction == Direction.BACK
    assert not w.play_button.isEnabled()
    assert not w.export_action.isEnabled()
    path = tmp_path / "project.json"
    w.service.save(path)
    assert not w.service.dirty
    w.service.load(path)
    assert w.service.project.characters[0].name == "魔法使"
    w.service.dirty = False


def test_close_cancel_preserves_changes(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from anime_rpg_sprite_studio.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    w.add_character()
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Cancel)
    assert not w.close()
    assert w.service.dirty
    w.service.dirty = False
