from io import BytesIO

from PIL import Image
from PySide6.QtWidgets import QDialog

from anime_rpg_sprite_studio.core.project_service import ProjectService
from test_ab_workflow import sample


def png(mode, color):
    image = Image.new(mode, (32, 32), color)
    stream = BytesIO(); image.save(stream, format='PNG'); return stream.getvalue()


def test_edit_layer_keeps_editable_parts_after_project_reopen(qtbot, tmp_path, monkeypatch):
    from anime_rpg_sprite_studio.ui.ab_dialog import ABDialog
    from anime_rpg_sprite_studio.ui import mask_paint_dialog
    service = ProjectService(); character = service.add_character(); service.save(tmp_path / 'project.json')
    rig, assets = sample(); service.apply_ab_walk(character.id, rig, assets)
    dialog = ABDialog(service, character.id); qtbot.addWidget(dialog)
    dialog.parts.setCurrentRow(0)
    mask = png('L', 255); paint = png('RGBA', (255, 0, 0, 100)); result = png('RGBA', (200, 0, 0, 255))
    class FakeEditor:
        def __init__(self, source_bytes, mask_bytes=None, paint_bytes=None, references=None, parent=None):
            self.result_bytes = (source_bytes, mask, paint, result)
        def exec(self): return QDialog.DialogCode.Accepted
    monkeypatch.setattr(mask_paint_dialog, 'MaskPaintDialog', FakeEditor)
    before = character.ab_walk.layers[0].asset_path
    dialog.open_mask_editor(start_from_source=False)
    assert character.ab_walk.layers[0].asset_path == before
    assert dialog.rig.layers[0].edit is not None
    dialog.apply_candidate(); service.save(service.path); service.load(service.path)
    layer = service.project.characters[0].ab_walk.layers[0]
    assert layer.edit is not None
    assert not service.repository.missing_assets(service.project, service.path)
    assert (service.path.parent / layer.edit.mask.asset_path).read_bytes() == mask
    dialog.candidate_dirty = False; dialog.close()


def test_new_part_from_source_starts_with_empty_mask_and_cancel_is_safe(qtbot, tmp_path, monkeypatch):
    from anime_rpg_sprite_studio.ui.ab_dialog import ABDialog
    from anime_rpg_sprite_studio.ui import mask_paint_dialog
    service = ProjectService(); character = service.add_character(); service.save(tmp_path / 'p.json')
    source = tmp_path / 'source.png'; source.write_bytes(png('RGBA', (20, 30, 40, 255)))
    dialog = ABDialog(service, character.id); qtbot.addWidget(dialog); dialog.set_source(source)
    seen = []
    class FakeEditor:
        def __init__(self, source_bytes, mask_bytes=None, paint_bytes=None, references=None, parent=None):
            with Image.open(BytesIO(mask_bytes)) as mask: seen.append(mask.getpixel((0, 0)))
        def exec(self): return QDialog.DialogCode.Rejected
    monkeypatch.setattr(mask_paint_dialog, 'MaskPaintDialog', FakeEditor)
    dialog.open_mask_editor(start_from_source=True)
    assert seen == [0] and dialog.rig.layers == []
    dialog.candidate_dirty = False; dialog.close()


def test_replacing_existing_from_source_requires_confirmation(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from anime_rpg_sprite_studio.ui.ab_dialog import ABDialog
    service = ProjectService(); character = service.add_character(); service.save(tmp_path / 'p.json')
    rig, assets = sample(); service.apply_ab_walk(character.id, rig, assets)
    dialog = ABDialog(service, character.id); qtbot.addWidget(dialog)
    old_layer = dialog.rig.layers[0]
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
    dialog.open_mask_editor(start_from_source=True)
    assert dialog.rig.layers[0] is old_layer
    dialog.close()


def test_rgb_source_can_be_cut_without_changing_original(qtbot, tmp_path, monkeypatch):
    from anime_rpg_sprite_studio.ui.ab_dialog import ABDialog
    from anime_rpg_sprite_studio.ui import mask_paint_dialog
    service = ProjectService(); character = service.add_character(); service.save(tmp_path / 'p.json')
    source = tmp_path / 'source.png'; original = png('RGB', (20, 30, 40)); source.write_bytes(original)
    dialog = ABDialog(service, character.id); qtbot.addWidget(dialog); dialog.set_source(source)
    class FakeEditor:
        def __init__(self, source_bytes, mask_bytes=None, paint_bytes=None, references=None, parent=None):
            self.result_bytes = (source_bytes, png('L', 255), png('RGBA', (0,0,0,0)), png('RGBA', (20,30,40,255)))
        def exec(self): return QDialog.DialogCode.Accepted
    monkeypatch.setattr(mask_paint_dialog, 'MaskPaintDialog', FakeEditor)
    dialog.open_mask_editor(start_from_source=True)
    assert len(dialog.rig.layers) == 1 and source.read_bytes() == original
    dialog.candidate_dirty = False; dialog.close()


def test_different_source_size_allows_same_size_reference(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from anime_rpg_sprite_studio.ui.ab_dialog import ABDialog
    from anime_rpg_sprite_studio.ui import mask_paint_dialog
    service = ProjectService(); character = service.add_character(); service.save(tmp_path / 'p.json')
    rig, assets = sample()
    stream = BytesIO(); Image.new('RGBA', (64,64), 'red').save(stream, format='PNG')
    assets[rig.source.asset_path] = stream.getvalue()
    service.apply_ab_walk(character.id, rig, assets)
    dialog = ABDialog(service, character.id); qtbot.addWidget(dialog)
    reference = tmp_path / 'ref.png'; reference.write_bytes(png('RGBA', (1,2,3,255)))
    seen = []
    class FakeEditor:
        def __init__(self, source_bytes, mask_bytes=None, paint_bytes=None, references=None, parent=None): seen.append(source_bytes)
        def exec(self): return QDialog.DialogCode.Rejected
    monkeypatch.setattr(mask_paint_dialog, 'MaskPaintDialog', FakeEditor)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(reference), ''))
    before = dialog.rig.canvas
    dialog.open_mask_editor(start_from_source=True)
    assert seen == [reference.read_bytes()] and dialog.rig.canvas == before
    dialog.close()


def test_many_reference_layers_are_flattened(qtbot, tmp_path, monkeypatch):
    from anime_rpg_sprite_studio.core.ab_rig import ABLayer
    from anime_rpg_sprite_studio.ui.ab_dialog import ABDialog
    from anime_rpg_sprite_studio.ui import mask_paint_dialog
    service = ProjectService(); character = service.add_character(); service.save(tmp_path / 'p.json')
    rig, assets = sample(); service.apply_ab_walk(character.id, rig, assets)
    dialog = ABDialog(service, character.id); qtbot.addWidget(dialog)
    dialog.rig.layers.extend(ABLayer(asset_path=dialog.rig.layers[-1].asset_path, segment='body') for _ in range(3))
    seen = []
    class FakeEditor:
        def __init__(self, source_bytes, mask_bytes=None, paint_bytes=None, references=None, parent=None): seen.extend(references)
        def exec(self): return QDialog.DialogCode.Rejected
    monkeypatch.setattr(mask_paint_dialog, 'MaskPaintDialog', FakeEditor)
    dialog.open_mask_editor(start_from_source=False)
    assert len(seen) == 1
    dialog.close()
