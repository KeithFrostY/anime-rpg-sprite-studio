from copy import deepcopy

from PySide6.QtWidgets import QDialog, QMessageBox

from anime_rpg_sprite_studio.core.project_service import ProjectService
from test_ab_workflow import sample


def test_pose_editor_returns_candidate_without_changing_project(qtbot, tmp_path, monkeypatch):
    from anime_rpg_sprite_studio.ui.ab_dialog import ABDialog
    from anime_rpg_sprite_studio.ui import ab_pose_dialog
    service = ProjectService(); c = service.add_character(); service.save(tmp_path / 'project.json')
    rig, assets = sample(); dialog = ABDialog(service, c.id); qtbot.addWidget(dialog)
    dialog.rig, dialog.assets = rig, assets
    class FakeEditor:
        def __init__(self, rig, assets, initial_frame, parent):
            self.result_rig = deepcopy(rig)
            self.result_rig.frame_overrides = {'1': {'A': {'hip':[16,8], 'ankle':[17,24], 'bend':1, 'foot_angle':0}}}
        def exec(self): return QDialog.DialogCode.Accepted
        def deleteLater(self): pass
    monkeypatch.setattr(ab_pose_dialog, 'ABPoseDialog', FakeEditor)
    dialog.open_pose_editor()
    assert c.ab_walk is None and '1' in dialog.rig.frame_overrides and dialog.candidate_dirty
    dialog.candidate_dirty = False; dialog.close()


def test_frame_count_change_requires_confirmation(qtbot, tmp_path, monkeypatch):
    from anime_rpg_sprite_studio.ui.ab_dialog import ABDialog
    service = ProjectService(); c = service.add_character(); service.save(tmp_path / 'p.json')
    rig, assets = sample(); rig.frame_overrides = {'7': {'A': {'hip':[16,8], 'ankle':[17,24], 'bend':1, 'foot_angle':0}}}
    dialog = ABDialog(service, c.id); qtbot.addWidget(dialog); dialog.rig, dialog.assets = rig, assets; dialog.load_controls()
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.StandardButton.No)
    dialog.frame_count.setValue(4)
    assert dialog.frame_count.value() == 8 and '7' in rig.frame_overrides
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.StandardButton.Yes)
    dialog.frame_count.setValue(4)
    assert rig.frame_overrides == {} and rig.settings['frames'] == 4
    dialog.candidate_dirty = False; dialog.close()
