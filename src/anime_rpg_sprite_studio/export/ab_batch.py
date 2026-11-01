"""Sequential, independently committed A/B exports from a project snapshot."""
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from ..core.project_repository import ProjectRepository
from .ab_export import export_ab, ABExportCancelled


@dataclass(frozen=True)
class BatchItem:
    id: str
    name: str
    rig: object


@dataclass(frozen=True)
class BatchSnapshot:
    root: Path
    items: tuple[BatchItem, ...]


@dataclass(frozen=True)
class BatchResult:
    id: str
    name: str
    status: str
    output: Path | None = None
    message: str = ''


def capture_batch(service, character_ids):
    if service.path is None: raise ValueError('請先儲存專案')
    if not character_ids or len(character_ids) != len(set(character_ids)):
        raise ValueError('請選擇至少一個不同的角色')
    characters = {c.id: c for c in service.project.characters}
    if any(id not in characters for id in character_ids): raise ValueError('角色不存在')
    return BatchSnapshot(service.path.parent.resolve(), tuple(
        BatchItem(id, characters[id].name, deepcopy(characters[id].ab_walk)) for id in character_ids))


def export_batch(snapshot, destination, cancel=None, progress=None, on_result=None):
    cancel = cancel if cancel is not None else Event()
    destination = Path(destination)
    if not destination.is_dir(): raise ValueError('輸出位置必須是現有資料夾')
    results = []; total = len(snapshot.items)
    if not total: raise ValueError('沒有選擇角色')
    def update(percent, index, message):
        if progress: progress(percent, index, message)
    for index, item in enumerate(snapshot.items):
        if cancel.is_set():
            result = BatchResult(item.id, item.name, 'cancelled', message='已取消／未處理')
        else:
            try:
                if item.rig is None: raise ValueError('角色沒有已套用的 A/B 骨架')
                item.rig.validate()
                assets = {}
                for ref in (item.rig.source, *item.rig.layers):
                    if cancel.is_set(): raise ABExportCancelled('已取消')
                    path = ProjectRepository()._asset(snapshot.root, ref.asset_path)
                    with path.open('rb') as stream: data = stream.read(32 * 1024 * 1024 + 1)
                    if len(data) > 32 * 1024 * 1024: raise ValueError('素材過大')
                    assets[ref.asset_path] = data
                output = export_ab(item.rig, assets, destination, cancel,
                    lambda percent, message: update(int((index + percent/100) * 100 / total), index, message))
                result = BatchResult(item.id, item.name, 'success', output, '已完成')
            except ABExportCancelled:
                result = BatchResult(item.id, item.name, 'cancelled', message='已取消／未處理')
            except (OSError, ValueError) as exc:
                result = BatchResult(item.id, item.name, 'failed', message=str(exc))
            except Exception:
                result = BatchResult(item.id, item.name, 'failed', message='處理角色時發生錯誤')
        results.append(result)
        if on_result: on_result(index, result)
        if not cancel.is_set(): update(round((index+1)*100/total), index, result.message)
    return results
