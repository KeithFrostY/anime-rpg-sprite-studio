"""Safe project-root adapter to the offline A/B renderer."""
from copy import deepcopy
from pathlib import Path
import math

from ..core.ab_rig import ABWalk
from .ab_renderer import RigProject


def load_ab_renderer(rig: ABWalk, project_root: Path) -> RigProject:
    rig.validate()
    root = Path(project_root).resolve()
    for ref in (rig.source, *rig.layers):
        target = (root / ref.asset_path).resolve()
        if not target.is_relative_to(root):
            raise ValueError('Asset escapes project directory')
    data = {
        'canvas': list(rig.canvas),
        'settings': deepcopy(rig.settings),
        'legs': deepcopy(rig.legs),
        'frame_overrides': deepcopy(rig.frame_overrides),
        'interpolate': rig.interpolate,
        'layers': [{'file': layer.asset_path, 'segment': layer.segment} for layer in rig.layers],
    }
    return RigProject(root / 'rig.json', data)


def correction_from_joint(renderer: RigProject, frame: int, leg: str, joint: str, target):
    """Return one frame/leg correction; move knee with fixed rigid bone lengths."""
    count = renderer.data['settings']['frames']
    if type(frame) is not int or not 0 <= frame < count or leg not in ('A', 'B') or joint not in ('hip', 'knee', 'ankle', 'toe'):
        raise ValueError('Invalid frame or joint')
    if not isinstance(target, (list, tuple)) or len(target) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 100000 for x in target):
        raise ValueError('Invalid target')
    target = [float(x) for x in target]
    source = renderer.data['legs'][leg]
    pose = renderer.pose(frame / count)['legs'][leg]
    existing = renderer.data.get('frame_overrides', {}).get(str(frame), {}).get(leg)
    change = {'hip': list(pose['hip']), 'ankle': list(pose['requested_ankle']),
              'bend': existing['bend'] if existing else pose.get('bend', source['bend']), 'foot_angle': pose.get('foot_angle', 0.0)}
    if joint == 'hip': change['hip'] = target
    elif joint == 'ankle': change['ankle'] = target
    elif joint == 'knee':
        hx, hy = pose['hip']; dx, dy = target[0] - hx, target[1] - hy
        length = math.hypot(dx, dy)
        if length <= 1e-9: raise ValueError('Knee target coincides with hip')
        upper = math.dist(source['hip'], source['knee'])
        knee = [hx + dx / length * upper, hy + dy / length * upper]
        vx, vy = pose['ankle'][0] - pose['knee'][0], pose['ankle'][1] - pose['knee'][1]
        lower = math.dist(source['knee'], source['ankle']); vlen = math.hypot(vx, vy)
        if vlen <= 1e-9: raise ValueError('Invalid lower leg')
        ankle = [knee[0] + vx / vlen * lower, knee[1] + vy / vlen * lower]
        cross = (knee[0]-hx)*(ankle[1]-hy) - (knee[1]-hy)*(ankle[0]-hx)
        if abs(cross) > 1e-8: change['bend'] = 1 if cross > 0 else -1
        change['ankle'] = ankle
    else:
        dx, dy = target[0]-pose['ankle'][0], target[1]-pose['ankle'][1]
        sx, sy = source['toe'][0]-source['ankle'][0], source['toe'][1]-source['ankle'][1]
        if math.hypot(dx, dy) <= 1e-9 or math.hypot(sx, sy) <= 1e-9:
            raise ValueError('Toe and ankle must be distinct')
        angle = math.degrees(math.atan2(dy, dx) - math.atan2(sy, sx))
        change['foot_angle'] = (angle + 180) % 360 - 180
    return change
