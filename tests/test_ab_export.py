import json
from threading import Event

import pytest
from PIL import Image

from test_ab_workflow import sample


def test_ab_export_preserves_frames_sheet_and_metadata(tmp_path):
    from anime_rpg_sprite_studio.export.ab_export import export_ab
    rig, assets = sample()
    rig.layers[0].needs_repair = True
    folder = export_ab(rig, assets, tmp_path)
    data = json.loads((folder / 'animation.json').read_text(encoding='utf-8'))
    assert data['direction'] == 'right' and data['fps'] == 10
    assert data['canvas'] == [32, 32] and len(data['frames']) == 8
    assert data['pending_repairs'] == ['B.upper']
    assert data['frames'][-1]['phase'] == 7 / 8
    sheet = Image.open(folder / 'spritesheet.png').convert('RGBA')
    assert sheet.size == (128, 64)
    for i, item in enumerate(data['frames']):
        frame = Image.open(folder / item['file']).convert('RGBA')
        assert frame.size == (32, 32)
        assert frame.tobytes() == sheet.crop(((i % 4)*32, (i // 4)*32, (i % 4+1)*32, (i // 4+1)*32)).tobytes()
        assert all('limited' in item['legs'][leg] and 'ground_error' in item['legs'][leg] for leg in ('A', 'B'))


def test_ab_export_cancel_or_bad_asset_leaves_no_output(tmp_path):
    from anime_rpg_sprite_studio.export.ab_export import export_ab, ABExportCancelled
    rig, assets = sample(); cancel = Event(); cancel.set()
    with pytest.raises(ABExportCancelled): export_ab(rig, assets, tmp_path, cancel)
    assert list(tmp_path.iterdir()) == []
    assets[rig.layers[0].asset_path] = b'broken'
    with pytest.raises(ValueError): export_ab(rig, assets, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_ab_dialog_exports_current_candidate(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from anime_rpg_sprite_studio.core.project_service import ProjectService
    from anime_rpg_sprite_studio.ui.ab_dialog import ABDialog
    rig, assets = sample()
    service = ProjectService(); character = service.add_character(); service.save(tmp_path / 'project.json')
    dialog = ABDialog(service, character.id); qtbot.addWidget(dialog)
    dialog.rig, dialog.assets = rig, assets
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(tmp_path))
    dialog.export_candidate()
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    assert dialog.result_path and (dialog.result_path / 'animation.json').exists()
    assert character.ab_walk is None
    dialog.close()


def test_cancel_during_export_cleans_stage_and_late_cancel_keeps_result(tmp_path):
    from anime_rpg_sprite_studio.export.ab_export import export_ab, ABExportCancelled
    rig, assets = sample(); cancel = Event()
    def early(percent, _):
        if percent >= 20: cancel.set()
    with pytest.raises(ABExportCancelled): export_ab(rig, assets, tmp_path, cancel, early)
    assert list(tmp_path.iterdir()) == []
    cancel.clear()
    def late(percent, _):
        if percent == 100: cancel.set()
    result = export_ab(rig, assets, tmp_path, cancel, late)
    assert cancel.is_set() and (result / 'animation.json').exists()


def test_ab_export_rejects_invalid_source_image(tmp_path):
    from anime_rpg_sprite_studio.export.ab_export import export_ab
    rig, assets = sample(); assets[rig.source.asset_path] = b'not a PNG'
    with pytest.raises(ValueError): export_ab(rig, assets, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_progress_failure_after_publish_still_reports_result(tmp_path):
    from anime_rpg_sprite_studio.export.ab_export import export_ab
    rig, assets = sample()
    def progress(value, message):
        if value == 100: raise RuntimeError('UI closed')
    result = export_ab(rig, assets, tmp_path, progress=progress)
    assert (result / 'animation.json').is_file()
