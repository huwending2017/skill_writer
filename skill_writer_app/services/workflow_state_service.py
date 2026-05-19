from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from skill_writer_app.services.mojibake_repair import repair_tree


class WorkflowStateService:
    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path

    def load(self) -> dict[str, dict[str, str]]:
        if not self.state_path.exists():
            return {}
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        repaired = repair_tree(data)
        if repaired != data:
            self.state_path.write_text(json.dumps(repaired, ensure_ascii=False, indent=2), encoding="utf-8")
            data = repaired
        if not isinstance(data, dict):
            return {}
        result: dict[str, dict[str, str]] = {}
        for key, value in data.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            step = value.get("step")
            applied_at = value.get("applied_at")
            if isinstance(step, str) and isinstance(applied_at, str):
                result[key] = {"step": step, "applied_at": applied_at}
        return result

    def save(self, state: dict[str, dict[str, str]]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, target_key: str) -> dict[str, str] | None:
        if not target_key:
            return None
        return self.load().get(target_key)

    def set(self, target_key: str, step: str) -> None:
        if not target_key:
            return
        state = self.load()
        state[target_key] = {
            "step": step,
            "applied_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.save(state)

    def clear(self, target_key: str) -> None:
        if not target_key:
            return
        state = self.load()
        if target_key in state:
            del state[target_key]
            self.save(state)
