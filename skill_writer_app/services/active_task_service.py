from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from skill_writer_app.services.mojibake_repair import repair_tree


class ActiveTaskService:
    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path

    def load(self) -> dict[str, dict[str, Any]]:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        repaired = repair_tree(data)
        if repaired != data:
            self.state_path.write_text(json.dumps(repaired, ensure_ascii=False, indent=2), encoding="utf-8")
            data = repaired
        runs = data.get("runs", data)
        if not isinstance(runs, dict):
            return {}
        normalized = {str(key): value for key, value in runs.items() if isinstance(value, dict)}
        changed = False
        step_names = {
            "develop": "技能开发",
            "audit": "本地预审",
            "compile": "本地编译",
            "test": "技能测试",
            "preview": "预览回写",
            "copy": "写入 Excel 副本",
            "real": "写回正式 Excel",
        }
        for item in normalized.values():
            task_name = str(item.get("task_name", "") or "")
            if task_name and set(task_name) == {"?"}:
                item["task_name"] = step_names.get(str(item.get("step", "")), "任务")
                changed = True
        if changed:
            self.save(normalized)
        return normalized

    def save(self, runs: dict[str, dict[str, Any]]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"runs": runs}
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def upsert(self, target_key: str, info: dict[str, Any]) -> None:
        if not target_key:
            return
        runs = self.load()
        now = self._now()
        current = runs.get(target_key, {})
        current.update(info)
        current.setdefault("started_at", now)
        current["updated_at"] = now
        runs[target_key] = current
        self.save(runs)

    def update(self, target_key: str, **updates: Any) -> None:
        if not target_key:
            return
        runs = self.load()
        if target_key not in runs:
            return
        runs[target_key].update(updates)
        runs[target_key]["updated_at"] = self._now()
        self.save(runs)

    def clear(self, target_key: str) -> None:
        if not target_key:
            return
        runs = self.load()
        if target_key in runs:
            del runs[target_key]
            self.save(runs)

    def find_resumable(
        self,
        *,
        step: str,
        target_keys: list[str],
        workspace_root: str,
        prompt_hash: str = "",
        allow_workspace_fallback: bool = True,
    ) -> tuple[str, dict[str, Any]] | None:
        runs = self.load()
        allowed_status = {"running", "interrupted", "failed"}

        for key in target_keys:
            item = runs.get(key)
            if self._is_resumable(item, step, allowed_status):
                return key, item

        if not allow_workspace_fallback:
            return None

        normalized_workspace = self._normalize_path(workspace_root)
        candidates: list[tuple[str, dict[str, Any]]] = []
        for key, item in runs.items():
            if not self._is_resumable(item, step, allowed_status):
                continue
            if normalized_workspace and self._normalize_path(str(item.get("workspace_root", ""))) != normalized_workspace:
                continue
            if prompt_hash and item.get("prompt_hash") != prompt_hash:
                continue
            candidates.append((key, item))

        candidates.sort(key=lambda pair: str(pair[1].get("updated_at", "")), reverse=True)
        return candidates[0] if candidates else None

    def _is_resumable(self, item: dict[str, Any] | None, step: str, allowed_status: set[str]) -> bool:
        return bool(item and item.get("step") == step and item.get("status") in allowed_status)

    def _normalize_path(self, value: str) -> str:
        if not value:
            return ""
        try:
            return str(Path(value).resolve()).lower()
        except OSError:
            return str(Path(value)).lower()

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
