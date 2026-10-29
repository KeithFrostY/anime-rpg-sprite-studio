"""Explicit template loading; no AI, inference, or automatic direction synthesis."""
from io import BytesIO
import json
from pathlib import Path
from threading import Event

from PIL import Image, ImageDraw

from ..core.models import Direction
from ..core.rig import CharacterTemplate, TemplateView, Layer, template_from_dict
from ..rendering.sprite_import import decode_png, normalize_png


def check_cancel(cancel: Event | None):
    if cancel is not None and cancel.is_set():
        raise GenerationCancelled("已取消，原動畫保持不變")


class GenerationCancelled(ValueError):
    pass


def validate_layer(data: bytes) -> bytes:
    normalized = normalize_png(data)
    with Image.open(BytesIO(normalized)) as image:
        if image.getchannel("A").getextrema()[0] == 255:
            raise ValueError("分層素材需要透明背景；不會自動去背")
    return normalized


def load_template_assets(template: CharacterTemplate, root: Path, cancel=None):
    template.validate()
    assets = {}
    root = root.resolve()
    for view in template.views:
        for layer in view.layers:
            check_cancel(cancel)
            path = (root / layer.asset_path).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Template asset escapes directory")
            assets[layer.asset_path] = validate_layer(decode_png(path))
    return template, assets


def load_template(path: Path, cancel=None):
    path = Path(path)
    if path.stat().st_size > 256 * 1024:
        raise ValueError("Template manifest exceeds 256 KiB")
    try:
        template = template_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except RecursionError as exc:
        raise ValueError("Template JSON is too deeply nested") from exc
    return load_template_assets(template, path.parent, cancel)


def demo_template():
    """Diagnostic layered mannequin. All four views drawn explicitly on CPU."""
    assets, views = {}, []
    joints = {"head": (128, 78), "body": (128, 140), "left_arm": (93, 110),
              "right_arm": (163, 110), "left_leg": (113, 178), "right_leg": (143, 178)}
    for direction in Direction:
        layers = []
        order = ["left_leg", "right_leg", "left_arm", "body", "head", "right_arm"]
        if direction == Direction.LEFT:
            order = ["left_arm", "left_leg", "body", "head", "right_leg", "right_arm"]
        elif direction == Direction.RIGHT:
            order = ["right_arm", "right_leg", "body", "head", "left_leg", "left_arm"]
        elif direction == Direction.BACK:
            order = ["left_leg", "right_leg", "left_arm", "right_arm", "body", "head"]
        for part in order:
            image = Image.new("RGBA", (256, 256))
            draw = ImageDraw.Draw(image)
            if part == "head":
                draw.ellipse((100, 28, 156, 84), fill="#e9b790")
                draw.pieslice((98, 25, 158, 81), 180, 360, fill="#493941")
                if direction == Direction.BACK:
                    draw.ellipse((98, 25, 158, 84), fill="#493941")
                else:
                    eyes = [112, 140] if direction == Direction.FRONT else [107] if direction == Direction.LEFT else [145]
                    for x in eyes:
                        draw.ellipse((x, 53, x + 4, 60), fill="#262637")
            elif part == "body":
                draw.rounded_rectangle((96, 86, 160, 182), 12, fill="#637bd6")
                draw.rectangle((98, 165, 158, 177), fill="#48384d")
                if direction == Direction.FRONT:
                    draw.line((128, 92, 128, 163), fill="#d4ddfa", width=3)
            elif part.endswith("arm"):
                x = 85 if part == "left_arm" else 157
                draw.rounded_rectangle((x, 102, x + 14, 164), 6, fill="#e9b790")
                draw.rounded_rectangle((x - 1, 100, x + 15, 126), 6, fill="#637bd6")
            else:
                x = 104 if part == "left_leg" else 134
                draw.rounded_rectangle((x, 175, x + 18, 239), 6, fill="#404454")
                draw.rounded_rectangle((x - 2, 229, x + 20, 246), 4, fill="#292b38")
            stream = BytesIO()
            image.save(stream, format="PNG")
            relative = f"layers/{direction.value}/{part}.png"
            assets[relative] = stream.getvalue()
            layers.append(Layer(part, relative, joints[part]))
        views.append(TemplateView(direction, layers))
    template = CharacterTemplate("離線六層測試人偶（非 AI 成果）", views)
    template.validate()
    return template, assets
