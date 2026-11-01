from io import BytesIO
from copy import deepcopy

import pytest
from PIL import Image

from anime_rpg_sprite_studio.core.ab_rig import ABAsset, ABLayer, ABWalk
from anime_rpg_sprite_studio.core.project_service import ProjectService


def sample():
    segments = ('B.upper', 'B.lower', 'B.foot', 'A.upper', 'A.lower', 'A.foot', 'body')
    rig = ABWalk(canvas=(32, 32), source=ABAsset('source.png'),
        layers=[ABLayer(asset_path=f'{segment}.png', segment=segment) for segment in segments],
        legs={leg: {'hip':[16,8], 'knee':[16,16], 'ankle':[16,24], 'toe':[20,24], 'sole_y':25, 'bend':1} for leg in ('A','B')},
        settings={'frames':8,'fps':10,'stride':2,'lift':1,'bob':0,'hip_drop':0,'ground_y':25,'stance_fraction':0.6})
    img = Image.new('RGBA', (32, 32), (100, 50, 20, 255))
    b = BytesIO(); img.save(b, format='PNG')
    assets = {r.asset_path: b.getvalue() for r in (rig.source, *rig.layers)}
    return rig, assets


def test_apply_ab_candidate_roundtrip_and_failure(tmp_path):
    service = ProjectService(); character = service.add_character(); service.save(tmp_path / 'project.json')
    rig, assets = sample()
    service.apply_ab_walk(character.id, rig, assets)
    assert character.ab_walk is not None and character.ab_walk is not rig
    service.save(service.path)
    service.load(service.path)
    assert service.project.characters[0].ab_walk.settings['frames'] == 8
    from anime_rpg_sprite_studio.animation.ab_walk import load_ab_renderer
    assert load_ab_renderer(service.project.characters[0].ab_walk, tmp_path).render(0).size == (32, 32)
    before = deepcopy(service.project.characters[0].ab_walk)
    assets[rig.layers[0].asset_path] = b'invalid'
    with pytest.raises(ValueError): service.apply_ab_walk(character.id, rig, assets)
    assert service.project.characters[0].ab_walk == before


def test_ab_editor_candidate_preview_and_apply(qtbot, tmp_path):
    from anime_rpg_sprite_studio.ui.ab_dialog import ABDialog
    service = ProjectService(); character = service.add_character(); service.save(tmp_path / 'project.json')
    rig, assets = sample()
    paths = {}
    for name, data in assets.items():
        path = tmp_path / name; path.write_bytes(data); paths[name] = path
    dialog = ABDialog(service, character.id)
    qtbot.addWidget(dialog)
    dialog.set_source(paths['source.png'])
    for layer in rig.layers:
        dialog.set_layer(layer.segment, paths[layer.asset_path])
    dialog.parts.setCurrentRow(0)
    original = [layer.segment for layer in dialog.rig.layers]
    dialog.move_layer(1)
    assert [layer.segment for layer in dialog.rig.layers][:2] == original[:2][::-1]
    assert character.ab_walk is None
    dialog.joint_x.setValue(14)
    dialog.update_joint()
    dialog.show_source()
    dialog.skeleton.joint_moved.emit('A', 'hip', 12.0, 8.0)
    assert dialog.rig.legs['A']['hip'] == [12.0, 8.0]
    dialog.joint_x.setValue(14)
    dialog.update_joint()
    dialog.generate_preview()
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    assert len(dialog.frames) == 8
    assert dialog.rig.legs['A']['hip'][0] == 14
    dialog.apply_candidate()
    assert character.ab_walk is not None
    dialog.close()


def test_missing_source_does_not_break_editor(qtbot, tmp_path):
    from anime_rpg_sprite_studio.ui.ab_dialog import ABDialog
    service = ProjectService(); c = service.add_character(); service.save(tmp_path / 'p.json')
    rig, assets = sample(); service.apply_ab_walk(c.id, rig, assets)
    (tmp_path / c.ab_walk.source.asset_path).unlink()
    dialog = ABDialog(service, c.id); qtbot.addWidget(dialog)
    dialog.show_source()
    assert dialog.skeleton.image.isNull()
    assert len(dialog.assets) == 7
    dialog.close()


def test_duplicate_layer_replacement_is_rejected_without_mutation(qtbot, tmp_path):
    from anime_rpg_sprite_studio.ui.ab_dialog import ABDialog
    service = ProjectService(); c = service.add_character(); service.save(tmp_path / 'p.json')
    rig, assets = sample(); service.apply_ab_walk(c.id, rig, assets)
    c.ab_walk.layers.append(deepcopy(c.ab_walk.layers[0]))
    dialog = ABDialog(service, c.id); qtbot.addWidget(dialog)
    before, prior_assets = deepcopy(dialog.rig), dict(dialog.assets)
    path = tmp_path / 'new.png'; path.write_bytes(next(iter(assets.values())))
    with pytest.raises(ValueError): dialog.set_layer('B.upper', path)
    assert dialog.rig == before and dialog.assets == prior_assets
    dialog.close()


def test_unsaved_candidate_requires_confirmation(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from anime_rpg_sprite_studio.ui.ab_dialog import ABDialog
    service = ProjectService(); character = service.add_character(); service.save(tmp_path / 'p.json')
    _, assets = sample(); source = tmp_path / 'input.png'; source.write_bytes(assets['source.png'])
    dialog = ABDialog(service, character.id); qtbot.addWidget(dialog); dialog.set_source(source); dialog.show()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
    dialog.close()
    assert dialog.isVisible() and dialog.candidate_dirty
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    dialog.close()
    assert not dialog.isVisible()


def test_skeleton_maps_source_size_to_rig_canvas(qtbot):
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtGui import QPixmap
    from PySide6.QtTest import QTest
    from anime_rpg_sprite_studio.ui.ab_dialog import SkeletonEditor
    rig, _ = sample()
    editor = SkeletonEditor(); qtbot.addWidget(editor); editor.resize(320, 320)
    editor.rig = rig; editor.image = QPixmap(64, 64); editor.show()
    qtbot.waitExposed(editor)
    moved = []; editor.joint_moved.connect(lambda *args: moved.append(args))
    QTest.mousePress(editor, Qt.MouseButton.LeftButton, pos=QPoint(160, 80))
    QTest.mouseRelease(editor, Qt.MouseButton.LeftButton, pos=QPoint(200, 100))
    assert moved and moved[0][:2] == ('A', 'hip')
    assert moved[0][2:] == pytest.approx((20, 10))


def test_missing_source_can_be_restored_without_losing_rig(qtbot, tmp_path):
    from anime_rpg_sprite_studio.ui.ab_dialog import ABDialog
    service = ProjectService(); c = service.add_character(); service.save(tmp_path / 'p.json')
    rig, assets = sample(); service.apply_ab_walk(c.id, rig, assets)
    original_legs = deepcopy(c.ab_walk.legs)
    (tmp_path / c.ab_walk.source.asset_path).unlink()
    dialog = ABDialog(service, c.id); qtbot.addWidget(dialog)
    path = tmp_path / 'replacement.png'; path.write_bytes(assets['source.png'])
    dialog.restore_source(path)
    assert dialog.rig.legs == original_legs and len(dialog.rig.layers) == 7
    assert not dialog.skeleton.image.isNull()
    dialog.candidate_dirty = False; dialog.close()
