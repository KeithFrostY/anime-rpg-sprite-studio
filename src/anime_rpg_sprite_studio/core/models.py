from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import PureWindowsPath
from uuid import uuid4
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .rig import CharacterTemplate


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_asset_path(path: str) -> None:
    p = PureWindowsPath(path)
    if not path or p.is_absolute() or p.drive or p.root or ".." in p.parts or ":" in path:
        raise ValueError("Asset path must stay inside the project")


class Direction(StrEnum):
    FRONT = "front"
    LEFT = "left"
    RIGHT = "right"
    BACK = "back"


@dataclass
class SpriteFrame:
    asset_path: str
    direction: Direction
    index: int
    id: str = field(default_factory=new_id)
    width: int = 256
    height: int = 256
    mode: str = "RGBA"
    pivot: tuple[float, float] = (0.5, 0.0)

    def __post_init__(self):
        validate_asset_path(self.asset_path)
        self.direction = Direction(self.direction)
        if type(self.index) is not int or not 0 <= self.index <= 3:
            raise ValueError("Frame index must be 0–3")
        if (self.width, self.height, self.mode) != (256, 256, "RGBA"):
            raise ValueError("Frames require 256x256 RGBA")
        if self.pivot != (0.5, 0.0):
            raise ValueError("Pivot must be foot center (0.5, 0.0)")


@dataclass
class AnimationClip:
    id: str = field(default_factory=new_id)
    name: str = "Walk"
    fps: int = 8
    loop: bool = True
    frames: list[SpriteFrame] = field(default_factory=list)

    def __post_init__(self):
        if type(self.fps) is not int or not 1 <= self.fps <= 60:
            raise ValueError("FPS must be an integer from 1 to 60")
        if self.name != "Walk":
            raise ValueError("Only Walk is supported")
        if type(self.loop) is not bool or not isinstance(self.id, str) or not self.id:
            raise ValueError("Invalid clip metadata")

    def validate(self, complete: bool = False) -> list[str]:
        self.__post_init__()
        errors = []
        keys = [(f.direction, f.index) for f in self.frames]
        for frame in self.frames:
            frame.__post_init__()
        if len(keys) != len(set(keys)):
            errors.append("Duplicate frame")
        if complete:
            for direction in Direction:
                if sorted(i for d, i in keys if d == direction) != [0, 1, 2, 3]:
                    errors.append(f"{direction.value}: requires four frames")
        return errors


@dataclass
class Character:
    name: str = "新角色"
    id: str = field(default_factory=new_id)
    description: str = ""
    style_profile: str = "日系動漫 RPG / 3–4 頭身 / 2D 斜俯視"
    clips: list[AnimationClip] = field(default_factory=lambda: [AnimationClip()])
    template: CharacterTemplate | None = None


@dataclass
class Project:
    name: str = "未命名專案"
    id: str = field(default_factory=new_id)
    schema_version: int = 2
    characters: list[Character] = field(default_factory=list)
    active_character_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def validate(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 2:
            raise ValueError("Unsupported schema version")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Project name is required")
        ids = [c.id for c in self.characters]
        if len(set(ids)) != len(ids) or (self.active_character_id is not None and self.active_character_id not in ids):
            raise ValueError("Invalid character references")
        for dt in (self.created_at, self.updated_at):
            if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
                raise ValueError("Timestamps must use UTC")
        for c in self.characters:
            if not isinstance(c.name, str) or not c.name.strip() or not c.clips:
                raise ValueError("Character name and clip are required")
            if not all(isinstance(value, str) for value in (c.id, c.description, c.style_profile)):
                raise ValueError("Invalid character metadata")
            for clip in c.clips:
                if clip.validate():
                    raise ValueError("Invalid animation frames")
            if c.template is not None:
                c.template.validate()


def asset_references(project: Project):
    """Objects with asset_path, covering animation frames and template layers."""
    for character in project.characters:
        for clip in character.clips:
            yield from clip.frames
        if character.template is not None:
            for view in character.template.views:
                yield from view.layers
