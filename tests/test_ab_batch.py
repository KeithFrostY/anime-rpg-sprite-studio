from threading import Event

from test_ab_workflow import sample
from anime_rpg_sprite_studio.core.project_service import ProjectService


def test_batch_reports_each_character_and_continues_after_failure(tmp_path):
    from anime_rpg_sprite_studio.export.ab_batch import capture_batch, export_batch
    service = ProjectService(); good = service.add_character(); good.name = '完成角色'
    service.save(tmp_path / 'p.json'); rig, assets = sample(); service.apply_ab_walk(good.id, rig, assets)
    bad = service.add_character(); bad.name = '缺少骨架'
    destination = tmp_path / 'exports'; destination.mkdir()
    progress = []
    results = export_batch(capture_batch(service, [bad.id, good.id]), destination, progress=lambda *p: progress.append(p))
    assert [r.status for r in results] == ['failed', 'success']
    assert results[1].output.joinpath('animation.json').is_file()
    assert progress[-1][0] == 100


def test_batch_cancel_marks_unfinished_and_keeps_completed(tmp_path):
    from anime_rpg_sprite_studio.export.ab_batch import capture_batch, export_batch
    service = ProjectService(); first = service.add_character(); service.save(tmp_path / 'p.json')
    rig, assets = sample(); service.apply_ab_walk(first.id, rig, assets)
    second = service.add_character(); service.apply_ab_walk(second.id, rig, assets)
    destination = tmp_path / 'exports'; destination.mkdir(); cancel = Event()
    def progress(percent, *args):
        if percent >= 50: cancel.set()
    results = export_batch(capture_batch(service, [first.id, second.id]), destination, cancel, progress)
    assert [r.status for r in results] == ['success', 'cancelled']
    assert results[0].output.is_dir()


def test_batch_dialog_reports_results(qtbot, tmp_path):
    from anime_rpg_sprite_studio.ui.ab_batch_dialog import ABBatchDialog
    service = ProjectService(); c = service.add_character(); service.save(tmp_path / 'p.json')
    rig, assets = sample(); service.apply_ab_walk(c.id, rig, assets)
    dialog = ABBatchDialog(service); qtbot.addWidget(dialog)
    dialog.destination.setText(str(tmp_path))
    dialog.start_export()
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    assert dialog.table.item(0, 1).text() == '成功'
    assert dialog.progress.value() == 100
    dialog.close()
