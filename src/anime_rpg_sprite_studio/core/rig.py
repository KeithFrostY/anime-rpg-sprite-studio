"""Serializable rig metadata. Joint coordinates use the image's top-left origin."""
from dataclasses import dataclass, field
from math import isfinite

from .models import Direction, validate_asset_path

PARTS = {"head", "body", "left_arm", "right_arm", "left_leg", "right_leg"}


@dataclass
class WalkParameters:
    arm_swing: int = 12
    leg_swing: int = 10
    bob: int = 2

    def validate(self):
        for value, maximum in ((self.arm_swing, 30), (self.leg_swing, 25), (self.bob, 6)):
            if type(value) is not int or not isfinite(value) or not 0 <= value <= maximum:
                raise ValueError("步態參數超出範圍：手臂 0–30°、腿部 0–25°、起伏 0–6 px")


@dataclass
class Layer:
    part: str
    asset_path: str
    joint: tuple[int, int]

    def validate(self):
        if self.part not in PARTS:
            raise ValueError("Unknown layer part")
        validate_asset_path(self.asset_path)
        if not isinstance(self.joint, (tuple, list)) or len(self.joint) != 2 or any(type(v) is not int or not 0 <= v <= 255 for v in self.joint):
            raise ValueError("Joint must use integer image coordinates 0–255")


@dataclass
class TemplateView:
    direction: Direction
    layers: list[Layer]

    def validate(self):
        self.direction = Direction(self.direction)
        if len(self.layers) != 6 or {layer.part for layer in self.layers} != PARTS:
            raise ValueError("每方向必須包含六個不同圖層")
        for layer in self.layers:
            layer.validate()


@dataclass
class CharacterTemplate:
    name: str
    views: list[TemplateView]
    parameters: WalkParameters = field(default_factory=WalkParameters)
    template_version: int = 1

    def validate(self):
        if type(self.template_version) is not int or self.template_version != 1:
            raise ValueError("Unsupported template version")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Template name required")
        for view in self.views:
            view.validate()
        if len(self.views) != 4 or {view.direction for view in self.views} != set(Direction):
            raise ValueError("模板必須明確提供 Front、Left、Right、Back")
        self.parameters.validate()


def template_from_dict(raw: dict) -> CharacterTemplate:
    try:
        if not isinstance(raw, dict):
            raise ValueError("Template must be an object")
        data = dict(raw)
        views = []
        for raw_view in data.pop("views"):
            layers = []
            for item in raw_view["layers"]:
                layer = dict(item)
                layer["joint"] = tuple(layer["joint"])
                layers.append(Layer(**layer))
            views.append(TemplateView(Direction(raw_view["direction"]), layers))
        parameters = WalkParameters(**data.pop("parameters", {}))
        template = CharacterTemplate(**data, views=views, parameters=parameters)
        template.validate()
        return template
    except (TypeError, KeyError, AttributeError) as exc:
        raise ValueError("Malformed template metadata") from exc
