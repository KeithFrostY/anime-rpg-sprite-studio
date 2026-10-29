from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from .models import Project, Character, AnimationClip, SpriteFrame, asset_references
from .rig import template_from_dict


class ProjectRepository:
    def _asset(self, root: Path, relative: str) -> Path:
        target = (root / relative).resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError("Asset escapes project directory")
        return target

    def save(self, project: Project, path: Path) -> None:
        path = Path(path)
        project.validate()
        for ref in asset_references(project):
            self._asset(path.parent, ref.asset_path)
        payload = asdict(project)
        payload["created_at"] = project.created_at.isoformat()
        payload["updated_at"] = project.updated_at.isoformat()
        text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
                temp = Path(stream.name)
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if temp is not None and temp.exists():
                temp.unlink()

    def load(self, path: Path) -> Project:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data.get("schema_version") not in (1, 2):
                raise ValueError("Unsupported schema version")
            data["schema_version"] = 2
            for key in ("id", "name", "characters", "created_at", "updated_at"):
                if key not in data:
                    raise ValueError(f"Missing field: {key}")
            characters = []
            for raw in data.pop("characters"):
                template = raw.pop("template", None)
                if template is not None:
                    template = template_from_dict(template)
                clips = []
                for item in raw.pop("clips"):
                    frames = []
                    for f in item.pop("frames"):
                        f["pivot"] = tuple(f["pivot"])
                        frames.append(SpriteFrame(**f))
                    clips.append(AnimationClip(**item, frames=frames))
                characters.append(Character(**raw, clips=clips, template=template))
            for key in ("created_at", "updated_at"):
                data[key] = datetime.fromisoformat(data[key])
            project = Project(**data, characters=characters)
            project.validate()
            self.missing_assets(project, Path(path))
            return project
        except (TypeError, KeyError, AttributeError, OverflowError) as exc:
            raise ValueError("Malformed project data") from exc

    def missing_assets(self, project: Project, path: Path) -> list[str]:
        return [f.asset_path for f in asset_references(project)
                if not self._asset(Path(path).parent, f.asset_path).is_file()]
