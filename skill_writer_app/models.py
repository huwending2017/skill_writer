from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class AppSettings:
    workspace_root: str = ""
    config_dir: str = ""
    skill_excel_path: str = ""
    war_excel_path: str = ""
    backup_dir: str = ""
    copy_dir: str = ""
    payload_path: str = ""
    template_name: str = "single"
    agent_backend: str = "codex"
    model_preset_key: str = "openai_gpt54"
    codex_executable: str = ""
    claude_executable: str = ""
    python_executable: str = ""
    codex_model: str = "gpt-5.4"
    codex_extra_args: str = ""
    claude_model: str = "sonnet"
    claude_extra_args: str = ""
    scene_label: str = ""
    dedupe_existing: bool = True
    serial_include_real_writeback: bool = False
    skill_description: str = ""
    additional_constraints: str = (
        "新增 Lua 脚本请带详细中文注释，尽量细到每一步；正式 Excel 不直接修改，"
        "先产出 temp_excel_payload.json 和临时配置。生产 Lua 必须自洽，不能依赖测试文件或测试 helper；"
        "等级规则：显式技能等级/最大等级优先；未写时自带默认 0-10，兵书/装备默认 0-1。"
        "单技能模板允许一次填写多个互不关联技能，此时按独立批量开发；在执行环境支持时可按技能并行完成"
        "复用审计、脚本编写和单技能测试，但最终必须统一合并校验，且不构造跨技能依赖。"
    )
    protected_files: str = ""
    last_prompt: str = ""
    last_output_file: str = ""
    last_task_dir: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppSettings":
        defaults = cls()
        merged = defaults.to_dict()
        for key, value in data.items():
            if key in merged:
                merged[key] = value
        return cls(**merged)

    def ensure_output_file(self) -> str:
        if self.last_output_file:
            return self.last_output_file
        output = Path.cwd() / "data" / "last_codex_message.txt"
        self.last_output_file = str(output)
        return self.last_output_file


@dataclass
class TaskHistoryEntry:
    timestamp: str
    task_name: str
    status_code: int
    status_text: str
    workspace_root: str
    battle_root: str
    template_name: str
    scene_label: str
    agent_backend: str
    model_preset_key: str
    model_name: str
    codex_extra_args: str
    payload_path: str
    task_dir: str
    output_file: str
    archive_dir: str
    skill_description: str
    protected_files: str
    additional_constraints: str
    dedupe_existing: bool
    session_id: str = ""
    session_file: str = ""
    artifacts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskHistoryEntry":
        defaults = cls(
            timestamp="",
            task_name="",
            status_code=-1,
            status_text="",
            workspace_root="",
            battle_root="",
            template_name="",
            scene_label="",
            agent_backend="codex",
            model_preset_key="",
            model_name="",
            codex_extra_args="",
            payload_path="",
            task_dir="",
            output_file="",
            archive_dir="",
            skill_description="",
            protected_files="",
            additional_constraints="",
            dedupe_existing=True,
            session_id="",
            session_file="",
            artifacts=[],
        )
        merged = defaults.to_dict()
        for key, value in data.items():
            if key in merged:
                merged[key] = value
        return cls(**merged)
