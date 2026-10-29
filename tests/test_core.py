import json
from pathlib import Path

import pytest


def test_defaults_and_complete_validation():
    from anime_rpg_sprite_studio.core.models import Project, Character, Direction
    p = Project(name="測試")
    c = Character(name="勇者")
    p.characters.append(c)
    assert list(Direction) == [Direction.FRONT, Direction.LEFT, Direction.RIGHT, Direction.BACK]
    assert c.clips[0].fps == 8
    assert c.clips[0].validate() == []
    assert len(c.clips[0].validate(complete=True)) == 4


@pytest.mark.parametrize("fps", [0, 61, True, 1.5])
def test_invalid_fps(fps):
    from anime_rpg_sprite_studio.core.models import AnimationClip
    with pytest.raises(ValueError):
        AnimationClip(fps=fps)


def test_frame_invariants():
    from anime_rpg_sprite_studio.core.models import SpriteFrame, Direction, AnimationClip
    f = SpriteFrame(asset_path="assets/a.png", direction=Direction.FRONT, index=0)
    assert f.pivot == (0.5, 0.0)
    clip = AnimationClip(frames=[f, f])
    assert "Duplicate frame" in clip.validate()
    with pytest.raises(ValueError):
        SpriteFrame(asset_path="../secret.png", direction=Direction.FRONT, index=0)
    with pytest.raises(ValueError):
        SpriteFrame(asset_path="a.png", direction=Direction.FRONT, index=4)


def test_repository_roundtrip_and_missing_assets(tmp_path):
    from anime_rpg_sprite_studio.core.models import Project, Character, SpriteFrame, Direction
    from anime_rpg_sprite_studio.core.project_repository import ProjectRepository
    p = Project(name="角色專案", characters=[Character(name="勇者")])
    p.active_character_id = p.characters[0].id
    p.characters[0].clips[0].frames.append(SpriteFrame(asset_path="assets/missing.png", direction=Direction.FRONT, index=0))
    path = tmp_path / "中文" / "project.json"
    repo = ProjectRepository()
    repo.save(p, path)
    loaded = repo.load(path)
    assert loaded == p
    assert repo.missing_assets(loaded, path) == ["assets/missing.png"]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = 99
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        repo.load(path)


@pytest.mark.parametrize("content", ["{", "[]", '{"schema_version":1}'])
def test_corrupt_projects(tmp_path, content):
    from anime_rpg_sprite_studio.core.project_repository import ProjectRepository
    path = tmp_path / "project.json"
    path.write_text(content)
    with pytest.raises(ValueError):
        ProjectRepository().load(path)


def test_mock_offline():
    from anime_rpg_sprite_studio.ai.mock_provider import MockProvider
    from anime_rpg_sprite_studio.ai.contracts import GenerationRequest
    from decimal import Decimal
    provider = MockProvider()
    request = GenerationRequest(prompt="勇者")
    assert provider.estimate(request).estimated_cost == Decimal("0")
    result = provider.generate(request)
    assert result == provider.generate(request)
    from PIL import Image
    from io import BytesIO
    image = Image.open(BytesIO(result.png))
    assert image.mode == "RGBA" and image.size == (256, 256)


def test_core_has_no_qt_or_network_imports():
    import ast
    root = Path(__file__).parents[1] / "src/anime_rpg_sprite_studio/core"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("PySide6", "httpx", "keyring"))


def test_rejects_bad_description_before_replacing_project(tmp_path):
    from anime_rpg_sprite_studio.core.project_service import ProjectService
    service = ProjectService()
    service.add_character()
    path = tmp_path / "project.json"
    service.save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["characters"][0]["description"] = 42
    path.write_text(json.dumps(data), encoding="utf-8")
    previous = service.project
    with pytest.raises(ValueError):
        service.load(path)
    assert service.project is previous


def test_fixed_pivot():
    from anime_rpg_sprite_studio.core.models import SpriteFrame, Direction
    with pytest.raises(ValueError):
        SpriteFrame(asset_path="a.png", direction=Direction.FRONT, index=0, pivot=(0, 1))


def test_failed_replace_preserves_saved_file(tmp_path, monkeypatch):
    from anime_rpg_sprite_studio.core.project_repository import ProjectRepository
    from anime_rpg_sprite_studio.core.models import Project
    import os
    repo = ProjectRepository()
    path = tmp_path / "project.json"
    repo.save(Project(name="original"), path)
    original = path.read_bytes()
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        repo.save(Project(name="new"), path)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]
