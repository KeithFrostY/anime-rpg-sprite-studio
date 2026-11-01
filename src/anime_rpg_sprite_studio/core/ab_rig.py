"""Serializable A/B walk data, independent of GUI and renderer."""
from dataclasses import dataclass, field
from math import isfinite, dist
from .models import validate_asset_path

SEGMENTS = {'body', 'A.upper', 'A.lower', 'A.foot', 'B.upper', 'B.lower', 'B.foot'}


@dataclass
class ABAsset:
    asset_path: str

    def validate(self):
        if not isinstance(self.asset_path, str):
            raise ValueError('Invalid asset path')
        validate_asset_path(self.asset_path)


@dataclass
class ABEdit:
    source: ABAsset
    mask: ABAsset
    paint: ABAsset
    version: int = 1

    def validate(self):
        if type(self.version) is not int or self.version != 1:
            raise ValueError('Unsupported A/B edit version')
        for asset in (self.source, self.mask, self.paint):
            if not isinstance(asset, ABAsset): raise ValueError('Invalid A/B edit asset')
            asset.validate()


@dataclass
class ABLayer(ABAsset):
    segment: str
    needs_repair: bool = False
    edit: ABEdit | None = None

    def validate(self):
        super().validate()
        if self.segment not in SEGMENTS or type(self.needs_repair) is not bool:
            raise ValueError('Invalid A/B layer')
        if self.edit is not None:
            if not isinstance(self.edit, ABEdit): raise ValueError('Invalid A/B edit')
            self.edit.validate()


@dataclass
class ABWalk:
    canvas: tuple[int, int]
    source: ABAsset
    layers: list[ABLayer]
    legs: dict
    settings: dict
    version: int = 1
    view: str = 'right'
    origin: tuple[int, int] = (0, 0)
    frame_overrides: dict = field(default_factory=dict)
    interpolate: bool = True

    def validate(self):
        if type(self.interpolate) is not bool:
            raise ValueError('Invalid interpolation mode')
        if type(self.version) is not int or self.version != 1 or self.view != 'right':
            raise ValueError('Unsupported A/B version or view')
        if len(self.canvas) != 2 or any(type(x) is not int or not 1 <= x <= 8192 for x in self.canvas) or self.canvas[0] * self.canvas[1] > 32_000_000:
            raise ValueError('Invalid A/B canvas')
        if tuple(self.origin) != (0, 0):
            raise ValueError('A/B origin must be top-left')
        if not isinstance(self.source, ABAsset):
            raise ValueError('Source image required')
        self.source.validate()
        if not isinstance(self.layers, list) or not 7 <= len(self.layers) <= 32:
            raise ValueError('Invalid A/B layers')
        if self.canvas[0] * self.canvas[1] * len(self.layers) > 64_000_000:
            raise ValueError('A/B layers exceed memory limit')
        for layer in self.layers:
            if not isinstance(layer, ABLayer): raise ValueError('Invalid A/B layer')
            layer.validate()
        if {layer.segment for layer in self.layers} != SEGMENTS:
            raise ValueError('A/B segments are incomplete')
        if not isinstance(self.legs, dict) or set(self.legs) != {'A', 'B'}:
            raise ValueError('A/B legs required')
        def number(value):
            return type(value) in (int, float) and isfinite(value) and abs(value) <= 100000
        for leg in self.legs.values():
            if not isinstance(leg, dict): raise ValueError('Invalid leg')
            for name in ('hip', 'knee', 'ankle', 'toe'):
                point = leg.get(name)
                if not isinstance(point, (list, tuple)) or len(point) != 2 or not all(number(n) for n in point):
                    raise ValueError('Invalid joint')
            if dist(leg['hip'], leg['knee']) <= 1e-9 or dist(leg['knee'], leg['ankle']) <= 1e-9:
                raise ValueError('Invalid bone length')
            if not number(leg.get('sole_y')) or type(leg.get('bend')) is not int or leg['bend'] not in (-1, 1):
                raise ValueError('Invalid sole or bend')
        s = self.settings
        required = {'frames', 'fps', 'stride', 'lift', 'bob', 'hip_drop', 'ground_y', 'stance_fraction'}
        if not isinstance(s, dict) or set(s) != required or not all(number(s[k]) for k in required):
            raise ValueError('Invalid walk settings')
        if type(s['frames']) is not int or not 2 <= s['frames'] <= 240 or not 1 <= s['fps'] <= 100 or any(s[k] < 0 for k in ('stride', 'lift', 'bob')) or not 0 <= s['ground_y'] <= self.canvas[1] or not 0 < s['stance_fraction'] < 1:
            raise ValueError('Walk settings out of range')
        if self.canvas[0] * self.canvas[1] * s['frames'] > 32_000_000:
            raise ValueError('A/B output exceeds memory limit')
        if not isinstance(self.frame_overrides, dict) or len(self.frame_overrides) > s['frames']:
            raise ValueError('Invalid frame overrides')
        for index, override in self.frame_overrides.items():
            if not isinstance(index, str) or not index.isascii() or not index.isdecimal() or str(int(index)) != index or not 0 <= int(index) < s['frames']:
                raise ValueError('Invalid correction frame index')
            if not isinstance(override, dict) or not override or not set(override).issubset({'A', 'B'}):
                raise ValueError('Invalid correction legs')
            for correction in override.values():
                if not isinstance(correction, dict) or set(correction) != {'hip', 'ankle', 'bend', 'foot_angle'}:
                    raise ValueError('Invalid correction')
                for joint in ('hip', 'ankle'):
                    point = correction[joint]
                    if not isinstance(point, (list, tuple)) or len(point) != 2 or not all(number(v) for v in point):
                        raise ValueError('Invalid corrected joint')
                if type(correction['bend']) is not int or correction['bend'] not in (-1, 1) or not number(correction['foot_angle']) or abs(correction['foot_angle']) > 360:
                    raise ValueError('Invalid correction bend or angle')


def ab_from_prototype(data, source_path):
    try:
        rig = ABWalk(canvas=tuple(data['canvas']), source=ABAsset(source_path),
                     layers=[ABLayer(asset_path=l['file'], segment=l['segment']) for l in data['layers']],
                     legs=data['legs'], settings=data['settings'])
        rig.validate()
        return rig
    except (TypeError, KeyError, AttributeError) as exc:
        raise ValueError('Malformed A/B rig') from exc


def ab_from_dict(data):
    try:
        values = dict(data)
        values['source'] = ABAsset(**values['source'])
        layers = []
        for item in values['layers']:
            layer = dict(item)
            edit = layer.get('edit')
            if edit is not None:
                edit = dict(edit)
                for key in ('source', 'mask', 'paint'):
                    edit[key] = ABAsset(**edit[key])
                layer['edit'] = ABEdit(**edit)
            layers.append(ABLayer(**layer))
        values['layers'] = layers
        values['canvas'] = tuple(values['canvas'])
        values['origin'] = tuple(values.get('origin', (0, 0)))
        rig = ABWalk(**values)
        rig.validate()
        return rig
    except (TypeError, KeyError, AttributeError) as exc:
        raise ValueError('Malformed A/B rig') from exc
