"""Transactional offline export for an A/B walk candidate."""
from copy import deepcopy
import json
from io import BytesIO
from math import ceil, dist, cos, radians
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from PIL import Image
from ..animation.ab_walk import load_ab_renderer


class ABExportCancelled(Exception):
    pass


def export_ab(rig, assets, destination, cancel=None, progress=None):
    rig = deepcopy(rig); rig.validate()
    assets = dict(assets)
    destination = Path(destination)
    if not destination.is_dir(): raise ValueError('輸出位置必須是現有資料夾')
    def check():
        if cancel is not None and cancel.is_set(): raise ABExportCancelled('已取消')
    def update(n, message):
        if progress is not None: progress(n, message)
    check()
    with TemporaryDirectory(prefix='.ab-export-', dir=destination) as temporary:
        root = Path(temporary); sources = root / 'source'; output = root / 'output'
        sources.mkdir(); output.mkdir()
        for ref in (rig.source, *rig.layers):
            check()
            blob = assets.get(ref.asset_path)
            if not isinstance(blob, bytes) or len(blob) > 32 * 1024 * 1024:
                raise ValueError('素材缺失或過大')
            try:
                with Image.open(BytesIO(blob)) as image:
                    if image.format != 'PNG' or image.width * image.height > 32_000_000 or getattr(image, 'n_frames', 1) != 1:
                        raise ValueError('素材必須是單張 PNG')
                    image.verify()
            except (OSError, Image.DecompressionBombError) as exc:
                raise ValueError('無法讀取 PNG 素材') from exc
            target = sources / ref.asset_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
        renderer = load_ab_renderer(rig, sources)
        width, height = rig.canvas; count = rig.settings['frames']
        sheet = Image.new('RGBA', (4 * width, ceil(count / 4) * height))
        frames, warnings = [], []
        for i in range(count):
            check()
            pose = renderer.pose(i / count)
            frame, bounds = renderer._compose(pose)
            clipped = bool(bounds and (bounds[0] < 0 or bounds[1] < 0 or bounds[2] > width or bounds[3] > height))
            legs = {}
            for leg in ('A', 'B'):
                p = pose['legs'][leg]; source = rig.legs[leg]
                sole_y = p['ankle'][1] + cos(radians(p.get('foot_angle', 0))) * (source['sole_y'] - source['ankle'][1])
                legs[leg] = {'hip': p['hip'], 'knee': p['knee'], 'ankle': p['ankle'], 'toe': p['toe'],
                             'expected_contact': p['contact'], 'limited': p['limited'],
                             'foot_angle': p.get('foot_angle', 0),
                             'requested_ankle': p['requested_ankle'],
                             'reach_error': dist(p['ankle'], p['requested_ankle']),
                             'ground_error': sole_y - rig.settings['ground_y']}
                if p['limited']: warnings.append(f'frame {i} leg {leg}: unreachable')
            if clipped: warnings.append(f'frame {i}: clipped')
            name = f'frame_{i:03}.png'; frame.save(output / name)
            x, y = (i % 4) * width, (i // 4) * height
            sheet.paste(frame, (x, y))
            frames.append({'index': i, 'phase': i/count, 'file': name, 'rect': [x, y, width, height],
                           'legs': legs, 'unclipped_bounds': bounds, 'clipped': clipped})
            update(round(80 * (i+1)/count), f'正在處理第 {i+1}/{count} 幀')
        check(); sheet.save(output / 'spritesheet.png')
        data = {'format_version': 1, 'animation': 'walk', 'direction': 'right', 'fps': rig.settings['fps'],
                'loop': True, 'canvas': list(rig.canvas), 'origin': list(rig.origin),
                'coordinate_system': 'top-left, y down', 'ground_y': rig.settings['ground_y'],
                'ground_error_definition': 'Rotated source reference point (ankle.x, sole_y) minus ground_y; not the lowest visible pixel.',
                'leg_identity': {'A': 'near', 'B': 'far'}, 'settings': rig.settings,
                'interpolation': {'enabled': rig.interpolate, 'method': 'cyclic smoothstep on relative offsets',
                                  'bend': 'previous key, discrete'},
                'pending_repairs': [layer.segment for layer in rig.layers if layer.needs_repair],
                'sheet': {'file': 'spritesheet.png', 'columns': 4, 'rows': ceil(count/4)},
                'frames': frames, 'warnings': warnings}
        (output / 'animation.json').write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        if json.loads((output / 'animation.json').read_text(encoding='utf-8')) != data:
            raise ValueError('動畫資料驗證失敗')
        with Image.open(output / 'spritesheet.png') as stored:
            if stored.mode != 'RGBA' or stored.size != sheet.size: raise ValueError('Sprite Sheet 驗證失敗')
            for item in frames:
                check()
                with Image.open(output / item['file']) as frame:
                    x, y, w, h = item['rect']
                    if frame.mode != 'RGBA' or frame.size != (w, h) or frame.tobytes() != stored.crop((x, y, x+w, y+h)).tobytes():
                        raise ValueError('匯出影格驗證失敗')
        check()
        target = destination / f'ab-walk-{uuid4().hex}'
        output.rename(target)
    # Publication succeeded; a disconnected progress listener must not turn it into failure.
    try: update(100, '匯出完成')
    except Exception: pass
    return target
