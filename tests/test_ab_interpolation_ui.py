from copy import deepcopy
from threading import Event

from PySide6.QtWidgets import QMessageBox
import pytest

from test_ab_workflow import sample


def wait(dialog, qtbot):
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)


def test_toggle_add_delete_keys_and_cancel(qtbot, monkeypatch):
    from anime_rpg_sprite_studio.ui.ab_pose_dialog import ABPoseDialog
    rig, assets = sample(); original = deepcopy(rig)
    dialog = ABPoseDialog(rig, assets); qtbot.addWidget(dialog); dialog.show(); wait(dialog, qtbot)
    assert dialog.interpolate_check.isChecked()
    assert '原步態' in dialog.key_status.text()
    dialog.add_key(); wait(dialog, qtbot)
    assert set(dialog.rig.frame_overrides['0']) == {'A'}
    assert '關鍵幀' in dialog.key_status.text()
    dialog.leg.setCurrentText('B'); dialog.add_key(); wait(dialog, qtbot)
    assert set(dialog.rig.frame_overrides['0']) == {'A', 'B'}
    dialog.reset_leg(); wait(dialog, qtbot)
    assert set(dialog.rig.frame_overrides['0']) == {'A'}
    assert '原步態' in dialog.key_status.text()
    dialog.leg.setCurrentText('A'); dialog.frame.setValue(1); wait(dialog, qtbot)
    assert '插值' in dialog.key_status.text()
    dialog.interpolate_check.setChecked(False); wait(dialog, qtbot)
    assert not dialog.rig.interpolate and dialog.dirty and '原步態' in dialog.key_status.text()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    dialog.reject()
    assert dialog.result_rig is None and rig == original


def test_interpolation_setting_saved_in_accepted_candidate(qtbot):
    from anime_rpg_sprite_studio.ui.ab_pose_dialog import ABPoseDialog
    rig, assets = sample()
    dialog = ABPoseDialog(rig, assets); qtbot.addWidget(dialog); wait(dialog, qtbot)
    dialog.interpolate_check.setChecked(False); wait(dialog, qtbot)
    dialog.accept()
    assert dialog.result_rig is not None and dialog.result_rig.interpolate is False
    assert rig.interpolate is True


def test_pending_coordinates_are_not_silently_discarded(qtbot, monkeypatch):
    from anime_rpg_sprite_studio.ui.ab_pose_dialog import ABPoseDialog
    rig, assets = sample()
    dialog = ABPoseDialog(rig, assets); qtbot.addWidget(dialog); dialog.show(); wait(dialog, qtbot)
    dialog.x.setValue(dialog.x.value() + 1)
    dialog.interpolate_check.setChecked(False)
    assert dialog.interpolate_check.isChecked() and dialog.rig.interpolate
    assert '請先套用座標' in dialog.status.text()
    dialog.add_key()
    assert not dialog.rig.frame_overrides and '請先套用座標' in dialog.status.text()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
    dialog.reject()
    assert dialog.isVisible()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    dialog.reject()


def test_interpolation_cannot_change_while_rendering(qtbot, monkeypatch):
    from anime_rpg_sprite_studio.ui import ab_pose_dialog
    started, release = Event(), Event()
    original_run = ab_pose_dialog.FrameWorker.run
    def delayed(worker):
        started.set(); release.wait(5); original_run(worker)
    monkeypatch.setattr(ab_pose_dialog.FrameWorker, 'run', delayed)
    rig, assets = sample(); dialog = ab_pose_dialog.ABPoseDialog(rig, assets)
    qtbot.addWidget(dialog); qtbot.waitUntil(started.is_set, timeout=10000)
    assert not dialog.interpolate_check.isEnabled()
    dialog.interpolate_check.setChecked(False)
    assert dialog.interpolate_check.isChecked() and dialog.rig.interpolate
    release.set(); wait(dialog, qtbot)
    assert not dialog.dirty
    dialog.reject()


def test_pin_interpolated_frame_preserves_visible_pose(qtbot, monkeypatch):
    from anime_rpg_sprite_studio.ui.ab_pose_dialog import ABPoseDialog
    rig, assets = sample(); dialog = ABPoseDialog(rig, assets)
    qtbot.addWidget(dialog); wait(dialog, qtbot)
    ankle = dialog.pose['legs']['A']['ankle']
    dialog.move_joint('A', 'ankle', ankle[0] + 1, ankle[1]); wait(dialog, qtbot)
    dialog.frame.setValue(1); wait(dialog, qtbot)
    before = deepcopy(dialog.pose['legs'])
    dialog.add_key(); wait(dialog, qtbot)
    assert 'A' in dialog.rig.frame_overrides['1'] and '關鍵幀' in dialog.key_status.text()
    for joint in ('hip', 'knee', 'ankle', 'toe'):
        assert dialog.pose['legs']['A'][joint] == pytest.approx(before['A'][joint])
        assert dialog.pose['legs']['B'][joint] == pytest.approx(before['B'][joint])
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    dialog.reject()
