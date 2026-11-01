import json
from copy import deepcopy
from math import dist

import pytest

from test_ab_workflow import sample
from anime_rpg_sprite_studio.animation.ab_walk import load_ab_renderer
from anime_rpg_sprite_studio.core.project_service import ProjectService


def setup_rig(tmp_path):
    rig, assets = sample()
    for name, data in assets.items(): (tmp_path / name).write_bytes(data)
    return rig, assets


def override(base, dx, angle=0, bend=1):
    return {'hip': [base['hip'][0]+dx, base['hip'][1]],
            'ankle': [base['requested_ankle'][0]+dx, base['requested_ankle'][1]],
            'bend': bend, 'foot_angle': angle}


def test_interpolation_keyframes_midpoints_wrap_and_bone_lengths(tmp_path):
    rig, _ = setup_rig(tmp_path); base = load_ab_renderer(rig, tmp_path)
    old = [base.pose(i/8) for i in range(8)]
    rig.frame_overrides = {'1': {'A': override(old[1]['legs']['A'], 2, 170)},
                           '5': {'A': override(old[5]['legs']['A'], 6, -170)}}
    rig.interpolate = True
    engine = load_ab_renderer(rig, tmp_path)
    for i, expected in ((1,2), (2,2.625), (3,4), (5,6), (7,4), (0,2.625)):
        pose = engine.pose(i/8)
        assert pose['legs']['A']['hip'][0] - old[i]['legs']['A']['hip'][0] == pytest.approx(expected)
        assert pose['legs']['B'] == old[i]['legs']['B']
        assert dist(pose['legs']['A']['hip'], pose['legs']['A']['knee']) == pytest.approx(8)
        assert dist(pose['legs']['A']['knee'], pose['legs']['A']['ankle']) == pytest.approx(8)
    assert abs(engine.pose(3/8)['legs']['A']['foot_angle']) == pytest.approx(180)
    for i in (1, 5):
        leg = engine.pose(i/8)['legs']['A']; key = rig.frame_overrides[str(i)]['A']
        assert leg['hip'] == pytest.approx(key['hip'])
        assert leg['requested_ankle'] == pytest.approx(key['ankle'])
        assert leg['foot_angle'] == pytest.approx(key['foot_angle'])
    assert engine.pose(0) == engine.pose(1)
    before, after = engine.pose(1-1e-8)['legs']['A'], engine.pose(1e-8)['legs']['A']
    assert before['requested_ankle'] == pytest.approx(after['requested_ankle'], abs=1e-5)


def test_disabled_and_single_key_behaviour(tmp_path):
    rig, _ = setup_rig(tmp_path); old = load_ab_renderer(rig, tmp_path)
    base = [old.pose(i/8) for i in range(8)]
    rig.frame_overrides = {'0': {'A': override(base[0]['legs']['A'], 3, 30)}}
    rig.interpolate = False
    disabled = load_ab_renderer(rig, tmp_path)
    assert disabled.pose(1/8) == base[1]
    rig.interpolate = True
    enabled = load_ab_renderer(rig, tmp_path)
    for i in range(8):
        leg = enabled.pose(i/8)['legs']['A']
        assert leg['hip'][0] == pytest.approx(base[i]['legs']['A']['hip'][0]+3)
        assert leg['foot_angle'] == pytest.approx(30)


def test_legacy_project_preserves_frame_mode_and_backup(tmp_path):
    service = ProjectService(); c = service.add_character(); path = tmp_path/'project.json'; service.save(path)
    rig, assets = sample(); service.apply_ab_walk(c.id, rig, assets); service.save(path)
    raw = json.loads(path.read_text(encoding='utf-8')); raw['schema_version'] = 5
    raw['characters'][0]['ab_walk'].pop('interpolate', None)
    old = json.dumps(raw).encode(); path.write_bytes(old)
    service.load(path)
    assert service.project.schema_version == 6
    assert service.project.characters[0].ab_walk.interpolate is False
    service.save(path)
    assert path.with_name('project.json.schema5.bak').read_bytes() == old


def test_export_uses_same_interpolated_pose(tmp_path):
    from anime_rpg_sprite_studio.export.ab_export import export_ab
    rig, assets = setup_rig(tmp_path); base = load_ab_renderer(rig, tmp_path)
    rig.frame_overrides = {'0': {'A': override(base.pose(0)['legs']['A'], 2)},
                           '4': {'A': override(base.pose(.5)['legs']['A'], 4)}}
    rig.interpolate = True
    engine = load_ab_renderer(rig, tmp_path)
    out = export_ab(rig, assets, tmp_path)
    data = json.loads((out/'animation.json').read_text(encoding='utf-8'))
    assert data['interpolation']['enabled'] is True
    for i in range(8):
        pose = engine.pose(i/8)['legs']['A']
        assert data['frames'][i]['legs']['A']['requested_ankle'] == pytest.approx(pose['requested_ankle'])
        from PIL import Image
        with Image.open(out / data['frames'][i]['file']) as frame:
            assert frame.tobytes() == engine.render(i/8).tobytes()


def test_without_keys_renderer_pixels_unchanged_and_bend_is_discrete(tmp_path):
    rig, _ = setup_rig(tmp_path); rig.interpolate = False
    old = load_ab_renderer(rig, tmp_path)
    rig.interpolate = True; same = load_ab_renderer(rig, tmp_path)
    for i in range(8):
        assert same.pose(i/8) == old.pose(i/8)
        assert same.render(i/8).tobytes() == old.render(i/8).tobytes()
    poses = [old.pose(i/8) for i in range(8)]
    rig.frame_overrides = {'1': {'A': override(poses[1]['legs']['A'], 0, bend=1)},
                           '5': {'A': override(poses[5]['legs']['A'], 0, bend=-1)}}
    result = load_ab_renderer(rig, tmp_path)
    assert result.pose(4/8)['legs']['A']['bend'] == 1
    assert result.pose(5/8)['legs']['A']['bend'] == -1
    assert result.pose(0)['legs']['A']['bend'] == -1


def test_old_schema_cannot_smuggle_interpolation_flag(tmp_path):
    service = ProjectService(); c = service.add_character(); path = tmp_path/'project.json'; service.save(path)
    rig, assets = sample(); service.apply_ab_walk(c.id, rig, assets); service.save(path)
    raw = json.loads(path.read_text(encoding='utf-8')); raw['schema_version'] = 5
    path.write_text(json.dumps(raw), encoding='utf-8')
    with pytest.raises(ValueError, match='schema 6'): service.load(path)


def test_new_key_inherits_interpolated_knee_bend(tmp_path):
    from anime_rpg_sprite_studio.animation.ab_walk import correction_from_joint
    rig, _ = setup_rig(tmp_path); base = load_ab_renderer(rig, tmp_path)
    rig.frame_overrides = {'0': {'A': override(base.pose(0)['legs']['A'], 0, bend=-1)},
                           '4': {'A': override(base.pose(.5)['legs']['A'], 0, bend=1)}}
    renderer = load_ab_renderer(rig, tmp_path)
    previous = renderer.pose(.25)['legs']['A']
    assert previous['bend'] == -1
    key = correction_from_joint(renderer, 2, 'A', 'hip', previous['hip'])
    assert key['bend'] == -1
    rig.frame_overrides['2'] = {'A': key}
    after = load_ab_renderer(rig, tmp_path).pose(.25)['legs']['A']
    assert after['knee'] == pytest.approx(previous['knee'])
