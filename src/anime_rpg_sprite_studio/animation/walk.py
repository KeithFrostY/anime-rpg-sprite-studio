"""Deterministic CPU affine transforms, alpha composition, fixed four-pose walk."""
from dataclasses import dataclass
from io import BytesIO
from threading import Event
from PIL import Image

from ..core.models import Direction
from ..core.rig import CharacterTemplate
from .templates import check_cancel, validate_layer, GenerationCancelled


@dataclass(frozen=True)
class GeneratedWalk:
    frames: dict[Direction, dict[int, bytes]]
    warnings: tuple[str, ...]


def generate_walk(template: CharacterTemplate, assets: dict[str, bytes], cancel: Event | None = None) -> GeneratedWalk:
    template.validate()
    decoded = {}
    for view in template.views:
        for layer in view.layers:
            check_cancel(cancel)
            if layer.asset_path not in assets:
                raise ValueError(f"Missing layer: {layer.asset_path}")
            data = validate_layer(assets[layer.asset_path])
            with Image.open(BytesIO(data)) as image:
                decoded[layer.asset_path] = image.copy()
    frames, warnings = {}, []
    p = template.parameters
    for view in template.views:
        frames[view.direction] = {}
        for index, phase in enumerate((1, 0, -1, 0)):
            canvas = Image.new("RGBA", (768, 768))
            for layer in view.layers:
                check_cancel(cancel)
                part = layer.part
                angle = 0
                if part.endswith("arm"):
                    angle = p.arm_swing * phase * (1 if part == "left_arm" else -1)
                elif part.endswith("leg"):
                    angle = p.leg_swing * phase * (-1 if part == "left_leg" else 1)
                padded = Image.new("RGBA", (768, 768))
                padded.paste(decoded[layer.asset_path], (256, 256))
                rotated = padded.rotate(angle, resample=Image.Resampling.BICUBIC,
                                        center=(256 + layer.joint[0], 256 + layer.joint[1]))
                dy = -p.bob if index in (1, 3) and not part.endswith("leg") else 0
                if dy:
                    moved = Image.new("RGBA", (768, 768))
                    moved.paste(rotated, (0, dy))
                    rotated = moved
                canvas = Image.alpha_composite(canvas, rotated)
            bounds = canvas.getchannel("A").getbbox()
            if bounds and (bounds[0] < 256 or bounds[1] < 256 or bounds[2] > 512 or bounds[3] > 512):
                warnings.append(f"{view.direction.value} 幀 {index}：內容超出畫布並已裁切")
            image = canvas.crop((256, 256, 512, 512))
            stream = BytesIO()
            image.save(stream, format="PNG")
            frames[view.direction][index] = stream.getvalue()
    check_cancel(cancel)
    return GeneratedWalk(frames, tuple(warnings))
