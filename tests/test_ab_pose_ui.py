from copy import deepcopy
from threading import Event

from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest

from test_ab_workflow import sample


def test_pose_editor_numeric_edit_reset_and_cancel(qtbot, monkeypatch):
    from anime_rpg_sprite_studio.ui.ab_pose_dialog import ABPoseDialog
    rig, assets = sample(); original = deepcopy(rig)
    dialog = ABPoseDialog(rig, assets, 0); qtbot.addWidget(dialog); dialog.show()
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    assert dialog.pose is not None
    dialog.leg.setCurrentText('A'); dialog.joint.setCurrentText('ankle')
    dialog.x.setValue(dialog.x.value() + 1)
    dialog.apply_coordinates()
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    assert 'A' in dialog.rig.frame_overrides['0']
    assert rig == original
    dialog.reset_leg()
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    assert not dialog.rig.frame_overrides
    dialog.frame.setValue(1)
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    assert dialog.index == 1
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    dialog.reject()
    assert dialog.result_rig is None


def test_pose_canvas_drag_updates_selected_frame(qtbot, monkeypatch):
    from anime_rpg_sprite_studio.ui.ab_pose_dialog import ABPoseDialog
    rig, assets = sample(); dialog = ABPoseDialog(rig, assets); qtbot.addWidget(dialog); dialog.show()
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    canvas = dialog.canvas; rect = canvas.image_rect()
    hip = dialog.pose['legs']['A']['hip']
    start = QPoint(round(rect.x()+hip[0]*rect.width()/32), round(rect.y()+hip[1]*rect.height()/32))
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=start + QPoint(8, 0))
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    assert 'A' in dialog.rig.frame_overrides['0']
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    dialog.reject()


def test_accept_returns_isolated_candidate_and_can_reopen(qtbot):
    from anime_rpg_sprite_studio.ui.ab_pose_dialog import ABPoseDialog
    rig, assets = sample(); original = deepcopy(rig)
    dialog = ABPoseDialog(rig, assets, initial_frame=3); qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    dialog.leg.setCurrentText('B'); dialog.joint.setCurrentText('toe')
    dialog.y.setValue(dialog.y.value() - 3); dialog.apply_coordinates()
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    assert dialog.rig.frame_overrides['3']['B']['foot_angle'] != 0
    dialog.accept()
    assert dialog.result_rig.frame_overrides == dialog.rig.frame_overrides
    assert rig == original
    reopened = ABPoseDialog(dialog.result_rig, assets, initial_frame=3); qtbot.addWidget(reopened)
    qtbot.waitUntil(lambda: not reopened.busy, timeout=10000)
    assert reopened.pose['legs']['B']['foot_angle'] != 0
    reopened.reject()


def test_invalid_knee_does_not_write_candidate(qtbot):
    from anime_rpg_sprite_studio.ui.ab_pose_dialog import ABPoseDialog
    rig, assets = sample(); dialog = ABPoseDialog(rig, assets); qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    hip = dialog.pose['legs']['A']['hip']
    dialog.move_joint('A', 'knee', *hip)
    assert not dialog.rig.frame_overrides and not dialog.busy
    assert '無法修改姿勢' in dialog.status.text()
    dialog.reject()


def test_accept_rejects_invalid_pending_coordinates(qtbot, monkeypatch):
    from anime_rpg_sprite_studio.ui.ab_pose_dialog import ABPoseDialog
    rig, assets = sample(); dialog = ABPoseDialog(rig, assets); qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    dialog.joint.setCurrentText('knee')
    hip = dialog.pose['legs']['A']['hip']
    dialog.x.setValue(hip[0]); dialog.y.setValue(hip[1])
    dialog.accept()
    assert dialog.result_rig is None and '無法修改姿勢' in dialog.status.text()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    dialog.reject()


def test_reject_waits_for_worker_cleanup(qtbot, monkeypatch):
    from anime_rpg_sprite_studio.ui import ab_pose_dialog
    started, release = Event(), Event()
    def delayed(worker):
        started.set(); release.wait(5)
        worker.signals.finished.emit(worker.job, None, '已取消')
    monkeypatch.setattr(ab_pose_dialog.FrameWorker, 'run', delayed)
    rig, assets = sample(); dialog = ab_pose_dialog.ABPoseDialog(rig, assets); qtbot.addWidget(dialog); dialog.show()
    qtbot.waitUntil(started.is_set, timeout=10000)
    dialog.reject()
    assert dialog.isVisible() and dialog.busy and dialog.cancel.is_set()
    release.set()
    qtbot.waitUntil(lambda: not dialog.isVisible(), timeout=10000)
    assert dialog.result_rig is None


def test_pending_invalid_coordinates_block_frame_and_joint_switch(qtbot, monkeypatch):
    from anime_rpg_sprite_studio.ui.ab_pose_dialog import ABPoseDialog
    rig, assets = sample(); dialog = ABPoseDialog(rig, assets); qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    dialog.joint.setCurrentText('knee')
    hip = dialog.pose['legs']['A']['hip']
    dialog.x.setValue(hip[0]); dialog.y.setValue(hip[1])
    dialog.frame.setValue(1)
    assert dialog.frame.value() == 0 and dialog.index == 0 and dialog.y.value() == hip[1]
    dialog.leg.setCurrentText('B')
    assert dialog.leg.currentText() == 'A' and dialog.joint.currentText() == 'knee'
    assert dialog.y.value() == hip[1]
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    dialog.reject()
