from copy import deepcopy
from io import BytesIO
import json

from PIL import Image
import pytest

from test_ab_workflow import sample
from anime_rpg_sprite_studio.core.project_service import ProjectService


def png(mode, size=(32, 32)):
    out = BytesIO(); Image.new(mode, size).save(out, format='PNG'); return out.getvalue()


def test_edit_assets_save_reload_and_relocate(tmp_path):
    from anime_rpg_sprite_studio.core.ab_rig import ABAsset, ABEdit
    rig, assets = sample()
    rig.layers[0].edit = ABEdit(source=ABAsset('edit-source.png'), mask=ABAsset('edit-mask.png'), paint=ABAsset('edit-paint.png'))
    assets.update({'edit-source.png': png('RGBA'), 'edit-mask.png': png('L'), 'edit-paint.png': png('RGBA')})
    service = ProjectService(); character = service.add_character(); service.save(tmp_path / 'first/project.json')
    service.apply_ab_walk(character.id, rig, assets)
    service.save(service.path)
    service.save(tmp_path / 'second/project.json'); service.load(service.path)
    edit = service.project.characters[0].ab_walk.layers[0].edit
    assert edit is not None
    assert all(service.repository._asset(service.path.parent, ref.asset_path).is_file() for ref in (edit.source, edit.mask, edit.paint))
    assert service.repository.missing_assets(service.project, service.path) == []
    assert service.project.schema_version == 6


def test_invalid_mask_preserves_candidate_and_source(tmp_path):
    from anime_rpg_sprite_studio.core.ab_rig import ABAsset, ABEdit
    rig, assets = sample(); service = ProjectService(); character = service.add_character(); service.save(tmp_path / 'p.json')
    service.apply_ab_walk(character.id, rig, assets)
    before = deepcopy(character.ab_walk)
    rig.layers[0].edit = ABEdit(source=ABAsset('edit-source.png'), mask=ABAsset('edit-mask.png'), paint=ABAsset('edit-paint.png'))
    assets.update({'edit-source.png': png('RGBA'), 'edit-mask.png': png('RGBA'), 'edit-paint.png': png('RGBA')})
    before_files = set(tmp_path.rglob('*.png'))
    with pytest.raises(ValueError): service.apply_ab_walk(character.id, rig, assets)
    assert character.ab_walk == before and set(tmp_path.rglob('*.png')) == before_files


def test_schema3_upgrade_backup_and_conflicting_backup(tmp_path):
    service = ProjectService(); service.add_character(); path = tmp_path / 'project.json'; service.save(path)
    data = json.loads(path.read_text(encoding='utf-8')); data['schema_version'] = 3
    original = json.dumps(data).encode(); path.write_bytes(original)
    service.load(path)
    backup = tmp_path / 'project.json.schema3.bak'; backup.write_bytes(b'do not overwrite')
    with pytest.raises(FileExistsError): service.save(path)
    assert path.read_bytes() == original and backup.read_bytes() == b'do not overwrite'
    backup.unlink(); service.save(path)
    assert backup.read_bytes() == original
    assert json.loads(path.read_text(encoding='utf-8'))['schema_version'] == 6


def test_old_schema_rejects_new_edit_reference(tmp_path):
    from anime_rpg_sprite_studio.core.ab_rig import ABAsset, ABEdit
    rig, assets = sample(); service = ProjectService(); c = service.add_character(); path = tmp_path / 'p.json'; service.save(path)
    rig.layers[0].edit = ABEdit(ABAsset('src.png'), ABAsset('mask.png'), ABAsset('paint.png'))
    assets.update({'src.png': png('RGBA'), 'mask.png': png('L'), 'paint.png': png('RGBA')})
    service.apply_ab_walk(c.id, rig, assets); service.save(path)
    data = json.loads(path.read_text(encoding='utf-8')); data['schema_version'] = 3
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError): service.load(path)


def test_shared_source_reference_survives_staging_and_save_as(tmp_path):
    from anime_rpg_sprite_studio.core.ab_rig import ABAsset, ABEdit
    rig, assets = sample()
    rig.layers[0].edit = ABEdit(source=rig.source, mask=ABAsset('mask.png'), paint=ABAsset('paint.png'))
    assets.update({'mask.png': png('L'), 'paint.png': png('RGBA')})
    service = ProjectService(); c = service.add_character(); service.save(tmp_path / 'first/p.json')
    service.apply_ab_walk(c.id, rig, assets)
    service.save(tmp_path / 'second/p.json')
    service.load(service.path)
    loaded = service.project.characters[0].ab_walk
    assert loaded.source.asset_path == loaded.layers[0].edit.source.asset_path
    assert not service.repository.missing_assets(service.project, service.path)
