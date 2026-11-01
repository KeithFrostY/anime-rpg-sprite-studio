from copy import deepcopy
from math import dist

import pytest

from test_ab_workflow import sample
from anime_rpg_sprite_studio.animation.ab_walk import load_ab_renderer


def renderer_for(tmp_path):
    rig, assets = sample()
    rig.interpolate = False  # This suite verifies legacy single-frame edits.
    for name, data in assets.items():
        (tmp_path / name).write_bytes(data)
    return rig, load_ab_renderer(rig, tmp_path)


def test_per_frame_correction_preserves_identity_and_bone_lengths(tmp_path):
    from anime_rpg_sprite_studio.animation.ab_walk import correction_from_joint
    rig, renderer = renderer_for(tmp_path)
    before = renderer.pose(0); untouched = renderer.pose(0.125)
    correction = correction_from_joint(renderer, 0, 'A', 'ankle', [17, 23])
    rig.frame_overrides = {'0': {'A': correction}}
    updated = load_ab_renderer(rig, tmp_path)
    pose = updated.pose(0)
    assert pose['legs']['A']['ankle'] == pytest.approx([17, 23])
    assert pose['legs']['B'] == before['legs']['B']
    assert updated.pose(0.125) == untouched
    assert dist(pose['legs']['A']['hip'], pose['legs']['A']['knee']) == pytest.approx(8)
    assert dist(pose['legs']['A']['knee'], pose['legs']['A']['ankle']) == pytest.approx(8)


def test_knee_and_toe_corrections_and_validation(tmp_path):
    from anime_rpg_sprite_studio.animation.ab_walk import correction_from_joint
    rig, renderer = renderer_for(tmp_path)
    change = correction_from_joint(renderer, 3, 'A', 'knee', [20, 16])
    rig.frame_overrides = {'3': {'A': change}}
    updated = load_ab_renderer(rig, tmp_path); pose = updated.pose(3/8)['legs']['A']
    assert dist(pose['hip'], pose['knee']) == pytest.approx(8)
    assert dist(pose['knee'], pose['ankle']) == pytest.approx(8)
    direction = [20 - pose['hip'][0], 16 - pose['hip'][1]]
    magnitude = (direction[0]**2 + direction[1]**2)**0.5
    assert pose['knee'] == pytest.approx([pose['hip'][i] + direction[i]*8/magnitude for i in range(2)])
    change = correction_from_joint(updated, 3, 'A', 'toe', [pose['ankle'][0], pose['ankle'][1] + 4])
    rig.frame_overrides['3']['A'] = change
    changed = load_ab_renderer(rig, tmp_path).pose(3/8)['legs']['A']
    assert changed['toe'] == pytest.approx([changed['ankle'][0], changed['ankle'][1] + 4])
    assert changed['foot_angle'] != 0
    invalid = deepcopy(rig); invalid.frame_overrides = {'8': {'A': change}}
    with pytest.raises(ValueError): invalid.validate()


def test_override_roundtrip_and_export_metadata(tmp_path):
    from anime_rpg_sprite_studio.animation.ab_walk import correction_from_joint
    from anime_rpg_sprite_studio.core.project_service import ProjectService
    from anime_rpg_sprite_studio.export.ab_export import export_ab
    import json
    rig, assets = sample()
    rig.interpolate = False
    for name, data in assets.items(): (tmp_path / name).write_bytes(data)
    renderer = load_ab_renderer(rig, tmp_path)
    rig.frame_overrides = {'0': {'A': correction_from_joint(renderer, 0, 'A', 'toe', [16, 28])}}
    service = ProjectService(); character = service.add_character(); service.save(tmp_path / 'p.json')
    service.apply_ab_walk(character.id, rig, assets); service.save(service.path); service.load(service.path)
    assert service.project.characters[0].ab_walk.frame_overrides == rig.frame_overrides
    output = export_ab(rig, assets, tmp_path)
    metadata = json.loads((output / 'animation.json').read_text(encoding='utf-8'))
    assert metadata['frames'][0]['legs']['A']['foot_angle'] == pytest.approx(rig.frame_overrides['0']['A']['foot_angle'])
    assert metadata['frames'][1]['legs']['A']['foot_angle'] == 0
    assert 'not the lowest visible pixel' in metadata['ground_error_definition']


def test_foot_rotation_changes_foot_pixels_and_contact_reference(tmp_path):
    from io import BytesIO
    from PIL import Image
    from anime_rpg_sprite_studio.export.ab_export import export_ab
    import json
    rig, assets = sample()
    blank = Image.new('RGBA', rig.canvas)
    foot = blank.copy(); foot.putpixel((20, 24), (255, 0, 0, 255))
    def encode(image):
        stream = BytesIO(); image.save(stream, format='PNG'); return stream.getvalue()
    for layer in rig.layers: assets[layer.asset_path] = encode(foot if layer.segment == 'A.foot' else blank)
    for name, data in assets.items(): (tmp_path / name).write_bytes(data)
    renderer = load_ab_renderer(rig, tmp_path)
    before = renderer.render(0).tobytes()
    pose = renderer.pose(0)['legs']['A']
    rig.frame_overrides = {'0': {'A': {'hip':pose['hip'], 'ankle':pose['ankle'], 'bend':1, 'foot_angle':90}}}
    after = load_ab_renderer(rig, tmp_path).render(0).tobytes()
    assert before != after
    folder = export_ab(rig, assets, tmp_path)
    entry = json.loads((folder / 'animation.json').read_text(encoding='utf-8'))['frames'][0]['legs']['A']
    assert entry['ground_error'] == pytest.approx(entry['ankle'][1] - rig.settings['ground_y'])


def test_out_of_reach_remains_clamped_and_old_schema_backup(tmp_path):
    import json
    from anime_rpg_sprite_studio.animation.ab_walk import correction_from_joint
    from anime_rpg_sprite_studio.core.project_service import ProjectService
    rig, renderer = renderer_for(tmp_path)
    rig.frame_overrides = {'2': {'B': correction_from_joint(renderer, 2, 'B', 'ankle', [1000, 1000])}}
    pose = load_ab_renderer(rig, tmp_path).pose(2/8)['legs']['B']
    assert pose['limited'] and pose['requested_ankle'] == [1000, 1000]
    assert dist(pose['hip'], pose['knee']) == pytest.approx(8)
    assert dist(pose['knee'], pose['ankle']) == pytest.approx(8)
    invalid = deepcopy(rig); invalid.settings['frames'] = 2
    with pytest.raises(ValueError): invalid.validate()
    svc = ProjectService(); svc.add_character(); path = tmp_path/'project.json'; svc.save(path)
    data = json.loads(path.read_text(encoding='utf-8')); data['schema_version'] = 4
    old_bytes = json.dumps(data).encode(); path.write_bytes(old_bytes)
    svc.load(path); svc.save(path)
    assert path.with_name('project.json.schema4.bak').read_bytes() == old_bytes
