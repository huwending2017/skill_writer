from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class TaskHandoffService:
    STATE_NAME = "task_state.json"
    HANDOFF_NAME = "task_handoff.md"
    MEMORY_NAME = "task_memory.json"

    def write(self, task_dir: str, payload: dict[str, Any]) -> tuple[Path, Path] | None:
        if not task_dir:
            return None
        root = Path(task_dir)
        if not root.exists() or not root.is_dir():
            return None

        data = dict(payload)
        data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state_path = root / self.STATE_NAME
        handoff_path = root / self.HANDOFF_NAME
        memory_path = root / self.MEMORY_NAME
        state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        handoff_path.write_text(self.render_markdown(data), encoding="utf-8")
        memory_path.write_text(json.dumps(self.build_memory(data), ensure_ascii=False, indent=2), encoding="utf-8")
        return state_path, handoff_path

    def load_memory(self, task_dir: str) -> dict[str, Any]:
        if not task_dir:
            return {}
        path = Path(task_dir) / self.MEMORY_NAME
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def build_memory(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "updated_at": data.get("updated_at", ""),
            "status": data.get("status", ""),
            "current_step": data.get("current_step", ""),
            "next_step": data.get("next_step", ""),
            "completed_step_keys": data.get("completed_step_keys", []),
            "task_dir": data.get("task_dir", ""),
            "payload_path": data.get("payload_path", ""),
            "agent_backend": data.get("agent_backend", ""),
            "model_name": data.get("model_name", ""),
            "session_id": data.get("session_id", ""),
            "known_artifacts": data.get("artifacts", []),
            "requirement": data.get("skill_description", ""),
            "constraints": data.get("additional_constraints", ""),
            "recent_output_excerpt": data.get("recent_output", ""),
            "resume_rules": [
                "优先沿用 task_dir、payload_path、known_artifacts。",
                "切换模型或登录方式后也不要重新创建任务目录。",
                "只修复用户指出的问题，除非审计发现必须调整相关逻辑。",
                "已完成步骤不得重跑，除非对应产物缺失或用户明确要求。",
            ],
        }

    def load_state(self, task_dir: str) -> dict[str, Any]:
        if not task_dir:
            return {}
        path = Path(task_dir) / self.STATE_NAME
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def read_handoff(self, task_dir: str) -> str:
        if not task_dir:
            return ""
        path = Path(task_dir) / self.HANDOFF_NAME
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def render_markdown(self, data: dict[str, Any]) -> str:
        completed = data.get("completed_steps", [])
        artifacts = data.get("artifacts", [])
        recent_output = str(data.get("recent_output", "") or "").strip()
        lines = [
            "# Skill Task Handoff",
            "",
            f"- updated_at: `{data.get('updated_at', '')}`",
            f"- status: `{data.get('status', '')}`",
            f"- current_step: `{data.get('current_step', '')}`",
            f"- next_step: `{data.get('next_step', '')}`",
            f"- backend: `{data.get('agent_backend', '')}`",
            f"- model: `{data.get('model_name', '')}`",
            f"- session_id: `{data.get('session_id', '') or 'none'}`",
            f"- task_dir: `{data.get('task_dir', '')}`",
            f"- payload_path: `{data.get('payload_path', '')}`",
            "",
            "## Completed Steps",
            "",
        ]
        lines.extend(f"- {item}" for item in completed) if completed else lines.append("- none")
        lines.extend(["", "## Existing Artifacts", ""])
        lines.extend(f"- `{item}`" for item in artifacts) if artifacts else lines.append("- none")
        lines.extend(
            [
                "",
                "## Original Requirement",
                "",
                str(data.get("skill_description", "") or "(none)"),
                "",
                "## Constraints",
                "",
                str(data.get("additional_constraints", "") or "(none)"),
                "",
                "## Resume Rules",
                "",
                "- Continue from existing artifacts first.",
                "- Do not recreate a new task directory when this task directory is still valid.",
                "- Do not rerun completed steps unless an artifact is missing or the user explicitly asks to reset.",
                "- Prefer minimal repair over redesign when continuing an existing task.",
            ]
        )
        if recent_output:
            lines.extend(["", "## Recent Model Output", "", "```text", recent_output, "```"])
        return "\n".join(lines).rstrip() + "\n"
