#!/usr/bin/env python3
"""Offline, deterministic walk cycles from manually prepared RGBA layers.

The A and B names always identify the same source artwork. The renderer rotates
and translates each upper/lower leg without scaling it, and translates feet
without rotating them. It cannot paint missing pixels or repair cutout seams.

Example:
    python walkcycle.py --project examples/schematic/rig.json --out output/demo
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Sequence

from PIL import Image, ImageDraw, ImageFont, ImageOps


LEG_NAMES = ("A", "B")
DEFAULT_SETTINGS = {
    "frames": 8,
    "fps": 10,
    "stride": 32,
    "lift": 12,
    "bob": 2,
    "hip_drop": 0,
    "stance_fraction": 0.6,
}
SEGMENTS = {"body"} | {f"{leg}.{part}" for leg in LEG_NAMES for part in ("upper", "lower", "foot")}
FIXED_OUTPUT_NAMES = {"spritesheet.png", "preview.gif", "contact_sheet.png", "metadata.json"}
LEG_COLORS = {"A": (0, 146, 151), "B": (224, 127, 47)}
PREVIEW_BACKGROUND = (236, 239, 242)


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number.")
    return result


def _point(value: Any, name: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must be [x, y].")
    return (_number(value[0], f"{name}.x"), _number(value[1], f"{name}.y"))


def _canvas_size(value: Any) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("canvas must be [width, height] in whole pixels.")
    if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in value):
        raise ValueError("canvas width and height must be positive whole pixels.")
    return tuple(value)


def solve_ik(
    hip: Sequence[float], target: Sequence[float],
    upper_length: float, lower_length: float, bend: int = 1,
) -> tuple[list[float], list[float], bool]:
    """Solve a two-bone chain without stretching, in screen coordinates (+y down).

    bend=+1 selects the forward (+x) knee side for a downward-pointing leg.
    An unreachable target is clamped to the closest point on the reach annulus.
    Coincident endpoints use a deterministic downward direction.
    """
    hx, hy = _point(hip, "hip")
    tx, ty = _point(target, "target")
    upper = _number(upper_length, "upper_length")
    lower = _number(lower_length, "lower_length")
    if upper <= 0 or lower <= 0:
        raise ValueError("upper_length and lower_length must be greater than zero.")
    if isinstance(bend, bool) or bend not in (-1, 1):
        raise ValueError("bend must be +1 or -1.")
    dx, dy = tx - hx, ty - hy
    distance = math.hypot(dx, dy)
    minimum, maximum = abs(upper - lower), upper + lower
    if not math.isfinite(distance) or not math.isfinite(maximum):
        raise ValueError("The joint coordinates or bone lengths are too large.")
    ux, uy = (dx / distance, dy / distance) if distance > 0 else (0.0, 1.0)
    solved_distance = min(maximum, max(minimum, distance))
    limited = not math.isclose(distance, solved_distance, rel_tol=1e-10, abs_tol=1e-8)
    ankle = [hx + ux * solved_distance, hy + uy * solved_distance]
    if solved_distance == 0:  # Equal bones folded back onto the hip.
        return [hx + bend * upper, hy], ankle, limited
    # Normalize before squaring so ordinary large coordinates do not overflow.
    scale = max(upper, lower, solved_distance)
    a, b, d = upper / scale, lower / scale, solved_distance / scale
    along = (a * a - b * b + d * d) / (2 * d)
    across = math.sqrt(max(0.0, a * a - along * along))
    knee = [
        hx + scale * (along * ux + bend * across * uy),
        hy + scale * (along * uy - bend * across * ux),
    ]
    return knee, ankle, limited


def _font(size: int = 14) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _union_bounds(bounds: list[list[int]]) -> list[int] | None:
    if not bounds:
        return None
    return [min(b[0] for b in bounds), min(b[1] for b in bounds),
            max(b[2] for b in bounds), max(b[3] for b in bounds)]


class RigProject:
    """Loaded source images plus a mutable project configuration.

    Change joint/settings values in ``data`` and call pose/render again. Images
    are cached by the exact layer ``file`` string. Reload after changing files.
    """

    def __init__(self, path: Path, data: dict[str, Any]):
        self.path = Path(path).expanduser().resolve()
        self.data = data
        self.images: dict[str, Image.Image] = {}
        self._source_paths: dict[str, Path] = {}
        self._validate()
        for layer in self.data["layers"]:
            filename = layer["file"]
            if filename in self.images:
                continue
            source_path = (self.path.parent / filename).resolve()
            try:
                with Image.open(source_path) as source:
                    if source.size != self.size:
                        raise ValueError(
                            f"Asset {filename!r} has size {source.size}; expected full-canvas {self.size}."
                        )
                    if "A" not in source.getbands() and "transparency" not in source.info:
                        raise ValueError(f"Asset {filename!r} needs an alpha channel; save a transparent RGBA PNG.")
                    self.images[filename] = source.convert("RGBA")
            except (OSError, Image.DecompressionBombError) as error:
                raise ValueError(f"Cannot read asset {filename!r} at {source_path}: {error}") from error
            self._source_paths[filename] = source_path
        self._validate()

    @property
    def size(self) -> tuple[int, int]:
        return _canvas_size(self.data.get("canvas"))

    def _validate(self) -> None:
        if not isinstance(self.data, dict):
            raise ValueError("The project JSON must be an object.")
        width, height = self.size
        settings = self.data.get("settings")
        if not isinstance(settings, dict):
            raise ValueError("settings must be an object.")
        frames = settings.get("frames")
        if isinstance(frames, bool) or not isinstance(frames, int) or not 2 <= frames <= 240:
            raise ValueError("settings.frames must be a whole number from 2 to 240.")
        if width * height * frames > 32_000_000:
            raise ValueError('A/B output exceeds memory limit')
        fps = _number(settings.get("fps"), "settings.fps")
        if not 1 <= fps <= 100:
            raise ValueError("settings.fps must be from 1 to 100 (GIF timing uses 10 ms ticks).")
        for key in ("stride", "lift", "bob"):
            if _number(settings.get(key), f"settings.{key}") < 0:
                raise ValueError(f"settings.{key} must be zero or greater.")
        _number(settings.get("hip_drop"), "settings.hip_drop")
        ground = _number(settings.get("ground_y"), "settings.ground_y")
        if not 0 <= ground <= height:
            raise ValueError(f"settings.ground_y must be between 0 and canvas height {height}.")
        duty = _number(settings.get("stance_fraction"), "settings.stance_fraction")
        if not 0 < duty < 1:
            raise ValueError("settings.stance_fraction must be strictly between 0 and 1.")
        legs = self.data.get("legs")
        if not isinstance(legs, dict) or set(legs) != set(LEG_NAMES):
            raise ValueError("legs must contain exactly A (near) and B (far); keep these IDs fixed.")
        for name in LEG_NAMES:
            leg = legs[name]
            if not isinstance(leg, dict):
                raise ValueError(f"legs.{name} must be an object.")
            points = {joint: _point(leg.get(joint), f"legs.{name}.{joint}")
                      for joint in ("hip", "knee", "ankle", "toe")}
            for start, end in (("hip", "knee"), ("knee", "ankle")):
                length = math.dist(points[start], points[end])
                if not math.isfinite(length) or length <= 1e-9:
                    raise ValueError(f"legs.{name}: {start} and {end} must define a nonzero, finite bone.")
            _number(leg.get("sole_y"), f"legs.{name}.sole_y")
            if isinstance(leg.get("bend"), bool) or leg.get("bend") not in (-1, 1):
                raise ValueError(f"legs.{name}.bend must be +1 or -1.")
        layers = self.data.get("layers")
        if not isinstance(layers, list) or not layers:
            raise ValueError("layers must be a nonempty list ordered from back to front.")
        for index, layer in enumerate(layers):
            if not isinstance(layer, dict):
                raise ValueError(f"layers[{index}] must be an object with file and segment.")
            filename, segment = layer.get("file"), layer.get("segment")
            if not isinstance(filename, str) or not filename.strip():
                raise ValueError(f"layers[{index}].file must name a prepared image.")
            if not isinstance(segment, str) or segment not in SEGMENTS:
                raise ValueError(f"layers[{index}].segment must be body, A.upper/A.lower/A.foot, or B.upper/B.lower/B.foot.")
            if self.images:
                if filename not in self.images:
                    raise ValueError(f"Asset {filename!r} is not loaded. Reload the project after changing file names.")
                if self.images[filename].size != (width, height):
                    raise ValueError(f"Asset {filename!r} must match canvas size {(width, height)}.")
        corrections = self.data.get('frame_overrides', {})
        if type(self.data.get('interpolate', False)) is not bool:
            raise ValueError('Invalid interpolation mode')
        if not isinstance(corrections, dict) or len(corrections) > frames:
            raise ValueError('Invalid frame overrides')
        for index, legs_override in corrections.items():
            if not isinstance(index, str) or not index.isascii() or not index.isdecimal() or str(int(index)) != index or not 0 <= int(index) < frames:
                raise ValueError('Invalid correction frame index')
            if not isinstance(legs_override, dict) or not legs_override or not set(legs_override).issubset(set(LEG_NAMES)):
                raise ValueError('Invalid correction legs')
            for override in legs_override.values():
                if not isinstance(override, dict) or set(override) != {'hip', 'ankle', 'bend', 'foot_angle'}:
                    raise ValueError('Invalid correction')
                for joint in ('hip', 'ankle'):
                    if any(abs(v) > 100000 for v in _point(override[joint], joint)):
                        raise ValueError('Correction outside coordinate bounds')
                if type(override['bend']) is not int or override['bend'] not in (-1, 1) or abs(_number(override['foot_angle'], 'foot_angle')) > 360:
                    raise ValueError('Invalid correction bend or angle')

    def _base_leg(self, phase, name):
        settings = self.data['settings']; source = self.data['legs'][name]
        stride, lift, duty = settings['stride'], settings['lift'], settings['stance_fraction']
        body_y = settings['hip_drop'] + settings['bob'] * math.sin(4 * math.pi * phase)
        local = (phase + (0.0 if name == 'A' else 0.5)) % 1.0
        contact = local < duty
        hip = [float(source['hip'][0]), source['hip'][1] + body_y]
        if contact:
            foot_x, foot_lift = stride * (0.5 - local / duty), 0.0
        else:
            swing = (local - duty) / (1 - duty)
            foot_x, foot_lift = -0.5 * stride * math.cos(math.pi * swing), lift * math.sin(math.pi * swing)
        sole_offset = source['sole_y'] - source['ankle'][1]
        return hip, [hip[0] + foot_x, settings['ground_y'] - sole_offset - foot_lift], contact

    def _interpolated_override(self, phase, name, base_hip, base_ankle):
        count = self.data['settings']['frames']
        corrections = self.data.get('frame_overrides', {})
        keys = sorted(int(key) for key, legs in corrections.items() if name in legs)
        if not keys: return None
        position = phase * count
        for key in keys:
            if math.isclose(position, key, rel_tol=0, abs_tol=1e-8):
                return corrections[str(key)][name]
        previous = next((key for key in reversed(keys) if key < position), keys[-1])
        following = next((key for key in keys if key > position), keys[0])
        left, right = corrections[str(previous)][name], corrections[str(following)][name]
        t = 0.0 if previous == following else ((position - previous) % count) / ((following - previous) % count)
        t = t * t * (3 - 2 * t)
        h0, a0, _ = self._base_leg(previous / count, name)
        h1, a1, _ = self._base_leg(following / count, name)
        def interpolate_point(base, before, after, p0, p1):
            return [base[j] + (before[j] - p0[j]) * (1-t) + (after[j] - p1[j]) * t for j in range(2)]
        delta = (right['foot_angle'] - left['foot_angle'] + 180) % 360 - 180
        angle = (left['foot_angle'] + t * delta + 180) % 360 - 180
        return {'hip': interpolate_point(base_hip, left['hip'], right['hip'], h0, h1),
                'ankle': interpolate_point(base_ankle, left['ankle'], right['ankle'], a0, a1),
                'bend': left['bend'], 'foot_angle': angle}

    def pose(self, phase: float) -> dict[str, Any]:
        """Return fixed-ID leg joints for phase 0..1; any finite phase wraps."""
        self._validate()
        phase = _number(phase, "phase") % 1.0
        settings = self.data["settings"]
        frame_pos = phase * settings['frames']
        frame = round(frame_pos)
        overrides = self.data.get('frame_overrides', {}).get(str(frame % settings['frames']), {}) if math.isclose(frame_pos, frame, rel_tol=0, abs_tol=1e-8) else {}
        body_y = settings["hip_drop"] + settings["bob"] * math.sin(4 * math.pi * phase)
        result: dict[str, Any] = {"phase": phase, "body_offset": [0.0, body_y], "legs": {}}
        for name in LEG_NAMES:
            source = self.data["legs"][name]
            hip, requested, contact = self._base_leg(phase, name)
            override = (self._interpolated_override(phase, name, hip, requested)
                        if self.data.get('interpolate', False) else overrides.get(name))
            if override:
                hip = list(override['hip'])
                requested = list(override['ankle'])
            upper = math.dist(source["hip"], source["knee"])
            lower = math.dist(source["knee"], source["ankle"])
            knee, ankle, limited = solve_ik(hip, requested, upper, lower, override['bend'] if override else source["bend"])
            if override:
                angle = math.radians(override['foot_angle'])
                dx = source['toe'][0] - source['ankle'][0]
                dy = source['toe'][1] - source['ankle'][1]
                toe = [ankle[0] + dx * math.cos(angle) - dy * math.sin(angle),
                       ankle[1] + dx * math.sin(angle) + dy * math.cos(angle)]
            else:
                toe = [ankle[i] + source['toe'][i] - source['ankle'][i] for i in range(2)]
            result["legs"][name] = {
                "hip": hip, "knee": knee, "ankle": ankle, "toe": toe,
                "contact": contact, "limited": limited, "requested_ankle": requested,
            }
            if override:
                result['legs'][name]['foot_angle'] = override['foot_angle']
                if self.data.get('interpolate', False): result['legs'][name]['bend'] = override['bend']
        return result

    def _layer_transform(self, segment: str, pose: dict[str, Any]) -> tuple[float, float, float, float]:
        """Return rigid forward transform (cos, sin, x translation, y translation)."""
        if segment == "body":
            return (1.0, 0.0, *pose["body_offset"])
        name, part = segment.split(".")
        source, target = self.data["legs"][name], pose["legs"][name]
        start, end = {"upper": ("hip", "knee"), "lower": ("knee", "ankle"), "foot": ("ankle", "toe")}[part]
        sx, sy = source[start]
        tx, ty = target[start]
        if part == "foot":
            angle = math.radians(target.get('foot_angle', 0))
            cosine, sine = math.cos(angle), math.sin(angle)
        else:
            angle = math.atan2(target[end][1] - ty, target[end][0] - tx)
            angle -= math.atan2(source[end][1] - sy, source[end][0] - sx)
            cosine, sine = math.cos(angle), math.sin(angle)
        return cosine, sine, tx - cosine * sx + sine * sy, ty - sine * sx - cosine * sy

    def _transform_part(self, image: Image.Image, transform: tuple[float, float, float, float]):
        """Render a part before canvas cropping, so clipping can be measured."""
        box = image.getchannel("A").getbbox()
        if box is None:
            return None
        # Bicubic sampling needs the transparent pixels beside an alpha edge.
        # A tight crop would clamp those samples and harden fractional edges.
        box = (box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2)
        cosine, sine, tx, ty = transform
        corners = [(cosine * x - sine * y + tx, sine * x + cosine * y + ty)
                   for x in (box[0], box[2]) for y in (box[1], box[3])]
        left = math.floor(min(p[0] for p in corners)) - 1
        top = math.floor(min(p[1] for p in corners)) - 1
        right = math.ceil(max(p[0] for p in corners)) + 1
        bottom = math.ceil(max(p[1] for p in corners)) + 1
        inverse = (
            cosine, sine, cosine * (left - tx) + sine * (top - ty) - box[0],
            -sine, cosine, -sine * (left - tx) + cosine * (top - ty) - box[1],
        )
        transformed = image.crop(box).transform(
            (right - left, bottom - top), Image.Transform.AFFINE, inverse,
            resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0),
        )
        actual = transformed.getchannel("A").getbbox()
        if actual is None:
            return None
        bounds = [actual[0] + left, actual[1] + top, actual[2] + left, actual[3] + top]
        return transformed, (left, top), bounds

    def _compose(self, pose: dict[str, Any], body_only: bool = False):
        frame = Image.new("RGBA", self.size)
        bounds = []
        for layer in self.data["layers"]:
            if body_only and layer["segment"] != "body":
                continue
            part = self._transform_part(self.images[layer["file"]], self._layer_transform(layer["segment"], pose))
            if part is None:
                continue
            pixels, (left, top), part_bounds = part
            bounds.append(part_bounds)
            # Composite only the visible intersection; metadata retains the rest.
            x0, y0 = max(0, left), max(0, top)
            x1, y1 = min(self.size[0], left + pixels.width), min(self.size[1], top + pixels.height)
            if x0 < x1 and y0 < y1:
                visible = pixels.crop((x0 - left, y0 - top, x1 - left, y1 - top))
                frame.alpha_composite(visible, dest=(x0, y0))
        return frame, _union_bounds(bounds)

    def _guide(self, pose: dict[str, Any]) -> Image.Image:
        width, height = self.size
        canvas = Image.new("RGBA", self.size, (247, 248, 250, 255))
        body, _ = self._compose(pose, body_only=True)
        muted = ImageOps.grayscale(body).convert("RGBA")
        muted.putalpha(body.getchannel("A").point(lambda a: round(a * 0.28)))
        canvas.alpha_composite(muted)
        draw = ImageDraw.Draw(canvas)
        line_width = max(2, round(width / 160))
        radius = max(3, round(width / 100))
        font = _font(max(10, round(width / 32)))
        ground = self.data["settings"]["ground_y"]
        draw.line((0, ground, width, ground), fill=(171, 181, 190), width=1)
        for name in ("B", "A"):
            leg, color = pose["legs"][name], LEG_COLORS[name]
            points = [tuple(leg[j]) for j in ("hip", "knee", "ankle", "toe")]
            draw.line(points, fill=color, width=line_width, joint="curve")
            for x, y in points:
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
            x, y = leg["knee"]
            draw.text((min(width - 30, max(2, x + radius + 3)), y - 8), name, fill=color, font=font)
            if leg["limited"]:
                x, y = leg["requested_ankle"]
                draw.line((x - 5, y - 5, x + 5, y + 5), fill=(195, 48, 67), width=2)
                draw.line((x - 5, y + 5, x + 5, y - 5), fill=(195, 48, 67), width=2)
        draw.text((8, 8), "A near", fill=LEG_COLORS["A"], font=font)
        draw.text((8, 10 + max(14, round(width / 25))), "B far", fill=LEG_COLORS["B"], font=font)
        return canvas

    def render(self, phase: float, scale: float = 1.0, guides: bool = False) -> Image.Image:
        """Render RGBA pixels at a fixed origin, optionally with pose guides."""
        scale = _number(scale, "scale")
        if scale <= 0:
            raise ValueError("scale must be greater than zero.")
        pose = self.pose(phase)
        image = self._guide(pose) if guides else self._compose(pose)[0]
        if scale != 1.0:
            size = (max(1, round(self.size[0] * scale)), max(1, round(self.size[1] * scale)))
            image = image.resize(size, Image.Resampling.LANCZOS)
        return image

    def export(self, out_dir: str | Path) -> dict[str, Any]:
        """Write a complete export into a new or empty directory.

        Existing contents are never overwritten by this method. The explicit
        CLI --overwrite option stages a fresh export and replaces known outputs.
        """
        self._validate()
        output = Path(out_dir).expanduser()
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise FileExistsError(f"Output {output} must be a new or empty directory. Use another folder or explicit CLI --overwrite.")
        settings = self.data["settings"]
        count, fps = settings["frames"], settings["fps"]
        frames, guide_frames, frame_info, warnings = [], [], [], []
        width, height = self.size
        for index in range(count):
            phase = index / count
            pose = self.pose(phase)
            frame, bounds = self._compose(pose)
            clipped = bool(bounds and (bounds[0] < 0 or bounds[1] < 0 or bounds[2] > width or bounds[3] > height))
            reach = {}
            for name in LEG_NAMES:
                leg, source = pose["legs"][name], self.data["legs"][name]
                upper, lower = math.dist(source["hip"], source["knee"]), math.dist(source["knee"], source["ankle"])
                reach[name] = {
                    "upper_length": upper, "lower_length": lower,
                    "minimum_reach": abs(upper - lower), "maximum_reach": upper + lower,
                    "requested_distance": math.dist(leg["hip"], leg["requested_ankle"]),
                    "error_pixels": math.dist(leg["ankle"], leg["requested_ankle"]),
                    "limited": leg["limited"],
                }
                if leg["limited"]:
                    warnings.append(f"Frame {index:03d}, leg {name}: target unreachable by {reach[name]['error_pixels']:.2f} px; bone lengths preserved, so foot contact may be lost.")
            if clipped:
                warnings.append(f"Frame {index:03d}: artwork extends outside canvas; unclipped bounds are {bounds}. Increase the prepared canvas or adjust the motion.")
            frame_info.append({
                "index": index, "phase": phase, "file": f"frame_{index:03d}.png",
                "guide": f"guides/guide_{index:03d}.png", "body_offset": pose["body_offset"],
                "legs": pose["legs"], "reach_report": reach,
                "unclipped_bounds": bounds, "clipped": clipped,
            })
            frames.append(frame)
            guide_frames.append(self._guide(pose))
        durations = [10 * (round((i + 1) * 100 / fps) - round(i * 100 / fps)) for i in range(count)]
        metadata = {
            "format_version": 1, "project": self.path.name, "canvas": list(self.size),
            "settings": copy.deepcopy(settings), "leg_identity": {"A": "near", "B": "far"},
            "loop": {"duplicate_closing_frame": False, "preview_durations_ms": durations},
            "spritesheet": {"file": "spritesheet.png", "columns": 4, "rows": math.ceil(count / 4)},
            "frames": frame_info, "warnings": warnings,
            "notes": [
                "Production PNGs have transparency; preview GIF and contact sheet use an opaque neutral background.",
                "Foot rotations may be supplied per frame. Body, hair, skirt and held objects move only as their assigned rigid layers.",
                "Unclipped bounds are measured from transformed source alpha before canvas cropping.",
                "GIF timing is rounded to 10 ms ticks; identical consecutive GIF frames may be combined by the encoder.",
            ],
        }
        output.mkdir(parents=True, exist_ok=True)
        (output / "guides").mkdir(exist_ok=True)
        sheet = Image.new("RGBA", (4 * width, math.ceil(count / 4) * height))
        for index, (frame, guide) in enumerate(zip(frames, guide_frames)):
            frame.save(output / frame_info[index]["file"])
            guide.save(output / frame_info[index]["guide"])
            sheet.alpha_composite(frame, ((index % 4) * width, (index // 4) * height))
        sheet.save(output / "spritesheet.png")
        self._save_preview(frames, durations, output / "preview.gif")
        self._contact_sheet(frames, frame_info).save(output / "contact_sheet.png")
        (output / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        return metadata

    def _save_preview(self, frames: list[Image.Image], durations: list[int], path: Path) -> None:
        opaque = []
        for frame in frames:
            image = Image.new("RGB", self.size, PREVIEW_BACKGROUND)
            image.paste(frame, mask=frame.getchannel("A"))
            opaque.append(image)
        # One shared palette reduces color flicker between independently quantized frames.
        thumb_width = min(128, self.size[0])
        thumb_height = max(1, round(self.size[1] * thumb_width / self.size[0]))
        sample = Image.new("RGB", (thumb_width, thumb_height * len(frames)))
        for index, frame in enumerate(opaque):
            sample.paste(frame.resize((thumb_width, thumb_height)), (0, index * thumb_height))
        palette = sample.quantize(colors=256)
        quantized = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in opaque]
        quantized[0].save(path, save_all=True, append_images=quantized[1:], duration=durations,
                          loop=0, disposal=2, optimize=False)

    def _contact_sheet(self, frames: list[Image.Image], info: list[dict[str, Any]]) -> Image.Image:
        cell_width = min(self.size[0], 256)
        art_height = max(1, round(self.size[1] * cell_width / self.size[0]))
        label_height = 38
        cell_height = art_height + label_height
        sheet = Image.new("RGB", (cell_width * 4, cell_height * math.ceil(len(frames) / 4)), PREVIEW_BACKGROUND)
        draw, font = ImageDraw.Draw(sheet), _font(11)
        for index, (frame, data) in enumerate(zip(frames, info)):
            x, y = (index % 4) * cell_width, (index // 4) * cell_height
            thumb = frame.resize((cell_width, art_height), Image.Resampling.LANCZOS)
            sheet.paste(thumb, (x, y), thumb.getchannel("A"))
            draw.text((x + 5, y + art_height + 3), f"{index:02d}  phase {data['phase']:.3f}", fill=(50, 60, 70), font=font)
            state = "  ".join(f"{name}: {'stance' if data['legs'][name]['contact'] else 'swing'}" for name in LEG_NAMES)
            draw.text((x + 5, y + art_height + 18), state, fill=(70, 80, 90), font=font)
            draw.rectangle((x, y, x + cell_width - 1, y + cell_height - 1), outline=(204, 211, 218))
        return sheet


def load_project(path: str | Path) -> RigProject:
    """Load project JSON and full-canvas RGBA assets relative to that JSON."""
    path = Path(path).expanduser().resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read project {path}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError("The project JSON must be an object.")
    _, height = _canvas_size(data.get("canvas"))
    if "settings" not in data:
        data["settings"] = {}
    if isinstance(data["settings"], dict):
        for key, value in {**DEFAULT_SETTINGS, "ground_y": height - 1}.items():
            data["settings"].setdefault(key, value)
    return RigProject(path, data)


def _export_overwrite(project: RigProject, output: Path) -> dict[str, Any]:
    """Stage first, then replace only the tool's own recognized output files."""
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise ValueError("--out must be a directory, not a symlink or a file.")
    guides = output / "guides"
    if guides.is_symlink() or (guides.exists() and not guides.is_dir()):
        raise ValueError("The guides output path must be a directory, not a symlink or file.")
    project._validate()
    known = {output / name for name in FIXED_OUTPUT_NAMES}
    for index in range(project.data["settings"]["frames"]):
        known.update((output / f"frame_{index:03d}.png", guides / f"guide_{index:03d}.png"))
    for folder, pattern in ((output, r"frame_\d{3,}\.png"), (guides, r"guide_\d{3,}\.png")):
        if folder.is_dir():
            known.update(path for path in folder.iterdir() if re.fullmatch(pattern, path.name))
    protected = {project.path} | set(project._source_paths.values())
    for target in known:
        if target.resolve() in protected:
            raise ValueError(f"Refusing to overwrite source project/asset {target}. Choose a separate output folder.")
        if target.exists() and not target.is_file():
            raise ValueError(f"Cannot replace output {target}: it is not a regular file.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="walkcycle-export-", dir=output.parent) as temporary:
        staged = Path(temporary) / "result"
        metadata = project.export(staged)
        generated = [path for path in staged.rglob("*") if path.is_file()]
        output.mkdir(exist_ok=True)
        guides.mkdir(exist_ok=True)
        installed = set()
        for source in generated:
            target = output / source.relative_to(staged)
            os.replace(source, target)
            installed.add(target)
        for stale in known - installed:
            if stale.is_file() or stale.is_symlink():
                stale.unlink()
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True, type=Path, help="Path to prepared rig JSON")
    parser.add_argument("--out", required=True, type=Path, help="New/empty export directory")
    parser.add_argument("--frames", type=int, help="2..240 frames; no duplicate closing frame")
    parser.add_argument("--fps", type=float, help="Preview speed, 1..100 fps")
    for name in ("stride", "lift", "bob", "hip-drop"):
        parser.add_argument(f"--{name}", type=float, help=f"Override {name} in source pixels")
    parser.add_argument("--overwrite", action="store_true", help="Replace known generated outputs, preserving other files")
    arguments = parser.parse_args(argv)
    try:
        project = load_project(arguments.project)
        for key in ("frames", "fps", "stride", "lift", "bob", "hip_drop"):
            value = getattr(arguments, key)
            if value is not None:
                project.data["settings"][key] = value
        metadata = _export_overwrite(project, arguments.out) if arguments.overwrite else project.export(arguments.out)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Error: {error}\n")
    print(f"Exported {len(metadata['frames'])} PNG frames, spritesheet, preview GIF, guides and metadata to {arguments.out}")
    for warning in metadata["warnings"]:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
