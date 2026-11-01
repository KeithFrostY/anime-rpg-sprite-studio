import json
from pathlib import Path

from PIL import Image, ImageChops
import pytest

from anime_rpg_sprite_studio.core.models import Character, Project
from anime_rpg_sprite_studio.core.project_repository import ProjectRepository


def test_legacy_upgrade_and_ab_roundtrip(tmp_path):
    from anime_rpg_sprite_studio.core.ab_rig import ABWalk, ABLayer, ABAsset
    repo = ProjectRepository()
    project = Project(characters=[Character()])
    path = tmp_path / 'project.json'
    repo.save(project, path)
    original = json.loads(path.read_text(encoding='utf-8'))
    original['schema_version'] = 2
    path.write_text(json.dumps(original), encoding='utf-8')
    loaded = repo.load(path)
    assert loaded.characters[0].ab_walk is None
    loaded.characters[0].ab_walk = ABWalk(canvas=(10, 10), source=ABAsset('assets/source.png'),
        layers=[ABLayer(segment=s, asset_path=f'assets/{s}.png') for s in ('body','A.upper','A.lower','A.foot','B.upper','B.lower','B.foot')],
        legs={name: {'hip':[5,2], 'knee':[5,4], 'ankle':[5,6], 'toe':[6,6], 'sole_y':7, 'bend':1} for name in ('A','B')},
        settings={'frames':8,'fps':10,'stride':2,'lift':1,'bob':0,'hip_drop':0,'ground_y':7,'stance_fraction':0.6})
    repo.save(loaded, path)
    reopened = repo.load(path)
    assert reopened.schema_version == 6 and reopened.characters[0].ab_walk.layers[0].segment == 'body'
    assert len(repo.missing_assets(reopened, path)) == 8


def test_ab_renderer_matches_prototype_and_rejects_escape(tmp_path):
    import importlib.util
    from anime_rpg_sprite_studio.core.ab_rig import ab_from_prototype
    from anime_rpg_sprite_studio.animation.ab_walk import load_ab_renderer
    root = Path('build/handoff-review-20261101/SpriteStudio/prototype/walkcycle_tool').resolve()
    if not (root / 'walkcycle.py').exists():
        pytest.skip('local handoff reference is unavailable')
    spec = importlib.util.spec_from_file_location('prototype_walkcycle', root / 'walkcycle.py')
    original = importlib.util.module_from_spec(spec); spec.loader.exec_module(original)
    for sample in ('schematic', 'arcane'):
        path = root / 'examples' / sample / 'rig.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        rig = ab_from_prototype(data, 'source.png')
        candidate = load_ab_renderer(rig, path.parent)
        baseline = original.load_project(path)
        for phase in (index / 8 for index in range(8)):
            assert candidate.pose(phase) == baseline.pose(phase)
            assert candidate.render(phase).tobytes() == baseline.render(phase).tobytes()
    data['layers'][0]['file'] = '../escape.png'
    with pytest.raises(ValueError): ab_from_prototype(data, 'source.png')


def test_project_save_as_copies_ab_assets_and_reopens(tmp_path):
    from anime_rpg_sprite_studio.core.project_service import ProjectService
    from anime_rpg_sprite_studio.core.ab_rig import ab_from_prototype
    source = Path('build/handoff-review-20261101/SpriteStudio/prototype/walkcycle_tool/examples/schematic').resolve()
    if not source.exists(): pytest.skip('local handoff reference is unavailable')
    data = json.loads((source / 'rig.json').read_text(encoding='utf-8'))
    rig = ab_from_prototype(data, 'layers/body.png')
    service = ProjectService()
    character = service.add_character()
    first = tmp_path / 'first'; first.mkdir()
    for ref in (rig.source, *rig.layers):
        dst = first / ref.asset_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((source / ref.asset_path).read_bytes())
    character.ab_walk = rig
    service.save(first / 'project.json')
    service.save(tmp_path / 'second' / 'project.json')
    service.load(service.path)
    from anime_rpg_sprite_studio.animation.ab_walk import load_ab_renderer
    candidate = load_ab_renderer(service.project.characters[0].ab_walk, service.path.parent)
    assert candidate.render(0).size == (384, 576)


def test_old_version_cannot_silently_carry_new_data(tmp_path):
    repo = ProjectRepository()
    path = tmp_path / 'p.json'
    repo.save(Project(characters=[Character()]), path)
    data = json.loads(path.read_text(encoding='utf-8'))
    data['schema_version'] = 2
    data['characters'][0]['ab_walk'] = {'version': 1}
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError): repo.load(path)


def test_renderer_uses_project_assets_without_handoff(tmp_path):
    from anime_rpg_sprite_studio.core.ab_rig import ABAsset, ABLayer, ABWalk
    from anime_rpg_sprite_studio.animation.ab_walk import load_ab_renderer
    segments = ('body','A.upper','A.lower','A.foot','B.upper','B.lower','B.foot')
    layers = []
    for index, segment in enumerate(segments):
        name = f'{index}.png'
        Image.new('RGBA', (32, 32), (index * 20, 10, 30, 255)).save(tmp_path / name)
        layers.append(ABLayer(asset_path=name, segment=segment))
    rig = ABWalk(canvas=(32, 32), source=ABAsset('0.png'), layers=layers,
        legs={key: {'hip':[16,8], 'knee':[16,16], 'ankle':[16,24], 'toe':[20,24], 'sole_y':25, 'bend':1} for key in ('A','B')},
        settings={'frames':8,'fps':10,'stride':2,'lift':1,'bob':0,'hip_drop':0,'ground_y':25,'stance_fraction':0.6})
    renderer = load_ab_renderer(rig, tmp_path)
    assert renderer.render(0).size == (32, 32)
    assert renderer.pose(0)['legs']['A']['contact']


def test_save_legacy_creates_backup_and_never_overwrites_it(tmp_path):
    repo = ProjectRepository()
    path = tmp_path / 'project.json'
    repo.save(Project(characters=[Character()]), path)
    old = json.loads(path.read_text(encoding='utf-8'))
    old['schema_version'] = 2
    original = json.dumps(old).encode('utf-8')
    path.write_bytes(original)
    loaded = repo.load(path)
    backup = tmp_path / 'project.json.schema2.bak'
    backup.write_bytes(b'other valuable backup')
    with pytest.raises(FileExistsError): repo.save(loaded, path)
    assert path.read_bytes() == original
    assert backup.read_bytes() == b'other valuable backup'
    backup.unlink()
    repo.save(loaded, path)
    assert backup.read_bytes() == original
    assert json.loads(path.read_text(encoding='utf-8'))['schema_version'] == 6


def test_ab_rejects_extreme_total_output_pixels():
    from anime_rpg_sprite_studio.core.ab_rig import ABAsset, ABLayer, ABWalk
    layers = [ABLayer(asset_path='a.png', segment=s) for s in ('body','A.upper','A.lower','A.foot','B.upper','B.lower','B.foot')]
    rig = ABWalk(canvas=(2048, 2048), source=ABAsset('a.png'), layers=layers,
        legs={key: {'hip':[16,8], 'knee':[16,16], 'ankle':[16,24], 'toe':[20,24], 'sole_y':25, 'bend':1} for key in ('A','B')},
        settings={'frames':240,'fps':10,'stride':2,'lift':1,'bob':0,'hip_drop':0,'ground_y':25,'stance_fraction':0.6})
    with pytest.raises(ValueError, match='memory'): rig.validate()
