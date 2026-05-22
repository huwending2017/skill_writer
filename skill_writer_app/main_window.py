from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import tkinter as tk
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from skill_writer_app.model_catalog import (
    MODEL_PRESETS,
    PROFILE_SHORTCUTS,
    SCENE_TO_PRESET_KEY,
    build_preset_note,
    build_recommendation_text,
    get_preset,
    label_to_key_map,
    preset_labels,
    scene_labels,
)
from skill_writer_app.models import AppSettings, TaskHistoryEntry
from skill_writer_app.services.codex_runner import CodexRunner
from skill_writer_app.services.claude_runner import ClaudeRunner
from skill_writer_app.services.active_task_service import ActiveTaskService
from skill_writer_app.services.bundled_skill_service import BundledSkillService
from skill_writer_app.services.environment_check_service import EnvironmentCheckService
from skill_writer_app.services.excel_writeback import ExcelWritebackService
from skill_writer_app.services.history_service import HistoryService
from skill_writer_app.services.local_script_runner import LocalScriptRunner
from skill_writer_app.services.log_sanitizer import LogSanitizer
from skill_writer_app.services.settings_service import SettingsService
from skill_writer_app.services.task_handoff_service import TaskHandoffService
from skill_writer_app.services.text_decode import decode_process_output
from skill_writer_app.services.workflow_state_service import WorkflowStateService
from skill_writer_app.services.workspace_manager import WorkspaceManager
from skill_writer_app.templates import (
    TEMPLATE_OPTIONS,
    TEMPLATE_TEXT,
    build_prompt,
    template_key_from_label,
    template_label_from_key,
    template_labels,
)


class SkillWriterApp:
    LOG_BATCH_SIZE = 160
    LOG_FLUSH_INTERVAL_MS = 1000
    LOG_MAX_LINES = 5000
    STATUS_TICK_MS = 1000
    CORE_LOG_PREFIXES = (
        "[session]",
        "[workflow]",
        "[workflow-resume]",
        "[workflow-guard]",
        "[health]",
        "[task]",
        "[serial]",
        "[handoff]",
        "[repair]",
        "[local-python]",
        "[local-script]",
        "[local-error]",
        "[audit]",
        "[audit-error]",
        "[compile]",
        "[compile-error]",
        "[test]",
        "[test-error]",
        "[writeback-mode]",
        "[writeback-progress]",
        "[writeback-error]",
        "[summary]",
        "[timing]",
        "[finalize]",
        "[archive]",
        "[python-deps]",
        "[codex-error]",
        "[claude-error]",
        "[log-ui]",
    )
    CORE_LOG_CONTAINS = (
        "Traceback",
        "Error",
        "Exception",
        "ModuleNotFoundError",
        "退出码",
        "执行失败",
        "不可执行",
        "passed",
        "failed",
    )
    REPAIR_TEXT_SUFFIXES = {".txt", ".log", ".md", ".json", ".lua", ".csv"}
    REPAIR_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
    SKILL_EXCEL_NAME = "J_技能表_skill.xlsx"
    WAR_EXCEL_NAME = "Z_战报表.xlsx"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Skill Writer Desktop")
        self.root.geometry("1460x990")

        self.base_dir = BundledSkillService.resolve_app_base_dir()
        self.data_dir = self.base_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.migrate_legacy_app_data()
        self.log_dir = self.data_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.full_log_path = self.log_dir / f"skill_writer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.bundled_skill_service = BundledSkillService(self.base_dir)
        self.skill_sync_results = self.bundled_skill_service.sync_all()
        self.settings_service = SettingsService(self.data_dir / "settings.json")
        self.history_service = HistoryService(self.data_dir / "history.json")
        self.workflow_state_service = WorkflowStateService(self.data_dir / "workflow_state.json")
        self.active_task_service = ActiveTaskService(self.data_dir / "active_task_state.json")
        self.task_handoff_service = TaskHandoffService()
        self.workspace_manager = WorkspaceManager()
        self.codex_runner = CodexRunner()
        self.claude_runner = ClaudeRunner()
        self.environment_check_service = EnvironmentCheckService()
        self.local_script_runner = LocalScriptRunner()
        self.log_sanitizer = LogSanitizer()
        family_skill_path = self.bundled_skill_service.bundled_skills_dir() / "family-battle-skill-writer"
        self.writeback_service = ExcelWritebackService(
            str(family_skill_path / "scripts" / "write_temp_skill_excel.py")
        )
        self.settings = self.settings_service.load()
        self.settings.last_output_file = str(self.default_output_file())
        self.log_queue: queue.Queue[str] = queue.Queue()

        self.template_var = tk.StringVar(value=template_label_from_key(self.settings.template_name))
        self.workspace_var = tk.StringVar(value=self.settings.workspace_root)
        self.battle_root_var = tk.StringVar(value="")
        self.config_dir_var = tk.StringVar(value=self.resolve_initial_config_dir())
        self.skill_excel_var = tk.StringVar(value=self.settings.skill_excel_path)
        self.war_excel_var = tk.StringVar(value=self.settings.war_excel_path)
        self.refresh_config_excel_paths(show_error=False)
        self.backup_dir_var = tk.StringVar(value=self.settings.backup_dir)
        self.copy_dir_var = tk.StringVar(value=self.settings.copy_dir)
        self.payload_var = tk.StringVar(value=self.settings.payload_path)
        self.model_preset_key_var = tk.StringVar(value=self.settings.model_preset_key)
        self.model_preset_label_var = tk.StringVar(value=self.get_preset_label(self.settings.model_preset_key))
        self.agent_backend_var = tk.StringVar(value=self.settings.agent_backend or "codex")
        self.codex_executable_var = tk.StringVar(value=self.settings.codex_executable)
        self.claude_executable_var = tk.StringVar(value=self.settings.claude_executable)
        self.python_executable_var = tk.StringVar(value=self.settings.python_executable)
        self.codex_model_var = tk.StringVar(value=self.settings.codex_model)
        self.codex_extra_args_var = tk.StringVar(value=self.settings.codex_extra_args)
        self.claude_model_var = tk.StringVar(value=self.settings.claude_model)
        self.claude_extra_args_var = tk.StringVar(value=self.settings.claude_extra_args)
        default_scene = self.settings.scene_label or (scene_labels()[0] if scene_labels() else "")
        self.scene_var = tk.StringVar(value=default_scene)
        self.command_preview_var = tk.StringVar(value="")
        self.latest_task_dir_var = tk.StringVar(value=self.settings.last_task_dir)
        self.artifact_summary_var = tk.StringVar(value="当前没有任务产物")
        self.dedupe_var = tk.BooleanVar(value=self.settings.dedupe_existing)
        self.serial_include_real_var = tk.BooleanVar(value=self.settings.serial_include_real_writeback)
        self.status_var = tk.StringVar(value="就绪")
        self.stage_var = tk.StringVar(value="空闲")
        self.elapsed_var = tk.StringVar(value="00:00")
        self.last_log_time_var = tk.StringVar(value="无")
        self.runtime_hint_var = tk.StringVar(value="等待开始任务")
        self.full_log_path_var = tk.StringVar(value=str(self.full_log_path))
        self.workflow_summary_var = tk.StringVar(value="流程：开发 -> 预审 -> 编译 -> 测试 -> 预览 -> 副本 -> 正式")
        self.next_action_var = tk.StringVar(value="下一步：先完成工作区配置，然后执行技能开发。")
        self.template_hint_var = tk.StringVar(value="")
        self.workflow_reset_var = tk.StringVar(value="按历史自动判断")
        self.current_step_title_var = tk.StringVar(value="当前步骤：等待开始")
        self.current_step_desc_var = tk.StringVar(value="请先完成工作区配置，然后按流程开始。")
        self.current_step_action_var = tk.StringVar(value="执行当前步骤")
        self.step_overview_toggle_var = tk.StringVar(value="显示全览")
        self.history_search_var = tk.StringVar(value="")
        self.history_task_filter_var = tk.StringVar(value="全部任务")
        self.history_status_filter_var = tk.StringVar(value="全部结果")
        self.history_view_mode_var = tk.StringVar(value="按技能聚合")
        self.history_summary_var = tk.StringVar(value="当前还没有历史记录")
        self.repair_session_var = tk.StringVar(value="当前会话：未选择。请先在左侧双击一个技能会话。")
        self.repair_attachment_status_var = tk.StringVar(value="附件：0 个")
        self.environment_health_var = tk.StringVar(value="环境体检：未执行")
        self.task_health_var = tk.StringVar(value="当前任务：未选择")

        self.description_text: tk.Text
        self.protected_text: tk.Text
        self.constraints_text: tk.Text
        self.prompt_text: tk.Text
        self.log_text: tk.Text
        self.workbench_log_text: tk.Text
        self.model_note_text: tk.Text
        self.model_recommend_text: tk.Text
        self.payload_listbox: tk.Listbox
        self.task_dir_listbox: tk.Listbox
        self.artifact_listbox: tk.Listbox
        self.history_listbox: tk.Listbox
        self.history_detail_text: tk.Text
        self.repair_chat_text: tk.Text
        self.repair_issue_text: tk.Text
        self.repair_attachment_listbox: tk.Listbox
        self.health_text: tk.Text
        self.notebook: ttk.Notebook
        self.develop_button: ttk.Button
        self.audit_button: ttk.Button
        self.compile_button: ttk.Button
        self.test_button: ttk.Button
        self.preview_button: ttk.Button
        self.copy_button: ttk.Button
        self.real_button: ttk.Button
        self.quick_real_button: ttk.Button
        self.stop_button: ttk.Button
        self.next_step_button: ttk.Button
        self.serial_button: ttk.Button
        self.reset_button: ttk.Button
        self.current_step_button: ttk.Button
        self.step_overview_button: ttk.Button
        self.local_compile_button: ttk.Button
        self.local_audit_button: ttk.Button
        self.step_overview_frame: ttk.LabelFrame
        self.future_steps_frame: ttk.LabelFrame
        self.workbench_advanced_button: ttk.Button
        self.workbench_advanced_frame: ttk.LabelFrame

        self.recent_payloads: list[Path] = []
        self.recent_task_dirs: list[Path] = []
        self.current_task_artifacts: list[Path] = []
        self.history_entries: list[TaskHistoryEntry] = []
        self.history_display_rows: list[dict[str, object]] = []
        self.payload_listboxes: list[tk.Listbox] = []
        self.task_dir_listboxes: list[tk.Listbox] = []
        self.syncing_recent_lists: bool = False
        self.active_repair_entry: TaskHistoryEntry | None = None
        self.repair_attachment_paths: list[str] = []
        self.pending_repair_chat_path: Path | None = None
        self.last_task_error_message: str = ""
        self.current_task_name: str = ""
        self.current_archive_dir: str = ""
        self.recommended_action_key: str = ""
        self.serial_workflow_active: bool = False
        self.serial_current_step: str = ""
        self.serial_pending_steps: list[str] = []
        self.step_overview_visible: bool = False
        self.workbench_advanced_visible: bool = False
        self.environment_check_running: bool = False
        self.accepted_workflow_prompt_hash: str = ""
        self.workflow_refresh_after_id: str | None = None
        self.suppress_requirement_change: bool = False
        self.current_task_started_at: datetime | None = None
        self.current_active_task_key: str = ""
        self.last_log_at: datetime | None = None

        self.build_ui()
        self.write_full_log(
            "[session] Skill Writer Desktop started\n"
            f"[session] full_log: {self.full_log_path}\n"
        )
        self.write_skill_sync_log()
        self.update_step_overview_visibility()
        self.update_workbench_advanced_visibility()
        self.load_initial_content()
        self.refresh_history_view()
        self.refresh_battle_root()
        self.restore_active_task_selection()
        self.ensure_codex_cli_ready()
        self.ensure_claude_cli_ready()
        self.refresh_model_note()
        self.refresh_command_preview()
        self.update_task_health_panel()
        self.root.after(800, self.run_environment_check)
        self.update_action_buttons()
        self.poll_logs()
        self.poll_runtime_status()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def get_preset_label(self, key: str) -> str:
        return get_preset(key).label

    def default_output_file(self) -> Path:
        return self.data_dir / "last_codex_message.txt"

    def migrate_legacy_app_data(self) -> None:
        legacy_items = [
            "settings.json",
            "history.json",
            "active_task_state.json",
            "workflow_state.json",
            "last_codex_message.txt",
        ]
        for name in legacy_items:
            source = self.base_dir / name
            destination = self.data_dir / name
            if source.exists() and not destination.exists():
                try:
                    shutil.move(str(source), str(destination))
                except Exception:
                    pass

        legacy_dirs = {
            "logs": self.data_dir / "logs",
            "repair_attachments": self.data_dir / "repair_attachments",
            "session_handoffs": self.data_dir / "session_handoffs",
        }
        for name, destination in legacy_dirs.items():
            source = self.base_dir / name
            if source.exists() and source.is_dir() and not destination.exists():
                try:
                    shutil.move(str(source), str(destination))
                except Exception:
                    pass

    def write_skill_sync_log(self) -> None:
        if not self.skill_sync_results:
            self.write_full_log("[skills] no bundled skills found\n")
            return
        for result in self.skill_sync_results:
            self.write_full_log(
                f"[skills] {result.action}: {result.name} -> {result.destination}\n"
            )

    def bundled_script_path(self, script_name: str) -> Path:
        candidates = [
            self.base_dir / "scripts" / script_name,
            self.base_dir.parent / "scripts" / script_name,
            self.base_dir / "_internal" / "scripts" / script_name,
            self.base_dir / "_internal" / ".." / "scripts" / script_name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=12)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        header.columnconfigure(5, weight=1)

        ttk.Label(header, text="工作目录").grid(row=0, column=0, sticky="w")
        ttk.Entry(header, textvariable=self.workspace_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(header, text="选择目录", command=self.choose_workspace).grid(row=0, column=2, padx=4)
        ttk.Button(header, text="刷新 battle_root", command=self.refresh_battle_root).grid(row=0, column=3, padx=4)
        ttk.Label(header, textvariable=self.status_var).grid(row=0, column=4, sticky="e", padx=8)
        ttk.Label(header, text="阶段").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(header, textvariable=self.stage_var).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Label(header, text="已运行").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Label(header, textvariable=self.elapsed_var).grid(row=1, column=3, sticky="w", pady=(8, 0))
        ttk.Label(header, text="最近日志").grid(row=1, column=4, sticky="e", pady=(8, 0))
        ttk.Label(header, textvariable=self.last_log_time_var).grid(row=1, column=5, sticky="w", padx=8, pady=(8, 0))
        ttk.Button(header, text="查看日志", command=self.show_log_tab).grid(row=1, column=6, sticky="e", pady=(8, 0))
        ttk.Label(header, textvariable=self.runtime_hint_var).grid(
            row=2,
            column=0,
            columnspan=7,
            sticky="w",
            pady=(6, 0),
        )

        notebook = ttk.Notebook(self.root)
        self.notebook = notebook
        notebook.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        self.build_workbench_tab(notebook)
        self.build_history_tab(notebook)
        self.build_log_tab(notebook)

    def build_workbench_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        frame.columnconfigure(0, weight=3)
        frame.columnconfigure(1, weight=2)
        frame.rowconfigure(1, weight=2)
        frame.rowconfigure(2, weight=1)
        notebook.add(frame, text="工作台")

        project_frame = ttk.LabelFrame(frame, text="1. 选择项目")
        project_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        project_frame.columnconfigure(1, weight=1)
        project_frame.columnconfigure(4, weight=1)

        ttk.Label(project_frame, text="工作目录").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(project_frame, textvariable=self.workspace_var).grid(
            row=0, column=1, columnspan=3, sticky="ew", padx=6, pady=6
        )
        ttk.Button(project_frame, text="选择", command=self.choose_workspace).grid(row=0, column=4, padx=6, pady=6)
        ttk.Button(project_frame, text="刷新", command=self.refresh_battle_root).grid(row=0, column=5, padx=6, pady=6)

        ttk.Label(project_frame, text="battle_root").grid(row=1, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(project_frame, textvariable=self.battle_root_var, state="readonly").grid(
            row=1, column=1, columnspan=5, sticky="ew", padx=6, pady=6
        )

        ttk.Label(project_frame, text="配置目录").grid(row=2, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(project_frame, textvariable=self.config_dir_var).grid(
            row=2, column=1, columnspan=4, sticky="ew", padx=6, pady=6
        )
        ttk.Button(project_frame, text="选择", command=self.choose_config_dir).grid(row=2, column=5, padx=6, pady=6)

        ttk.Label(project_frame, text="Payload").grid(row=3, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(project_frame, textvariable=self.payload_var).grid(
            row=3, column=1, columnspan=3, sticky="ew", padx=6, pady=6
        )
        ttk.Button(project_frame, text="选择", command=lambda: self.choose_file(self.payload_var)).grid(
            row=3, column=4, padx=6, pady=6
        )
        ttk.Button(project_frame, text="自动发现", command=self.auto_discover_payload).grid(
            row=3, column=5, padx=6, pady=6
        )

        input_frame = ttk.LabelFrame(frame, text="2. 描述技能")
        input_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        input_frame.columnconfigure(0, weight=1)
        input_frame.rowconfigure(1, weight=1)
        input_frame.rowconfigure(3, weight=1)

        input_bar = ttk.Frame(input_frame)
        input_bar.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 4))
        ttk.Label(input_bar, text="模板").pack(side="left")
        template_box = ttk.Combobox(
            input_bar,
            textvariable=self.template_var,
            values=template_labels(),
            state="readonly",
            width=20,
        )
        template_box.pack(side="left", padx=6)
        template_box.bind("<<ComboboxSelected>>", self.on_requirement_text_changed)
        ttk.Button(input_bar, text="生成 Prompt", command=self.refresh_prompt).pack(side="left", padx=6)
        ttk.Button(input_bar, text="复制 Prompt", command=self.copy_prompt).pack(side="left", padx=6)
        ttk.Button(input_bar, text="新建技能任务", command=self.confirm_new_skill_development).pack(side="left", padx=6)
        ttk.Label(input_bar, textvariable=self.template_hint_var).pack(side="left", padx=12)

        self.description_text = tk.Text(input_frame, height=7, wrap="word")
        self.description_text.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.description_text.bind("<KeyRelease>", self.on_requirement_text_changed)

        ttk.Label(input_frame, text="生成后的 Prompt").grid(row=2, column=0, sticky="w", padx=6)
        self.prompt_text = tk.Text(input_frame, height=8, wrap="word")
        self.prompt_text.grid(row=3, column=0, sticky="nsew", padx=6, pady=(2, 6))

        run_frame = ttk.LabelFrame(frame, text="3. 执行")
        run_frame.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        run_frame.columnconfigure(0, weight=1)

        ttk.Label(run_frame, textvariable=self.current_step_title_var).grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 4)
        )
        ttk.Label(run_frame, textvariable=self.current_step_desc_var, justify="left", wraplength=420).grid(
            row=1, column=0, sticky="ew", padx=8, pady=(0, 8)
        )
        action_row = ttk.Frame(run_frame)
        action_row.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        action_row.columnconfigure(0, weight=1)
        self.serial_button = ttk.Button(action_row, text="自动串行", command=self.run_serial_workflow)
        self.serial_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.current_step_button = ttk.Button(action_row, text="执行当前步骤", command=self.run_recommended_next_step)
        self.current_step_button.grid(row=0, column=1, padx=6)
        self.stop_button = ttk.Button(action_row, text="停止", command=self.stop_current_task)
        self.stop_button.grid(row=0, column=2, padx=(6, 0))

        ttk.Label(run_frame, textvariable=self.workflow_summary_var, justify="left", wraplength=420).grid(
            row=3, column=0, sticky="ew", padx=8, pady=4
        )
        ttk.Label(run_frame, textvariable=self.next_action_var, justify="left", wraplength=420).grid(
            row=4, column=0, sticky="ew", padx=8, pady=(0, 8)
        )

        utility_row = ttk.Frame(run_frame)
        utility_row.grid(row=5, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.next_step_button = ttk.Button(utility_row, text="执行下一步", command=self.run_recommended_next_step)
        self.next_step_button.pack(side="left")
        self.step_overview_button = ttk.Button(
            utility_row,
            textvariable=self.step_overview_toggle_var,
            command=self.toggle_step_overview,
        )
        self.step_overview_button.pack(side="left", padx=6)
        self.quick_real_button = ttk.Button(utility_row, text="写正式表", command=self.write_excel_real)
        self.quick_real_button.pack(side="left", padx=6)
        ttk.Checkbutton(
            utility_row,
            text="串行包含正式",
            variable=self.serial_include_real_var,
            command=self.update_action_buttons,
        ).pack(side="left", padx=6)
        ttk.Button(utility_row, text="打开输出", command=self.open_output_file).pack(side="left", padx=6)
        ttk.Button(utility_row, text="环境体检", command=self.run_environment_check).pack(side="left", padx=6)

        self.step_overview_frame = ttk.LabelFrame(run_frame, text="手动步骤")
        self.step_overview_frame.grid(row=6, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.develop_button = ttk.Button(self.step_overview_frame, text="1. 生成脚本", command=self.run_develop)
        self.develop_button.pack(side="left", padx=(6, 0), pady=6)
        self.audit_button = ttk.Button(self.step_overview_frame, text="2. 预审", command=self.run_local_audit)
        self.audit_button.pack(side="left", padx=6, pady=6)
        self.compile_button = ttk.Button(self.step_overview_frame, text="3. 编译", command=self.run_local_compile)
        self.compile_button.pack(side="left", padx=6, pady=6)
        self.test_button = ttk.Button(self.step_overview_frame, text="4. 测试", command=self.run_test)
        self.test_button.pack(side="left", padx=6, pady=6)

        self.future_steps_frame = ttk.LabelFrame(run_frame, text="Excel 回写")
        self.future_steps_frame.grid(row=7, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.preview_button = ttk.Button(self.future_steps_frame, text="5. 预览", command=self.write_excel_dry_run)
        self.preview_button.pack(side="left", padx=(6, 0), pady=6)
        self.copy_button = ttk.Button(self.future_steps_frame, text="6. 写副本", command=self.write_excel_copy)
        self.copy_button.pack(side="left", padx=6, pady=6)
        self.real_button = ttk.Button(self.future_steps_frame, text="7. 写正式表", command=self.write_excel_real)
        self.real_button.pack(side="left", padx=6, pady=6)

        health_frame = ttk.LabelFrame(run_frame, text="健康状态")
        health_frame.grid(row=8, column=0, sticky="nsew", padx=8, pady=(0, 8))
        health_frame.columnconfigure(0, weight=1)
        health_frame.rowconfigure(2, weight=1)
        ttk.Label(health_frame, textvariable=self.environment_health_var, justify="left").grid(
            row=0, column=0, sticky="ew", padx=6, pady=(6, 2)
        )
        ttk.Label(health_frame, textvariable=self.task_health_var, justify="left").grid(
            row=1, column=0, sticky="ew", padx=6, pady=2
        )
        self.health_text = tk.Text(health_frame, height=8, wrap="word")
        self.health_text.grid(row=2, column=0, sticky="nsew", padx=6, pady=(2, 6))
        self.health_text.configure(state="disabled")

        recent_log_frame = ttk.LabelFrame(run_frame, text="最近日志")
        recent_log_frame.grid(row=9, column=0, sticky="nsew", padx=8, pady=(0, 8))
        recent_log_frame.columnconfigure(0, weight=1)
        recent_log_frame.rowconfigure(1, weight=1)
        recent_log_actions = ttk.Frame(recent_log_frame)
        recent_log_actions.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(6, 2))
        ttk.Button(recent_log_actions, text="查看完整日志页", command=self.show_log_tab).pack(side="left")
        ttk.Button(recent_log_actions, text="打开日志文件", command=self.open_full_log_file).pack(side="left", padx=6)
        self.workbench_log_text = tk.Text(recent_log_frame, height=6, wrap="word")
        self.workbench_log_text.grid(row=1, column=0, sticky="nsew", padx=6, pady=(2, 6))
        recent_log_scroll = ttk.Scrollbar(recent_log_frame, orient="vertical", command=self.workbench_log_text.yview)
        recent_log_scroll.grid(row=1, column=1, sticky="ns", pady=(2, 6))
        self.workbench_log_text.configure(yscrollcommand=recent_log_scroll.set, state="disabled")

        result_frame = ttk.LabelFrame(frame, text="结果")
        result_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(10, 8))
        result_frame.columnconfigure(0, weight=2)
        result_frame.columnconfigure(1, weight=1)
        result_frame.columnconfigure(2, weight=1)
        result_frame.rowconfigure(1, weight=1)

        task_bar = ttk.Frame(result_frame)
        task_bar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=6, pady=6)
        task_bar.columnconfigure(1, weight=1)
        ttk.Label(task_bar, text="当前任务").grid(row=0, column=0, sticky="w")
        ttk.Entry(task_bar, textvariable=self.latest_task_dir_var, state="readonly").grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Button(task_bar, text="打开目录", command=self.open_latest_task_dir).grid(row=0, column=2, padx=6)
        ttk.Button(task_bar, text="修复问题", command=self.set_current_target_as_repair_session).grid(row=0, column=3, padx=6)
        ttk.Button(task_bar, text="刷新结果", command=self.refresh_current_task_artifacts).grid(row=0, column=4)

        artifact_box = ttk.LabelFrame(result_frame, text="产物")
        artifact_box.grid(row=1, column=0, sticky="nsew", padx=(6, 4), pady=(0, 6))
        artifact_box.columnconfigure(0, weight=1)
        artifact_box.rowconfigure(1, weight=1)
        ttk.Label(artifact_box, textvariable=self.artifact_summary_var).grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.artifact_listbox = tk.Listbox(artifact_box, exportselection=False, height=7)
        self.artifact_listbox.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)
        artifact_scroll = ttk.Scrollbar(artifact_box, orient="vertical", command=self.artifact_listbox.yview)
        artifact_scroll.grid(row=1, column=1, sticky="ns", pady=4)
        self.artifact_listbox.configure(yscrollcommand=artifact_scroll.set)
        self.artifact_listbox.bind("<<ListboxSelect>>", self.on_artifact_select)
        artifact_actions = ttk.Frame(artifact_box)
        artifact_actions.grid(row=2, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))
        ttk.Button(artifact_actions, text="打开文件", command=self.open_selected_artifact).pack(side="left")
        ttk.Button(artifact_actions, text="打开所在目录", command=self.open_selected_artifact_parent).pack(side="left", padx=6)
        ttk.Button(artifact_actions, text="作为 Payload", command=self.use_selected_artifact_as_payload).pack(side="left", padx=6)

        payload_box = ttk.LabelFrame(result_frame, text="最近 Payload")
        payload_box.grid(row=1, column=1, sticky="nsew", padx=4, pady=(0, 6))
        payload_box.columnconfigure(0, weight=1)
        payload_box.rowconfigure(0, weight=1)
        self.payload_listbox = tk.Listbox(payload_box, exportselection=False, height=7)
        self.payload_listboxes.append(self.payload_listbox)
        self.payload_listbox.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.payload_listbox.bind("<<ListboxSelect>>", self.on_recent_payload_select)
        payload_scroll = ttk.Scrollbar(payload_box, orient="vertical", command=self.payload_listbox.yview)
        payload_scroll.grid(row=0, column=1, sticky="ns", pady=6)
        self.payload_listbox.configure(yscrollcommand=payload_scroll.set)
        payload_actions = ttk.Frame(payload_box)
        payload_actions.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))
        ttk.Button(payload_actions, text="使用", command=lambda lb=self.payload_listbox: self.use_selected_payload(lb)).pack(side="left")
        ttk.Button(payload_actions, text="打开", command=self.open_selected_payload).pack(side="left", padx=6)
        ttk.Button(payload_actions, text="刷新", command=self.refresh_temp_workspace_views).pack(side="left", padx=6)

        task_box = ttk.LabelFrame(result_frame, text="最近任务")
        task_box.grid(row=1, column=2, sticky="nsew", padx=(4, 6), pady=(0, 6))
        task_box.columnconfigure(0, weight=1)
        task_box.rowconfigure(0, weight=1)
        self.task_dir_listbox = tk.Listbox(task_box, exportselection=False, height=7)
        self.task_dir_listboxes.append(self.task_dir_listbox)
        self.task_dir_listbox.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.task_dir_listbox.bind("<<ListboxSelect>>", self.on_recent_task_dir_select)
        task_scroll = ttk.Scrollbar(task_box, orient="vertical", command=self.task_dir_listbox.yview)
        task_scroll.grid(row=0, column=1, sticky="ns", pady=6)
        self.task_dir_listbox.configure(yscrollcommand=task_scroll.set)
        task_actions = ttk.Frame(task_box)
        task_actions.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))
        ttk.Button(task_actions, text="使用", command=lambda lb=self.task_dir_listbox: self.use_selected_task_dir(lb)).pack(side="left")
        ttk.Button(task_actions, text="打开", command=lambda lb=self.task_dir_listbox: self.open_selected_task_dir(lb)).pack(side="left", padx=6)
        ttk.Button(task_actions, text="刷新", command=self.refresh_temp_workspace_views).pack(side="left", padx=6)

        advanced_bar = ttk.Frame(frame)
        advanced_bar.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.workbench_advanced_button = ttk.Button(
            advanced_bar,
            text="显示高级设置",
            command=self.toggle_workbench_advanced,
        )
        self.workbench_advanced_button.pack(side="left")
        ttk.Button(advanced_bar, text="保存设置", command=self.save_settings).pack(side="left", padx=6)
        ttk.Label(advanced_bar, textvariable=self.full_log_path_var).pack(side="right")

        self.workbench_advanced_frame = ttk.LabelFrame(frame, text="高级设置")
        self.workbench_advanced_frame.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        self.workbench_advanced_frame.columnconfigure(1, weight=1)
        self.workbench_advanced_frame.columnconfigure(3, weight=1)
        self.workbench_advanced_frame.columnconfigure(4, weight=1)
        self.workbench_advanced_frame.rowconfigure(8, weight=1)

        ttk.Label(self.workbench_advanced_frame, text="保护文件").grid(row=0, column=0, sticky="nw", padx=6, pady=4)
        self.protected_text = tk.Text(self.workbench_advanced_frame, height=4, wrap="word")
        self.protected_text.grid(row=0, column=1, sticky="nsew", padx=6, pady=4)
        self.protected_text.bind("<KeyRelease>", lambda _: self.refresh_prompt())

        ttk.Label(self.workbench_advanced_frame, text="额外约束").grid(row=0, column=2, sticky="nw", padx=6, pady=4)
        self.constraints_text = tk.Text(self.workbench_advanced_frame, height=4, wrap="word")
        self.constraints_text.grid(row=0, column=3, sticky="nsew", padx=6, pady=4)
        self.constraints_text.bind("<KeyRelease>", lambda _: self.refresh_prompt())

        ttk.Label(self.workbench_advanced_frame, text="备份目录").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(self.workbench_advanced_frame, textvariable=self.backup_dir_var).grid(
            row=1, column=1, sticky="ew", padx=6, pady=4
        )
        ttk.Button(self.workbench_advanced_frame, text="选择", command=lambda: self.choose_dir(self.backup_dir_var)).grid(
            row=1, column=2, padx=6, pady=4
        )
        ttk.Label(self.workbench_advanced_frame, text="副本目录").grid(row=1, column=3, sticky="w", padx=6, pady=4)
        ttk.Entry(self.workbench_advanced_frame, textvariable=self.copy_dir_var).grid(
            row=1, column=4, sticky="ew", padx=6, pady=4
        )
        ttk.Button(self.workbench_advanced_frame, text="选择", command=lambda: self.choose_dir(self.copy_dir_var)).grid(
            row=1, column=5, padx=6, pady=4
        )

        ttk.Label(self.workbench_advanced_frame, text="场景").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        scene_box = ttk.Combobox(
            self.workbench_advanced_frame,
            textvariable=self.scene_var,
            values=scene_labels(),
            state="readonly",
            width=20,
        )
        scene_box.grid(row=2, column=1, sticky="w", padx=6, pady=4)
        ttk.Button(self.workbench_advanced_frame, text="应用推荐", command=self.apply_scene_recommendation).grid(
            row=2, column=2, padx=6, pady=4
        )

        ttk.Label(self.workbench_advanced_frame, text="执行后端").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        backend_box = ttk.Combobox(
            self.workbench_advanced_frame,
            textvariable=self.agent_backend_var,
            values=("codex", "claude"),
            state="readonly",
            width=12,
        )
        backend_box.grid(row=3, column=1, sticky="w", padx=6, pady=4)
        backend_box.bind("<<ComboboxSelected>>", lambda _: self.refresh_command_preview())

        ttk.Label(self.workbench_advanced_frame, text="Codex CLI").grid(row=4, column=0, sticky="w", padx=6, pady=4)
        codex_cli_entry = ttk.Entry(self.workbench_advanced_frame, textvariable=self.codex_executable_var)
        codex_cli_entry.grid(row=4, column=1, sticky="ew", padx=6, pady=4)
        codex_cli_entry.bind("<KeyRelease>", lambda _: self.refresh_command_preview())
        ttk.Button(self.workbench_advanced_frame, text="选择", command=lambda: self.choose_file(self.codex_executable_var)).grid(
            row=4, column=2, padx=6, pady=4
        )
        ttk.Button(self.workbench_advanced_frame, text="自动发现", command=self.auto_discover_codex_cli).grid(
            row=4, column=3, sticky="w", padx=6, pady=4
        )

        ttk.Label(self.workbench_advanced_frame, text="Claude CLI").grid(row=5, column=0, sticky="w", padx=6, pady=4)
        claude_cli_entry = ttk.Entry(self.workbench_advanced_frame, textvariable=self.claude_executable_var)
        claude_cli_entry.grid(row=5, column=1, sticky="ew", padx=6, pady=4)
        claude_cli_entry.bind("<KeyRelease>", lambda _: self.refresh_command_preview())
        ttk.Button(self.workbench_advanced_frame, text="选择", command=lambda: self.choose_file(self.claude_executable_var)).grid(
            row=5, column=2, padx=6, pady=4
        )
        ttk.Button(self.workbench_advanced_frame, text="自动发现", command=self.auto_discover_claude_cli).grid(
            row=5, column=3, sticky="w", padx=6, pady=4
        )

        ttk.Label(self.workbench_advanced_frame, text="Python").grid(row=6, column=0, sticky="w", padx=6, pady=4)
        python_entry = ttk.Entry(self.workbench_advanced_frame, textvariable=self.python_executable_var)
        python_entry.grid(row=6, column=1, sticky="ew", padx=6, pady=4)
        ttk.Button(self.workbench_advanced_frame, text="选择", command=lambda: self.choose_file(self.python_executable_var)).grid(
            row=6, column=2, padx=6, pady=4
        )
        ttk.Button(self.workbench_advanced_frame, text="自动发现", command=self.auto_discover_local_python).grid(
            row=6, column=3, sticky="w", padx=6, pady=4
        )

        ttk.Label(self.workbench_advanced_frame, text="模型预设").grid(row=7, column=0, sticky="w", padx=6, pady=4)
        model_box = ttk.Combobox(
            self.workbench_advanced_frame,
            textvariable=self.model_preset_label_var,
            values=preset_labels(),
            state="readonly",
            width=42,
        )
        model_box.grid(row=7, column=1, sticky="ew", padx=6, pady=4)
        model_box.bind("<<ComboboxSelected>>", lambda _: self.on_model_preset_change())
        ttk.Button(self.workbench_advanced_frame, text="应用", command=self.apply_model_preset).grid(
            row=7, column=2, padx=6, pady=4
        )
        ttk.Label(self.workbench_advanced_frame, text="Codex 模型名").grid(row=7, column=3, sticky="w", padx=6, pady=4)
        model_entry = ttk.Entry(self.workbench_advanced_frame, textvariable=self.codex_model_var)
        model_entry.grid(row=7, column=4, sticky="ew", padx=6, pady=4)
        model_entry.bind("<KeyRelease>", lambda _: self.refresh_command_preview())

        ttk.Label(self.workbench_advanced_frame, text="Claude 模型").grid(row=8, column=0, sticky="w", padx=6, pady=4)
        claude_model_entry = ttk.Entry(self.workbench_advanced_frame, textvariable=self.claude_model_var)
        claude_model_entry.grid(row=8, column=1, sticky="ew", padx=6, pady=4)
        claude_model_entry.bind("<KeyRelease>", lambda _: self.refresh_command_preview())
        ttk.Label(self.workbench_advanced_frame, text="额外参数").grid(row=9, column=0, sticky="w", padx=6, pady=4)
        extra_entry = ttk.Entry(self.workbench_advanced_frame, textvariable=self.codex_extra_args_var)
        extra_entry.grid(row=9, column=1, columnspan=2, sticky="ew", padx=6, pady=4)
        extra_entry.bind("<KeyRelease>", lambda _: self.refresh_command_preview())
        claude_extra_entry = ttk.Entry(self.workbench_advanced_frame, textvariable=self.claude_extra_args_var)
        claude_extra_entry.grid(row=8, column=3, columnspan=2, sticky="ew", padx=6, pady=4)
        claude_extra_entry.bind("<KeyRelease>", lambda _: self.refresh_command_preview())
        ttk.Entry(self.workbench_advanced_frame, textvariable=self.command_preview_var, state="readonly").grid(
            row=9, column=3, columnspan=3, sticky="ew", padx=6, pady=4
        )

        option_row = ttk.Frame(self.workbench_advanced_frame)
        option_row.grid(row=10, column=0, columnspan=6, sticky="ew", padx=6, pady=4)
        ttk.Checkbutton(option_row, text="跳过已存在配置", variable=self.dedupe_var).pack(side="left")
        ttk.Checkbutton(
            option_row,
            text="自动串行包含正式回写",
            variable=self.serial_include_real_var,
            command=self.update_action_buttons,
        ).pack(side="left", padx=12)
        ttk.Label(option_row, text="流程重置").pack(side="left", padx=(12, 4))
        ttk.Combobox(
            option_row,
            textvariable=self.workflow_reset_var,
            state="readonly",
            width=18,
            values=[
                "按历史自动判断",
                "技能开发",
                "本地预审",
                "本地编译",
                "技能测试",
                "预览回写",
                "写入 Excel 副本",
                "写回正式 Excel",
            ],
        ).pack(side="left")
        self.reset_button = ttk.Button(option_row, text="应用重置", command=self.apply_workflow_reset)
        self.reset_button.pack(side="left", padx=6)
        self.local_audit_button = ttk.Button(option_row, text="本地预审", command=self.run_local_audit)
        self.local_audit_button.pack(side="left", padx=6)
        self.local_compile_button = ttk.Button(option_row, text="本地编译", command=self.run_local_compile)
        self.local_compile_button.pack(side="left", padx=6)

        lower = ttk.Frame(self.workbench_advanced_frame)
        lower.grid(row=8, column=0, columnspan=6, sticky="nsew", padx=6, pady=4)
        lower.columnconfigure(0, weight=1)
        lower.columnconfigure(1, weight=1)
        lower.columnconfigure(2, weight=1)
        lower.rowconfigure(1, weight=1)
        ttk.Label(lower, text="当前 Prompt 会在主工作台实时显示").grid(row=0, column=0, sticky="w")
        ttk.Label(lower, text="模型说明").grid(row=0, column=1, sticky="w")
        ttk.Label(lower, text="推荐").grid(row=0, column=2, sticky="w")
        self.model_note_text = tk.Text(lower, height=8, wrap="word")
        self.model_note_text.grid(row=1, column=1, sticky="nsew", padx=6)
        self.model_recommend_text = tk.Text(lower, height=8, wrap="word")
        self.model_recommend_text.grid(row=1, column=2, sticky="nsew", padx=(6, 0))
        self.model_recommend_text.insert("1.0", build_recommendation_text())
        self.model_recommend_text.configure(state="disabled")

    def build_config_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)
        frame.rowconfigure(8, weight=1)
        frame.rowconfigure(15, weight=1)
        frame.rowconfigure(16, weight=1)
        notebook.add(frame, text="工程配置")

        ttk.Label(frame, text="battle_root").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.battle_root_var, state="readonly").grid(
            row=0, column=1, columnspan=3, sticky="ew", pady=4
        )

        ttk.Label(frame, text="配置目录").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.config_dir_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)
        ttk.Button(frame, text="选择目录", command=self.choose_config_dir).grid(row=1, column=3, padx=4)

        ttk.Label(frame, text="备份目录").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.backup_dir_var).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="选择目录", command=lambda: self.choose_dir(self.backup_dir_var)).grid(
            row=3, column=2, padx=4
        )

        ttk.Label(frame, text="副本输出目录").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.copy_dir_var).grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="选择目录", command=lambda: self.choose_dir(self.copy_dir_var)).grid(
            row=4, column=2, padx=4
        )

        ttk.Label(frame, text="Payload 路径").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.payload_var).grid(row=5, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="选择文件", command=lambda: self.choose_file(self.payload_var)).grid(
            row=5, column=2, padx=4
        )
        ttk.Button(frame, text="自动发现", command=self.auto_discover_payload).grid(row=5, column=3, padx=4)

        ttk.Label(frame, text="最近任务目录").grid(row=6, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.latest_task_dir_var, state="readonly").grid(
            row=6, column=1, columnspan=2, sticky="ew", pady=4
        )
        ttk.Button(frame, text="打开目录", command=self.open_latest_task_dir).grid(row=6, column=3, padx=4)

        ttk.Separator(frame, orient="horizontal").grid(row=7, column=0, columnspan=4, sticky="ew", pady=10)

        recent_payload_frame = ttk.LabelFrame(frame, text="最近 5 个 Payload")
        recent_payload_frame.grid(row=8, column=0, columnspan=2, sticky="nsew", padx=(0, 8), pady=4)
        recent_payload_frame.columnconfigure(0, weight=1)
        recent_payload_frame.rowconfigure(0, weight=1)

        self.payload_listbox = tk.Listbox(recent_payload_frame, exportselection=False, height=7)
        self.payload_listboxes.append(self.payload_listbox)
        self.payload_listbox.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.payload_listbox.bind("<<ListboxSelect>>", self.on_recent_payload_select)
        payload_scroll = ttk.Scrollbar(recent_payload_frame, orient="vertical", command=self.payload_listbox.yview)
        payload_scroll.grid(row=0, column=1, sticky="ns", pady=6)
        self.payload_listbox.configure(yscrollcommand=payload_scroll.set)

        payload_actions = ttk.Frame(recent_payload_frame)
        payload_actions.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))
        ttk.Button(payload_actions, text="使用选中项", command=lambda lb=self.payload_listbox: self.use_selected_payload(lb)).pack(side="left")
        ttk.Button(payload_actions, text="打开文件", command=self.open_selected_payload).pack(side="left", padx=6)
        ttk.Button(payload_actions, text="刷新列表", command=self.refresh_temp_workspace_views).pack(side="left", padx=6)

        recent_task_frame = ttk.LabelFrame(frame, text="最近 5 个任务目录")
        recent_task_frame.grid(row=8, column=2, columnspan=2, sticky="nsew", pady=4)
        recent_task_frame.columnconfigure(0, weight=1)
        recent_task_frame.rowconfigure(0, weight=1)

        self.task_dir_listbox = tk.Listbox(recent_task_frame, exportselection=False, height=7)
        self.task_dir_listboxes.append(self.task_dir_listbox)
        self.task_dir_listbox.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.task_dir_listbox.bind("<<ListboxSelect>>", self.on_recent_task_dir_select)
        task_scroll = ttk.Scrollbar(recent_task_frame, orient="vertical", command=self.task_dir_listbox.yview)
        task_scroll.grid(row=0, column=1, sticky="ns", pady=6)
        self.task_dir_listbox.configure(yscrollcommand=task_scroll.set)

        task_actions = ttk.Frame(recent_task_frame)
        task_actions.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))
        ttk.Button(task_actions, text="使用选中项", command=lambda lb=self.task_dir_listbox: self.use_selected_task_dir(lb)).pack(side="left")
        ttk.Button(task_actions, text="打开目录", command=lambda lb=self.task_dir_listbox: self.open_selected_task_dir(lb)).pack(side="left", padx=6)
        ttk.Button(task_actions, text="刷新列表", command=self.refresh_temp_workspace_views).pack(side="left", padx=6)

        ttk.Separator(frame, orient="horizontal").grid(row=9, column=0, columnspan=4, sticky="ew", pady=10)

        ttk.Label(frame, text="推荐场景").grid(row=10, column=0, sticky="w", pady=4)
        scene_box = ttk.Combobox(
            frame,
            textvariable=self.scene_var,
            values=scene_labels(),
            state="readonly",
            width=20,
        )
        scene_box.grid(row=10, column=1, sticky="w", pady=4)
        ttk.Button(frame, text="按场景套用", command=self.apply_scene_recommendation).grid(row=10, column=2, padx=4)

        ttk.Label(frame, text="Codex CLI").grid(row=11, column=0, sticky="w", pady=4)
        codex_cli_entry = ttk.Entry(frame, textvariable=self.codex_executable_var)
        codex_cli_entry.grid(row=11, column=1, sticky="ew", pady=4)
        codex_cli_entry.bind("<KeyRelease>", lambda _: self.refresh_command_preview())
        ttk.Button(frame, text="选择文件", command=lambda: self.choose_file(self.codex_executable_var)).grid(
            row=11, column=2, padx=4
        )
        ttk.Button(frame, text="自动探测", command=self.auto_discover_codex_cli).grid(row=11, column=3, padx=4)

        ttk.Label(frame, text="本地 Python").grid(row=12, column=0, sticky="w", pady=4)
        python_entry = ttk.Entry(frame, textvariable=self.python_executable_var)
        python_entry.grid(row=12, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="选择文件", command=lambda: self.choose_file(self.python_executable_var)).grid(
            row=12, column=2, padx=4
        )
        ttk.Button(frame, text="自动探测", command=self.auto_discover_local_python).grid(row=12, column=3, padx=4)

        ttk.Label(frame, text="模型预设").grid(row=13, column=0, sticky="w", pady=4)
        model_box = ttk.Combobox(
            frame,
            textvariable=self.model_preset_label_var,
            values=preset_labels(),
            state="readonly",
            width=42,
        )
        model_box.grid(row=13, column=1, sticky="ew", pady=4)
        model_box.bind("<<ComboboxSelected>>", lambda _: self.on_model_preset_change())
        ttk.Button(frame, text="套用预设", command=self.apply_model_preset).grid(row=13, column=2, padx=4)

        ttk.Label(frame, text="实际模型名").grid(row=14, column=0, sticky="w", pady=4)
        model_entry = ttk.Entry(frame, textvariable=self.codex_model_var)
        model_entry.grid(row=14, column=1, sticky="ew", pady=4)
        model_entry.bind("<KeyRelease>", lambda _: self.refresh_command_preview())

        ttk.Label(frame, text="额外 Codex 参数").grid(row=15, column=0, sticky="w", pady=4)
        extra_entry = ttk.Entry(frame, textvariable=self.codex_extra_args_var)
        extra_entry.grid(row=15, column=1, columnspan=2, sticky="ew", pady=4)
        extra_entry.bind("<KeyRelease>", lambda _: self.refresh_command_preview())
        ttk.Label(frame, text="例如: -p anthropic").grid(row=15, column=3, sticky="w", padx=4)

        ttk.Label(frame, text="命令预览").grid(row=16, column=0, sticky="nw", pady=4)
        ttk.Entry(frame, textvariable=self.command_preview_var, state="readonly").grid(
            row=16, column=1, columnspan=3, sticky="ew", pady=4
        )

        ttk.Label(frame, text="模型说明").grid(row=17, column=0, sticky="nw", pady=4)
        self.model_note_text = tk.Text(frame, height=8, wrap="word")
        self.model_note_text.grid(row=17, column=1, columnspan=3, sticky="nsew", pady=4)

        ttk.Label(frame, text="场景建议").grid(row=18, column=0, sticky="nw", pady=4)
        self.model_recommend_text = tk.Text(frame, height=7, wrap="word")
        self.model_recommend_text.grid(row=18, column=1, columnspan=3, sticky="nsew", pady=4)
        self.model_recommend_text.insert("1.0", build_recommendation_text())
        self.model_recommend_text.configure(state="disabled")

        ttk.Label(frame, text="Profile 快捷").grid(row=19, column=0, sticky="w", pady=4)
        quick_frame = ttk.Frame(frame)
        quick_frame.grid(row=19, column=1, columnspan=3, sticky="ew", pady=4)
        for shortcut in PROFILE_SHORTCUTS:
            ttk.Button(
                quick_frame,
                text=shortcut.label,
                command=lambda value=shortcut.extra_args: self.apply_profile_shortcut(value),
            ).pack(side="left", padx=(0, 6))

        ttk.Checkbutton(frame, text="写回时去重已有重复记录", variable=self.dedupe_var).grid(
            row=20, column=1, sticky="w", pady=8
        )
        ttk.Button(frame, text="保存设置", command=self.save_settings).grid(row=21, column=1, sticky="w", pady=8)

    def build_prompt_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)
        notebook.add(frame, text="模板与输入")

        top = ttk.Frame(frame)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(top, text="模板").pack(side="left")
        template_box = ttk.Combobox(
            top,
            textvariable=self.template_var,
            values=template_labels(),
            state="readonly",
            width=18,
        )
        template_box.pack(side="left", padx=8)
        template_box.bind("<<ComboboxSelected>>", self.on_requirement_text_changed)
        ttk.Button(top, text="新建技能任务", command=self.confirm_new_skill_development).pack(side="left", padx=8)
        ttk.Label(top, textvariable=self.template_hint_var).pack(side="left")

        ttk.Label(frame, text="技能描述").grid(row=1, column=0, sticky="w")
        ttk.Label(frame, text="保护文件与额外约束").grid(row=1, column=1, sticky="w")

        self.description_text = tk.Text(frame, wrap="word")
        self.description_text.grid(row=2, column=0, sticky="nsew", padx=(0, 6))
        self.description_text.bind("<KeyRelease>", self.on_requirement_text_changed)

        right = ttk.Frame(frame)
        right.grid(row=2, column=1, sticky="nsew", padx=(6, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)

        ttk.Label(right, text="保护文件").grid(row=0, column=0, sticky="w")
        self.protected_text = tk.Text(right, height=8, wrap="word")
        self.protected_text.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        self.protected_text.bind("<KeyRelease>", lambda _: self.refresh_prompt())

        ttk.Label(right, text="额外约束").grid(row=2, column=0, sticky="w")
        self.constraints_text = tk.Text(right, height=10, wrap="word")
        self.constraints_text.grid(row=3, column=0, sticky="nsew")
        self.constraints_text.bind("<KeyRelease>", lambda _: self.refresh_prompt())

        prompt_bar = ttk.Frame(frame)
        prompt_bar.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        ttk.Button(prompt_bar, text="生成 Prompt", command=self.refresh_prompt).pack(side="left")
        ttk.Button(prompt_bar, text="复制 Prompt", command=self.copy_prompt).pack(side="left", padx=6)
        self.local_compile_button = ttk.Button(prompt_bar, text="本地编译", command=self.run_local_compile)
        self.local_compile_button.pack(side="left", padx=6)
        self.local_audit_button = ttk.Button(prompt_bar, text="本地预审", command=self.run_local_audit)
        self.local_audit_button.pack(side="left", padx=6)
        ttk.Label(prompt_bar, textvariable=self.template_hint_var).pack(
            side="left",
            padx=12,
        )

        self.prompt_text = tk.Text(frame, wrap="word")
        self.prompt_text.grid(row=4, column=0, columnspan=2, sticky="nsew")

    def build_action_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(4, weight=1)
        notebook.add(frame, text="执行流程")

        current_frame = ttk.LabelFrame(frame, text="当前步骤")
        current_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        current_frame.columnconfigure(0, weight=1)
        ttk.Label(current_frame, textvariable=self.current_step_title_var).grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 4)
        )
        ttk.Label(current_frame, textvariable=self.current_step_desc_var, justify="left").grid(
            row=1, column=0, sticky="w", padx=8, pady=(0, 8)
        )
        action_row = ttk.Frame(current_frame)
        action_row.grid(row=0, column=1, rowspan=2, sticky="ns", padx=8, pady=8)
        self.current_step_button = ttk.Button(
            action_row,
            text="执行当前步骤",
            command=self.run_recommended_next_step,
        )
        self.current_step_button.pack(side="top")
        self.step_overview_button = ttk.Button(
            action_row,
            textvariable=self.step_overview_toggle_var,
            command=self.toggle_step_overview,
        )
        self.step_overview_button.pack(side="top", pady=(8, 0))
        ttk.Button(action_row, text="打开输出文件", command=self.open_output_file).pack(side="top", pady=(8, 0))
        self.stop_button = ttk.Button(action_row, text="停止当前任务", command=self.stop_current_task)
        self.stop_button.pack(side="top", pady=(8, 0))

        self.step_overview_frame = ttk.LabelFrame(frame, text="步骤全览")
        self.step_overview_frame.grid(row=1, column=0, sticky="ew", pady=6)
        self.develop_button = ttk.Button(self.step_overview_frame, text="1. 开发技能（Codex）", command=self.run_develop)
        self.develop_button.pack(side="left")
        self.audit_button = ttk.Button(self.step_overview_frame, text="2. 本地预审", command=self.run_local_audit)
        self.audit_button.pack(side="left", padx=8)
        self.compile_button = ttk.Button(self.step_overview_frame, text="3. 本地编译", command=self.run_local_compile)
        self.compile_button.pack(side="left", padx=8)
        self.test_button = ttk.Button(self.step_overview_frame, text="4. 技能测试（本地）", command=self.run_test)
        self.test_button.pack(side="left", padx=8)

        workflow_frame = ttk.LabelFrame(frame, text="流程设置")
        workflow_frame.grid(row=2, column=0, sticky="ew", pady=(6, 10))
        workflow_frame.columnconfigure(0, weight=1)
        ttk.Label(
            workflow_frame,
            text="默认链路：开发 -> 预审 -> 编译 -> 测试 -> 预览 -> 副本 -> 正式",
            justify="left",
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        ttk.Label(workflow_frame, textvariable=self.workflow_summary_var, justify="left").grid(
            row=1,
            column=0,
            sticky="w",
            padx=8,
            pady=4,
        )
        ttk.Label(workflow_frame, textvariable=self.next_action_var, justify="left").grid(
            row=2,
            column=0,
            sticky="w",
            padx=8,
            pady=4,
        )
        ttk.Checkbutton(
            workflow_frame,
            text="串行包含正式写回（高风险）",
            variable=self.serial_include_real_var,
            command=self.update_action_buttons,
        ).grid(row=3, column=0, sticky="w", padx=8, pady=(0, 8))
        reset_row = ttk.Frame(workflow_frame)
        reset_row.grid(row=4, column=0, sticky="w", padx=8, pady=(0, 8))
        ttk.Label(reset_row, text="流程重置").pack(side="left")
        ttk.Combobox(
            reset_row,
            textvariable=self.workflow_reset_var,
            state="readonly",
            width=20,
            values=[
                "按历史自动判断",
                "技能开发",
                "本地预审",
                "本地编译",
                "技能测试",
                "预览回写",
                "写入 Excel 副本",
                "写回正式 Excel",
            ],
        ).pack(side="left", padx=(6, 6))
        self.reset_button = ttk.Button(reset_row, text="应用重置", command=self.apply_workflow_reset)
        self.reset_button.pack(side="left")
        self.next_step_button = ttk.Button(
            workflow_frame,
            text="执行下一步",
            command=self.run_recommended_next_step,
        )
        self.next_step_button.grid(row=0, column=1, rowspan=5, padx=8, pady=8, sticky="ns")
        self.serial_button = ttk.Button(
            workflow_frame,
            text="自动串行",
            command=self.run_serial_workflow,
        )
        self.serial_button.grid(row=0, column=2, rowspan=5, padx=(0, 8), pady=8, sticky="ns")

        self.future_steps_frame = ttk.LabelFrame(frame, text="后续步骤")
        self.future_steps_frame.grid(row=3, column=0, sticky="ew", pady=6)
        self.preview_button = ttk.Button(self.future_steps_frame, text="5. 仅预览回写", command=self.write_excel_dry_run)
        self.preview_button.pack(side="left")
        self.copy_button = ttk.Button(self.future_steps_frame, text="6. 写入 Excel 副本", command=self.write_excel_copy)
        self.copy_button.pack(side="left", padx=8)
        self.real_button = ttk.Button(self.future_steps_frame, text="7. 写回正式 Excel", command=self.write_excel_real)
        self.real_button.pack(side="left", padx=8)

        artifact_frame = ttk.LabelFrame(frame, text="最近任务产物")
        artifact_frame.grid(row=4, column=0, sticky="nsew", pady=(10, 6))
        artifact_frame.columnconfigure(1, weight=1)
        artifact_frame.rowconfigure(2, weight=1)

        ttk.Label(artifact_frame, text="当前任务目录").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(artifact_frame, textvariable=self.latest_task_dir_var, state="readonly").grid(
            row=0,
            column=1,
            sticky="ew",
            padx=6,
            pady=6,
        )
        ttk.Button(artifact_frame, text="打开目录", command=self.open_selected_task_dir).grid(
            row=0,
            column=2,
            padx=6,
            pady=6,
        )

        ttk.Label(artifact_frame, textvariable=self.artifact_summary_var).grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="w",
            padx=6,
            pady=(0, 6),
        )

        self.artifact_listbox = tk.Listbox(artifact_frame, exportselection=False, height=10)
        self.artifact_listbox.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        artifact_scroll = ttk.Scrollbar(artifact_frame, orient="vertical", command=self.artifact_listbox.yview)
        artifact_scroll.grid(row=2, column=2, sticky="ns", pady=6)
        self.artifact_listbox.configure(yscrollcommand=artifact_scroll.set)
        self.artifact_listbox.bind("<<ListboxSelect>>", self.on_artifact_select)

        artifact_actions = ttk.Frame(artifact_frame)
        artifact_actions.grid(row=3, column=0, columnspan=3, sticky="ew", padx=6, pady=(0, 6))
        ttk.Button(artifact_actions, text="打开选中文件", command=self.open_selected_artifact).pack(side="left")
        ttk.Button(artifact_actions, text="打开所在目录", command=self.open_selected_artifact_parent).pack(
            side="left",
            padx=6,
        )
        ttk.Button(artifact_actions, text="选为 Payload", command=self.use_selected_artifact_as_payload).pack(
            side="left",
            padx=6,
        )
        ttk.Button(artifact_actions, text="刷新产物", command=self.refresh_current_task_artifacts).pack(
            side="left",
            padx=6,
        )

        hint = (
            "自动串行默认只执行到“写入 Excel 副本”；正式写回需单独开启。\n"
            "切换 payload 或任务目录后，流程状态会按该目标的历史记录重新判断。"
        )
        ttk.Label(frame, text=hint, justify="left").grid(row=5, column=0, sticky="w", pady=8)

    def build_history_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=2)
        frame.rowconfigure(3, weight=1)
        notebook.add(frame, text="技能会话")

        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Button(toolbar, text="刷新", command=self.refresh_history_view).pack(side="left")
        ttk.Button(toolbar, text="回填", command=self.apply_selected_history).pack(side="left", padx=6)
        ttk.Button(toolbar, text="进入会话", command=self.set_selected_history_as_repair_session).pack(side="left", padx=6)
        ttk.Button(toolbar, text="打开目录", command=self.open_selected_history_task_dir).pack(side="left", padx=6)
        ttk.Button(toolbar, text="打开 Payload", command=self.open_selected_history_payload).pack(side="left", padx=6)
        ttk.Button(toolbar, text="打开归档", command=self.open_selected_history_archive_dir).pack(side="left", padx=6)

        filter_bar = ttk.Frame(frame)
        filter_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(filter_bar, text="搜索").pack(side="left")
        search_entry = ttk.Entry(filter_bar, textvariable=self.history_search_var, width=36)
        search_entry.pack(side="left", padx=(6, 12))
        search_entry.bind("<KeyRelease>", lambda _: self.apply_history_filters())
        ttk.Label(filter_bar, text="任务").pack(side="left")
        self.history_task_filter_box = ttk.Combobox(
            filter_bar,
            textvariable=self.history_task_filter_var,
            state="readonly",
            width=16,
        )
        self.history_task_filter_box.pack(side="left", padx=(6, 12))
        self.history_task_filter_box.bind("<<ComboboxSelected>>", lambda _: self.apply_history_filters())
        ttk.Label(filter_bar, text="结果").pack(side="left")
        self.history_status_filter_box = ttk.Combobox(
            filter_bar,
            textvariable=self.history_status_filter_var,
            state="readonly",
            width=12,
            values=["全部结果", "成功", "失败"],
        )
        self.history_status_filter_box.pack(side="left", padx=(6, 12))
        self.history_status_filter_box.bind("<<ComboboxSelected>>", lambda _: self.apply_history_filters())
        ttk.Label(filter_bar, text="视图").pack(side="left")
        self.history_view_mode_box = ttk.Combobox(
            filter_bar,
            textvariable=self.history_view_mode_var,
            state="readonly",
            width=12,
            values=["明细记录", "按技能聚合"],
        )
        self.history_view_mode_box.pack(side="left", padx=(6, 12))
        self.history_view_mode_box.bind("<<ComboboxSelected>>", lambda _: self.apply_history_filters())
        ttk.Button(filter_bar, text="清空筛选", command=self.reset_history_filters).pack(side="left")

        ttk.Label(frame, textvariable=self.history_summary_var).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 8),
        )

        list_frame = ttk.LabelFrame(frame, text="技能编写会话")
        list_frame.grid(row=3, column=0, sticky="nsew", padx=(0, 8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.history_listbox = tk.Listbox(list_frame, exportselection=False)
        self.history_listbox.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.history_listbox.bind("<<ListboxSelect>>", self.on_history_select)
        self.history_listbox.bind("<Double-Button-1>", lambda _event: self.set_selected_history_as_repair_session())
        history_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.history_listbox.yview)
        history_scroll.grid(row=0, column=1, sticky="ns", pady=6)
        self.history_listbox.configure(yscrollcommand=history_scroll.set)

        detail_frame = ttk.LabelFrame(frame, text="会话工作台")
        detail_frame.grid(row=3, column=1, sticky="nsew")
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)
        detail_frame.rowconfigure(1, weight=0)

        conversation_tabs = ttk.Notebook(detail_frame)
        conversation_tabs.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        chat_frame = ttk.Frame(conversation_tabs)
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)
        conversation_tabs.add(chat_frame, text="对话")
        self.repair_chat_text = tk.Text(chat_frame, wrap="word")
        self.repair_chat_text.grid(row=0, column=0, sticky="nsew")
        self.repair_chat_text.configure(state="disabled")

        info_frame = ttk.Frame(conversation_tabs)
        info_frame.columnconfigure(0, weight=1)
        info_frame.rowconfigure(0, weight=1)
        conversation_tabs.add(info_frame, text="任务信息")
        self.history_detail_text = tk.Text(info_frame, wrap="word")
        self.history_detail_text.grid(row=0, column=0, sticky="nsew")
        self.history_detail_text.configure(state="disabled")

        repair_frame = ttk.LabelFrame(detail_frame, text="发送消息")
        repair_frame.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))
        repair_frame.columnconfigure(0, weight=1)
        repair_frame.columnconfigure(1, weight=0)
        ttk.Label(repair_frame, textvariable=self.repair_session_var).grid(
            row=0,
            column=0,
            sticky="w",
            padx=6,
            pady=(6, 2),
        )
        ttk.Label(repair_frame, textvariable=self.repair_attachment_status_var).grid(
            row=0,
            column=1,
            sticky="e",
            padx=6,
            pady=(6, 2),
        )
        self.repair_issue_text = tk.Text(repair_frame, height=4, wrap="word")
        self.repair_issue_text.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=4)
        self.repair_issue_text.insert(
            "1.0",
            "在这里粘贴问题说明、战报日志或复现步骤；截图后直接 Ctrl+V 即可加入附件。",
        )
        self.repair_issue_text.bind("<Control-v>", self.paste_repair_clipboard)
        self.repair_issue_text.bind("<Control-V>", self.paste_repair_clipboard)
        attachment_row = ttk.Frame(repair_frame)
        attachment_row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))
        attachment_row.columnconfigure(0, weight=1)
        self.repair_attachment_listbox = tk.Listbox(attachment_row, height=3, exportselection=False)
        self.repair_attachment_listbox.grid(row=0, column=0, rowspan=3, sticky="ew", padx=(0, 6))
        ttk.Button(attachment_row, text="选择文件", command=self.add_repair_session_attachments).grid(
            row=0,
            column=1,
            sticky="ew",
            pady=(0, 3),
        )
        ttk.Button(attachment_row, text="清空附件", command=self.clear_repair_session_attachments).grid(
            row=1,
            column=1,
            sticky="ew",
            pady=3,
        )
        ttk.Button(attachment_row, text="发送修复", command=self.run_active_repair_session_fix).grid(
            row=2,
            column=1,
            sticky="ew",
            pady=(3, 0),
        )

    def build_log_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        notebook.add(frame, text="日志")

        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        toolbar.columnconfigure(4, weight=1)
        ttk.Button(toolbar, text="清空界面日志", command=self.clear_visible_log).grid(row=0, column=0, sticky="w")
        ttk.Button(toolbar, text="打开完整日志", command=self.open_full_log_file).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(toolbar, text="打开日志目录", command=self.open_log_directory).grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Label(toolbar, text="完整日志").grid(row=0, column=3, sticky="e", padx=(16, 6))
        ttk.Entry(toolbar, textvariable=self.full_log_path_var, state="readonly").grid(row=0, column=4, sticky="ew")

        self.log_text = tk.Text(frame, wrap="word")
        self.log_text.grid(row=1, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

    def load_initial_content(self) -> None:
        self.description_text.insert("1.0", self.settings.skill_description)
        self.protected_text.insert("1.0", self.settings.protected_files)
        self.constraints_text.insert("1.0", self.settings.additional_constraints)
        self.prompt_text.insert("1.0", self.settings.last_prompt or TEMPLATE_TEXT[self.current_template_key()])
        self.refresh_prompt()
        self.accept_current_requirement_context()

    def resolve_initial_config_dir(self) -> str:
        if self.settings.config_dir:
            return self.settings.config_dir
        for excel_path in (self.settings.skill_excel_path, self.settings.war_excel_path):
            if excel_path:
                return str(Path(excel_path).parent)
        return ""

    def find_config_excel(self, config_dir: Path, exact_name: str, patterns: list[str]) -> Path | None:
        exact_path = config_dir / exact_name
        if exact_path.exists():
            return exact_path
        for pattern in patterns:
            candidates = sorted(
                path for path in config_dir.glob(pattern)
                if path.is_file() and not path.name.startswith("~$")
            )
            if candidates:
                return candidates[0]
        return None

    def refresh_config_excel_paths(self, show_error: bool = True) -> bool:
        config_dir_value = self.config_dir_var.get().strip()
        if not config_dir_value:
            return False
        config_dir = Path(config_dir_value)
        skill_excel = self.find_config_excel(
            config_dir,
            self.SKILL_EXCEL_NAME,
            ["*技能表*skill*.xlsx", "*技能表*.xlsx"],
        )
        war_excel = self.find_config_excel(
            config_dir,
            self.WAR_EXCEL_NAME,
            ["*战报表*.xlsx"],
        )
        if skill_excel:
            self.skill_excel_var.set(str(skill_excel))
        if war_excel:
            self.war_excel_var.set(str(war_excel))
        if show_error and (not skill_excel or not war_excel):
            missing = []
            if not skill_excel:
                missing.append(self.SKILL_EXCEL_NAME)
            if not war_excel:
                missing.append(self.WAR_EXCEL_NAME)
            messagebox.showerror("错误", "配置目录下未找到：" + "、".join(missing))
            return False
        return bool(skill_excel and war_excel)

    def choose_config_dir(self) -> None:
        path = filedialog.askdirectory(initialdir=self.config_dir_var.get() or r"G:\\")
        if path:
            self.config_dir_var.set(path)
            self.refresh_config_excel_paths()
            self.refresh_command_preview()
            self.update_action_buttons()

    def choose_workspace(self) -> None:
        path = filedialog.askdirectory(initialdir=self.workspace_var.get() or r"G:\\")
        if path:
            self.workspace_var.set(path)
            self.refresh_battle_root()

    def choose_file(self, variable: tk.StringVar) -> None:
        initial_dir = str(Path(variable.get()).parent) if variable.get() else r"G:\\"
        path = filedialog.askopenfilename(initialdir=initial_dir)
        if path:
            if variable is self.payload_var:
                self.sync_payload_selection(path)
            else:
                variable.set(path)
            self.refresh_command_preview()
            self.update_action_buttons()

    def choose_dir(self, variable: tk.StringVar) -> None:
        path = filedialog.askdirectory(initialdir=variable.get() or r"G:\\")
        if path:
            variable.set(path)
            self.update_action_buttons()

    def ensure_codex_cli_ready(self) -> None:
        try:
            resolved = self.codex_runner.resolve_executable(self.codex_executable_var.get().strip())
        except Exception:
            return
        if self.codex_executable_var.get().strip() != resolved:
            self.codex_executable_var.set(resolved)

    def ensure_claude_cli_ready(self) -> None:
        try:
            resolved = self.claude_runner.resolve_executable(self.claude_executable_var.get().strip())
        except Exception:
            return
        if self.claude_executable_var.get().strip() != resolved:
            self.claude_executable_var.set(resolved)

    def auto_discover_codex_cli(self) -> None:
        try:
            resolved = self.codex_runner.resolve_executable(self.codex_executable_var.get().strip())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", str(exc))
            return
        self.codex_executable_var.set(resolved)
        self.refresh_command_preview()
        self.status_var.set("已定位 Codex CLI")

    def auto_discover_claude_cli(self) -> None:
        try:
            resolved = self.claude_runner.resolve_executable(self.claude_executable_var.get().strip())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", str(exc))
            return
        self.claude_executable_var.set(resolved)
        self.refresh_command_preview()
        self.status_var.set("已定位 Claude CLI")

    def auto_discover_local_python(self) -> None:
        try:
            resolved = self.local_script_runner.resolve_python_executable(self.python_executable_var.get().strip())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", str(exc))
            return
        self.python_executable_var.set(resolved)
        self.status_var.set("已定位本地 Python")

    def on_model_preset_change(self) -> None:
        key = label_to_key_map().get(self.model_preset_label_var.get(), MODEL_PRESETS[0].key)
        self.model_preset_key_var.set(key)
        self.apply_model_preset()

    def apply_model_preset(self) -> None:
        preset = get_preset(self.model_preset_key_var.get())
        self.model_preset_label_var.set(preset.label)
        if preset.vendor == "Anthropic":
            self.agent_backend_var.set("claude")
            self.claude_model_var.set(preset.model_name or "sonnet")
        else:
            self.codex_model_var.set(preset.model_name or "")
        self.refresh_model_note()
        self.refresh_command_preview()

    def apply_profile_shortcut(self, extra_args: str) -> None:
        self.codex_extra_args_var.set(extra_args)
        self.refresh_command_preview()

    def apply_scene_recommendation(self) -> None:
        preset_key = SCENE_TO_PRESET_KEY.get(self.scene_var.get())
        if not preset_key:
            return
        self.model_preset_key_var.set(preset_key)
        self.apply_model_preset()

    def refresh_model_note(self) -> None:
        preset = get_preset(self.model_preset_key_var.get())
        self.model_note_text.configure(state="normal")
        self.model_note_text.delete("1.0", "end")
        self.model_note_text.insert("1.0", build_preset_note(preset))
        self.model_note_text.configure(state="disabled")

    def refresh_command_preview(self) -> None:
        workspace_root = self.workspace_var.get().strip()
        if not workspace_root:
            self.command_preview_var.set("")
            return
        preset = get_preset(self.model_preset_key_var.get())
        try:
            if self.agent_backend_var.get() == "claude":
                command = self.claude_runner.build_command(
                    workspace_root=workspace_root,
                    executable_path=self.claude_executable_var.get().strip(),
                    model=self.claude_model_var.get().strip(),
                    extra_args=self.claude_extra_args_var.get().strip(),
                )
            else:
                command = self.codex_runner.build_command(
                    workspace_root=workspace_root,
                    output_file=str(self.default_output_file()),
                    executable_path=self.codex_executable_var.get().strip(),
                    model=self.codex_model_var.get().strip(),
                    extra_args=self.codex_extra_args_var.get().strip(),
                    preset_args=preset.preset_args,
                )
        except Exception as exc:  # noqa: BLE001
            self.command_preview_var.set(f"{self.current_backend_label()} CLI 未就绪: {exc}")
            return
        self.command_preview_var.set(" ".join(command))

    def set_health_text(self, text: str) -> None:
        if not hasattr(self, "health_text"):
            return
        self.health_text.configure(state="normal")
        self.health_text.delete("1.0", "end")
        self.health_text.insert("1.0", text)
        self.health_text.configure(state="disabled")

    def run_environment_check(self) -> None:
        if self.environment_check_running:
            return
        self.environment_check_running = True
        self.environment_health_var.set("环境体检：检查中...")

        workspace_root = self.workspace_var.get().strip()
        battle_root = self.battle_root_var.get().strip()
        python_executable = self.python_executable_var.get().strip()
        codex_executable = self.codex_executable_var.get().strip() or "codex"
        claude_executable = self.claude_executable_var.get().strip() or "claude"
        skill_excel = self.skill_excel_var.get().strip()
        war_excel = self.war_excel_var.get().strip()

        def worker() -> None:
            items = [
                self.environment_check_service.check_python(python_executable),
                self.environment_check_service.check_python_dependencies(python_executable, auto_install=True),
                self.environment_check_service.check_command("Codex CLI", codex_executable, ["--version"]),
                self.environment_check_service.check_command("Claude CLI", claude_executable, ["--version"]),
                self.environment_check_service.check_path("工作区", workspace_root, must_be_dir=True),
                self.environment_check_service.check_path("battle_root", battle_root, must_be_dir=True),
                self.environment_check_service.check_path("技能 Excel", skill_excel, must_be_file=True),
                self.environment_check_service.check_path("战报 Excel", war_excel, must_be_file=True),
            ]
            if battle_root and Path(battle_root).exists():
                items.append(
                    self.environment_check_service.check_write_access(
                        "battle 临时目录写权限",
                        str(Path(battle_root) / "temp_skill_workspace"),
                    )
                )
            failed = [item for item in items if not item.ok]
            summary = f"环境体检：{len(items) - len(failed)}/{len(items)} 项通过"
            rendered = self.environment_check_service.render(items)
            self.root.after(0, lambda: self.finish_environment_check(summary, rendered))

        threading.Thread(target=worker, name="skill-writer-env-check", daemon=True).start()

    def finish_environment_check(self, summary: str, rendered: str) -> None:
        self.environment_check_running = False
        self.environment_health_var.set(summary)
        current = self.task_health_snapshot()
        self.set_health_text(rendered + ("\n\n" + current if current else ""))
        self.append_log("[health] " + summary)

    def task_health_snapshot(self) -> str:
        task_dir = self.latest_task_dir_var.get().strip()
        payload = self.payload_var.get().strip()
        flags = self.get_workflow_progress_flags()
        labels = self.task_step_labels()
        completed = [labels[key] for key in self.workflow_step_order() if flags.get(key)]
        missing = [labels[key] for key in self.workflow_step_order() if not flags.get(key)]
        lines = ["当前任务健康："]
        lines.append(f"- 任务目录: {task_dir or '未选择'}")
        lines.append(f"- Payload: {payload or '未选择'}")
        lines.append(f"- 已完成: {', '.join(completed) if completed else '无'}")
        lines.append(f"- 下一步: {missing[0] if missing else '已完成'}")
        if task_dir and Path(task_dir).exists():
            memory = self.task_handoff_service.load_memory(task_dir)
            if memory:
                lines.append(f"- 结构化记忆: task_memory.json 已更新 ({memory.get('updated_at', 'unknown')})")
            else:
                lines.append("- 结构化记忆: 缺失，下一次执行步骤时会自动生成")
            artifacts = self.workspace_manager.find_task_artifacts(task_dir, limit=8)
            lines.append(f"- 最近产物: {len(artifacts)} 个")
            lines.extend(f"  - {path.relative_to(Path(task_dir))}" for path in artifacts[:8])
        return "\n".join(lines)

    def update_task_health_panel(self) -> None:
        snapshot = self.task_health_snapshot()
        next_line = next((line for line in snapshot.splitlines() if line.startswith("- 下一步:")), "")
        self.task_health_var.set(next_line.replace("- ", "当前任务：", 1) if next_line else "当前任务：未选择")
        if hasattr(self, "health_text"):
            current = self.health_text.get("1.0", "end").strip()
            env_part = current.split("\n\n当前任务健康：", 1)[0] if current else self.environment_health_var.get()
            self.set_health_text(env_part + "\n\n" + snapshot)

    def current_backend_label(self) -> str:
        return "Claude" if self.agent_backend_var.get() == "claude" else "Codex"

    def prompt_for_current_backend(self, prompt: str) -> str:
        if self.agent_backend_var.get() != "claude":
            return prompt
        skill_path = self.bundled_skill_service.bundled_skills_dir() / "family-battle-skill-writer" / "SKILL.md"
        normalized_prompt = prompt.replace("Use $family-battle-skill-writer\n\n", "", 1)
        return (
            "先读取并严格遵守下面这个本地技能说明文件，然后再执行任务；"
            "不要把它当成普通参考资料跳过，也不要重新发明一套流程。\n"
            f"技能说明文件: {skill_path}\n\n"
            f"{normalized_prompt}"
        )

    def current_agent_is_running(self) -> bool:
        return self.claude_runner.is_running() if self.agent_backend_var.get() == "claude" else self.codex_runner.is_running()

    def stop_current_agent(self) -> bool:
        return self.claude_runner.stop_running() if self.agent_backend_var.get() == "claude" else self.codex_runner.stop_running()

    def refresh_battle_root(self) -> None:
        battle_root = self.workspace_manager.resolve_battle_root(self.workspace_var.get())
        if battle_root:
            self.battle_root_var.set(str(battle_root))
            self.realign_workspace_bound_paths()
            self.refresh_temp_workspace_views()
            self.status_var.set("battle_root 已定位")
        else:
            self.battle_root_var.set("")
            self.latest_task_dir_var.set("")
            self.payload_var.set("")
            self.clear_recent_lists()
            self.status_var.set("未找到 battle_root")
        self.refresh_prompt()
        self.refresh_command_preview()
        self.update_action_buttons()

    def realign_workspace_bound_paths(self) -> None:
        workspace_root = self.workspace_var.get().strip()
        if not workspace_root:
            return

        for source, target in self.workspace_manager.migrate_legacy_global_dirs(workspace_root):
            self.append_log(f"[workspace] migrated global artifact: {source} -> {target}")

        if not self.workspace_manager.belongs_to_temp_workspace(self.latest_task_dir_var.get().strip(), workspace_root):
            self.latest_task_dir_var.set("")
        elif self.latest_task_dir_var.get().strip():
            for source, target in self.workspace_manager.ensure_task_layout(self.latest_task_dir_var.get().strip()):
                self.append_log(f"[workspace] migrated task artifact: {source} -> {target}")
            canonical_payload = self.workspace_manager.find_primary_payload_for_dir(self.latest_task_dir_var.get().strip())
            if canonical_payload and Path(self.payload_var.get().strip()).name == "temp_excel_payload.json":
                self.payload_var.set(str(canonical_payload))

        if not self.workspace_manager.belongs_to_temp_workspace(self.payload_var.get().strip(), workspace_root):
            self.payload_var.set(self.workspace_manager.default_payload_path(workspace_root))

        if self.latest_task_dir_var.get().strip():
            self.set_task_local_excel_dirs(self.latest_task_dir_var.get().strip())

        default_copy_dir = self.workspace_manager.default_temp_copy_dir(workspace_root, "excel_test_copy")
        if (
            not self.workspace_manager.belongs_to_temp_workspace(self.copy_dir_var.get().strip(), workspace_root)
            or self.copy_dir_var.get().strip().endswith(r"\temp_skill_workspace\excel_test_copy")
        ):
            self.copy_dir_var.set(default_copy_dir)

        default_backup_dir = self.workspace_manager.default_temp_copy_dir(workspace_root, "excel_backup")
        if (
            not self.workspace_manager.belongs_to_temp_workspace(self.backup_dir_var.get().strip(), workspace_root)
            or self.backup_dir_var.get().strip().endswith(r"\temp_skill_workspace\excel_backup")
        ):
            self.backup_dir_var.set(default_backup_dir)

    def set_task_local_excel_dirs(self, task_dir: str) -> None:
        if not task_dir:
            return
        path = Path(task_dir)
        if not path.exists() or not path.is_dir():
            return
        self.copy_dir_var.set(str(self.workspace_manager.task_local_dir(path, "excel_test_copy")))
        self.backup_dir_var.set(str(self.workspace_manager.task_local_dir(path, "excel_backup")))

    def clear_recent_lists(self) -> None:
        self.recent_payloads = []
        self.recent_task_dirs = []
        self.current_task_artifacts = []
        for listbox in self.payload_listboxes:
            listbox.delete(0, "end")
        for listbox in self.task_dir_listboxes:
            listbox.delete(0, "end")
        self.artifact_listbox.delete(0, "end")
        self.artifact_summary_var.set("当前没有任务产物")
        self.update_action_buttons()

    def refresh_temp_workspace_views(self, force_latest: bool = False) -> None:
        current_payload = self.payload_var.get().strip()
        current_task_dir = self.latest_task_dir_var.get().strip()
        workspace_root = self.workspace_var.get().strip()

        if current_payload and not self.workspace_manager.belongs_to_temp_workspace(current_payload, workspace_root):
            current_payload = ""
            self.payload_var.set("")
        if current_task_dir and not self.workspace_manager.belongs_to_temp_workspace(current_task_dir, workspace_root):
            current_task_dir = ""
            self.latest_task_dir_var.set("")

        self.recent_task_dirs = self.workspace_manager.find_recent_task_dirs(workspace_root)[:5]
        self.recent_payloads = self.workspace_manager.find_payload_candidates(workspace_root)[:5]

        selected_task_dir = ""
        selected_payload = ""

        if force_latest and self.recent_payloads:
            selected_payload = str(self.recent_payloads[0])
            payload_parent = self.workspace_manager.task_dir_for_payload(self.recent_payloads[0])
            if payload_parent.exists() and payload_parent.is_dir():
                selected_task_dir = str(payload_parent)

        if self.recent_task_dirs:
            if (not force_latest) and current_task_dir and Path(current_task_dir).exists():
                selected_task_dir = current_task_dir
            elif (not force_latest) and current_payload and Path(current_payload).exists():
                payload_parent = self.workspace_manager.task_dir_for_payload(current_payload)
                temp_root = self.workspace_manager.temp_workspace_path(workspace_root)
                if temp_root and payload_parent != temp_root:
                    selected_task_dir = str(payload_parent)
            elif not selected_task_dir:
                selected_task_dir = str(self.recent_task_dirs[0])

            selected_task_path = Path(selected_task_dir)
            preferred_payload = self.workspace_manager.find_primary_payload_for_dir(selected_task_path)
            if preferred_payload and (force_latest or not current_payload or Path(current_payload).parent == selected_task_path):
                selected_payload = str(preferred_payload)

            self.latest_task_dir_var.set(selected_task_dir)
            self.fill_task_dir_listbox(selected_task_dir)
        else:
            self.latest_task_dir_var.set("")
            self.fill_task_dir_listbox("")

        if self.recent_payloads:
            if (not force_latest) and current_payload and Path(current_payload).exists() and not selected_payload:
                selected_payload = current_payload
            elif selected_task_dir and not selected_payload:
                preferred_payload = self.workspace_manager.find_primary_payload_for_dir(selected_task_dir)
                if preferred_payload:
                    selected_payload = str(preferred_payload)
            elif not selected_payload:
                selected_payload = str(self.recent_payloads[0])
            self.payload_var.set(selected_payload)
            self.fill_payload_listbox(selected_payload)
        else:
            self.payload_var.set(self.workspace_manager.default_payload_path(workspace_root))
            self.fill_payload_listbox("")

        if selected_task_dir:
            self.set_task_local_excel_dirs(selected_task_dir)
            self.load_task_context_into_editor(selected_task_dir)
        self.refresh_current_task_artifacts()
        self.update_action_buttons()

    def fill_payload_listbox(self, selected_path: str) -> None:
        self.syncing_recent_lists = True
        try:
            for listbox in self.payload_listboxes:
                listbox.delete(0, "end")
                for index, path in enumerate(self.recent_payloads):
                    listbox.insert("end", self.format_recent_path(path))
                    if selected_path and Path(selected_path) == path:
                        listbox.selection_set(index)
        finally:
            self.syncing_recent_lists = False

    def fill_task_dir_listbox(self, selected_path: str) -> None:
        self.syncing_recent_lists = True
        try:
            for listbox in self.task_dir_listboxes:
                listbox.delete(0, "end")
                for index, path in enumerate(self.recent_task_dirs):
                    listbox.insert("end", self.format_recent_path(path))
                    if selected_path and Path(selected_path) == path:
                        listbox.selection_set(index)
        finally:
            self.syncing_recent_lists = False

    def refresh_current_task_artifacts(self) -> None:
        task_dir = self.latest_task_dir_var.get().strip()
        self.current_task_artifacts = self.workspace_manager.find_task_artifacts(task_dir, limit=20)
        self.artifact_listbox.delete(0, "end")

        if not task_dir:
            self.artifact_summary_var.set("当前没有可用的任务目录")
            return
        if not Path(task_dir).exists():
            self.artifact_summary_var.set("当前任务目录不存在")
            return
        if not self.current_task_artifacts:
            self.artifact_summary_var.set("当前任务目录下未发现可展示的产物文件")
            return

        for path in self.current_task_artifacts:
            self.artifact_listbox.insert("end", self.format_artifact_path(path, Path(task_dir)))

        latest_artifact = self.current_task_artifacts[0]
        self.artifact_listbox.selection_set(0)
        self.artifact_summary_var.set(
            f"共发现 {len(self.current_task_artifacts)} 个产物，最新文件: {latest_artifact.name}"
        )

    def format_artifact_path(self, path: Path, task_dir: Path) -> str:
        try:
            return str(path.relative_to(task_dir))
        except ValueError:
            return str(path)

    def format_recent_path(self, path: Path) -> str:
        temp_root = self.workspace_manager.temp_workspace_root(self.workspace_var.get())
        if temp_root:
            try:
                relative = path.relative_to(temp_root)
                return str(relative)
            except ValueError:
                pass
        return str(path)

    def normalize_path(self, value: str) -> str:
        if not value.strip():
            return ""
        try:
            return str(Path(value).resolve())
        except OSError:
            return str(Path(value))

    def path_belongs_to_current_temp_workspace(self, value: str) -> bool:
        return self.workspace_manager.belongs_to_temp_workspace(value, self.workspace_var.get().strip())

    def sync_payload_selection(self, payload_path: str) -> None:
        normalized_payload = self.normalize_path(payload_path)
        self.payload_var.set(normalized_payload)

        selected_task_dir = ""
        if normalized_payload and self.path_belongs_to_current_temp_workspace(normalized_payload):
            payload_parent = self.workspace_manager.task_dir_for_payload(normalized_payload)
            temp_root = self.workspace_manager.temp_workspace_path(self.workspace_var.get().strip())
            if temp_root and payload_parent != temp_root:
                selected_task_dir = str(payload_parent)
                self.latest_task_dir_var.set(selected_task_dir)
                self.set_task_local_excel_dirs(selected_task_dir)
            else:
                self.latest_task_dir_var.set("")

        if selected_task_dir:
            self.load_task_context_into_editor(selected_task_dir)
        self.refresh_current_task_artifacts()
        self.fill_payload_listbox(normalized_payload)
        if self.latest_task_dir_var.get().strip():
            self.fill_task_dir_listbox(self.latest_task_dir_var.get().strip())
        self.update_action_buttons()

    def sync_task_dir_selection(self, task_dir: str) -> None:
        normalized_task_dir = self.normalize_path(task_dir)
        self.latest_task_dir_var.set(normalized_task_dir)
        self.set_task_local_excel_dirs(normalized_task_dir)

        preferred_payload = self.workspace_manager.find_primary_payload_for_dir(normalized_task_dir)
        if preferred_payload:
            self.payload_var.set(str(preferred_payload))
        else:
            self.workspace_manager.ensure_task_layout(normalized_task_dir)
            self.payload_var.set(str(self.workspace_manager.canonical_task_file(normalized_task_dir, "temp_excel_payload.json")))

        self.load_task_context_into_editor(normalized_task_dir)
        self.refresh_current_task_artifacts()
        self.fill_task_dir_listbox(normalized_task_dir)
        self.fill_payload_listbox(self.payload_var.get().strip())
        self.update_action_buttons()

    def load_task_context(self, task_dir: str) -> dict[str, str]:
        if not task_dir or not Path(task_dir).exists():
            return {}
        state = self.task_handoff_service.load_state(task_dir)
        memory = self.task_handoff_service.load_memory(task_dir)
        handoff = self.task_handoff_service.read_handoff(task_dir)

        def pick(*values: object) -> str:
            for value in values:
                text = str(value or "").strip()
                if text and text.lower() != "(none)":
                    return text
            return ""

        requirement = pick(
            state.get("skill_description"),
            memory.get("requirement"),
            self.extract_markdown_section(handoff, "Original Requirement"),
        )
        constraints = pick(
            state.get("additional_constraints"),
            memory.get("constraints"),
            self.extract_markdown_section(handoff, "Constraints"),
        )
        return {
            "requirement": requirement,
            "constraints": constraints,
            "agent_backend": pick(state.get("agent_backend"), memory.get("agent_backend"), self.agent_backend_var.get()),
            "model_name": pick(state.get("model_name"), memory.get("model_name")),
            "session_id": pick(state.get("session_id"), memory.get("session_id")),
            "updated_at": pick(state.get("updated_at"), memory.get("updated_at")),
            "status": pick(state.get("status"), memory.get("status")),
        }

    def extract_markdown_section(self, text: str, heading: str) -> str:
        if not text:
            return ""
        marker = f"## {heading}"
        start = text.find(marker)
        if start < 0:
            return ""
        start = text.find("\n", start)
        if start < 0:
            return ""
        end = text.find("\n## ", start + 1)
        section = text[start:end if end >= 0 else len(text)].strip()
        return section

    def load_task_context_into_editor(self, task_dir: str) -> None:
        context = self.load_task_context(task_dir)
        if not context:
            self.suppress_requirement_change = True
            try:
                self.description_text.delete("1.0", "end")
                self.refresh_prompt()
                self.accept_current_requirement_context()
                self.append_log(f"[workflow-resume] 任务目录没有保存技能描述，已清空描述框: {task_dir}")
            finally:
                self.suppress_requirement_change = False
            return
        changed = False
        self.suppress_requirement_change = True
        try:
            if context.get("requirement"):
                self.description_text.delete("1.0", "end")
                self.description_text.insert("1.0", context["requirement"])
                changed = True
            else:
                self.description_text.delete("1.0", "end")
                changed = True
            if context.get("constraints"):
                self.constraints_text.delete("1.0", "end")
                self.constraints_text.insert("1.0", context["constraints"])
                changed = True
            if changed:
                self.refresh_prompt()
                self.accept_current_requirement_context()
                self.append_log(f"[workflow-resume] 已从任务目录回填技能描述: {task_dir}")
        finally:
            self.suppress_requirement_change = False

    def restore_active_task_selection(self) -> None:
        workspace_root = self.workspace_var.get().strip()
        runs = self.active_task_service.load()
        resumable = [
            item
            for item in runs.values()
            if item.get("status") in {"running", "interrupted", "failed"}
            and self.normalize_path(str(item.get("workspace_root", ""))) == self.normalize_path(workspace_root)
        ]
        if not resumable:
            return
        resumable.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        latest = resumable[0]
        task_dir = str(latest.get("task_dir", "") or "")
        payload = str(latest.get("payload_path", "") or "")
        if task_dir and Path(task_dir).exists():
            self.latest_task_dir_var.set(task_dir)
            self.load_task_context_into_editor(task_dir)
        if payload and Path(payload).exists():
            self.payload_var.set(payload)
        if task_dir or payload:
            self.append_log("[workflow-resume] 已恢复上次未完成任务的目录选择。")
            self.refresh_current_task_artifacts()

    def validate_current_workspace_selection(self) -> str:
        task_dir = self.normalize_path(self.latest_task_dir_var.get())
        payload = self.normalize_path(self.payload_var.get())

        if task_dir and not self.path_belongs_to_current_temp_workspace(task_dir):
            return "当前任务目录不属于当前 battle_root，请刷新列表或重新选择。"
        if payload and not self.path_belongs_to_current_temp_workspace(payload):
            return "当前 payload 不属于当前 battle_root，请刷新列表或重新选择。"
        if task_dir and payload:
            payload_parent = self.normalize_path(str(self.workspace_manager.task_dir_for_payload(payload)))
            if payload_parent != task_dir:
                return "当前 payload 不属于当前任务目录，请重新选择任务目录或点击“自动发现”。"
        return ""

    def is_task_running(self) -> bool:
        return (
            self.codex_runner.is_running()
            or self.claude_runner.is_running()
            or self.local_script_runner.is_running()
            or self.writeback_service.is_running()
            or bool(self.current_task_name)
        )

    def workflow_step_order(self) -> list[str]:
        return ["develop", "audit", "compile", "test", "preview", "copy", "real"]

    def current_target_key(self) -> str:
        task_dir = self.normalize_path(self.latest_task_dir_var.get())
        payload = self.normalize_path(self.payload_var.get())
        return task_dir or payload

    def prompt_hash(self, prompt: str = "") -> str:
        value = prompt if prompt else self.prompt_text.get("1.0", "end").strip()
        return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()

    def current_prompt_hash(self) -> str:
        return self.prompt_hash(self.prompt_text.get("1.0", "end").strip())

    def accept_current_requirement_context(self) -> None:
        if hasattr(self, "prompt_text"):
            self.accepted_workflow_prompt_hash = self.current_prompt_hash()

    def has_requirement_changed(self) -> bool:
        if self.suppress_requirement_change or not self.accepted_workflow_prompt_hash:
            return False
        return self.current_prompt_hash() != self.accepted_workflow_prompt_hash

    def on_requirement_text_changed(self, _event: object | None = None) -> None:
        self.refresh_prompt()
        if self.suppress_requirement_change:
            return
        if self.workflow_refresh_after_id:
            self.root.after_cancel(self.workflow_refresh_after_id)
        self.workflow_refresh_after_id = self.root.after(150, self.on_requirement_refresh_due)

    def on_requirement_refresh_due(self) -> None:
        self.workflow_refresh_after_id = None
        if self.has_requirement_changed():
            self.stop_serial_workflow("检测到技能描述变更，已停止沿用旧流程状态。")
        self.update_action_buttons()
        self.update_task_health_panel()

    def detach_old_artifacts_for_new_requirement(self) -> None:
        if not self.has_requirement_changed():
            return
        self.reset_current_task_selection_for_new_requirement()

    def sync_changed_requirement_to_current_task(self) -> bool:
        if not self.has_requirement_changed():
            return False
        target_key = self.current_target_key()
        task_dir = self.latest_task_dir_var.get().strip()
        if not target_key or not task_dir or not Path(task_dir).exists():
            self.detach_old_artifacts_for_new_requirement()
            self.accept_current_requirement_context()
            return True

        self.stop_serial_workflow("检测到技能描述变更，已重置当前任务到开发步骤。")
        self.active_task_service.clear(target_key)
        self.workflow_state_service.set(target_key, "develop")
        self.write_task_handoff(status="requirement_changed", current_step="", next_step="develop")
        self.accept_current_requirement_context()
        self.append_log(f"[workflow] 已同步修改后的技能描述到当前任务: {task_dir}")
        return True

    def reset_current_task_selection_for_new_requirement(self) -> None:
        workspace_root = self.workspace_var.get().strip()
        self.latest_task_dir_var.set("")
        if workspace_root:
            self.payload_var.set(self.workspace_manager.default_payload_path(workspace_root))
        else:
            self.payload_var.set("")
        self.current_task_artifacts = []
        if hasattr(self, "artifact_listbox"):
            self.artifact_listbox.delete(0, "end")
        self.artifact_summary_var.set("检测到新需求：已脱离旧任务产物，下一步会创建新的任务目录。")

    def default_new_task_name(self) -> str:
        title = self.extract_skill_title(self.get_text(self.description_text) if hasattr(self, "description_text") else "")
        return self.workspace_manager.safe_task_dir_name(title, "skill_task")

    def confirm_new_skill_development(self) -> None:
        if self.is_task_running():
            messagebox.showwarning("提示", "当前已有任务在执行，请等待完成或停止后再确认新技能开发。")
            return
        self.refresh_prompt()
        if not self.get_text(self.description_text):
            messagebox.showwarning("提示", "请先填写技能描述。")
            return

        old_target = self.current_target_key()
        if old_target:
            self.workflow_state_service.clear(old_target)
        task_name = simpledialog.askstring(
            "新建技能任务",
            "给这次技能开发起一个任务名：",
            initialvalue=self.default_new_task_name(),
            parent=self.root,
        )
        if task_name is None:
            return
        task_dir = self.workspace_manager.create_named_task_dir(self.workspace_var.get().strip(), task_name)
        if not task_dir:
            messagebox.showerror("错误", "当前工作目录下未识别到 battle_root，无法创建任务目录。")
            return
        self.stop_serial_workflow("已确认新的技能开发，旧流程状态不再沿用。")
        self.latest_task_dir_var.set(str(task_dir))
        self.payload_var.set(str(self.workspace_manager.canonical_task_file(task_dir, "temp_excel_payload.json")))
        self.set_task_local_excel_dirs(str(task_dir))
        self.refresh_current_task_artifacts()
        self.accept_current_requirement_context()
        self.write_task_handoff(status="pending", current_step="", next_step="develop")
        self.status_var.set("已确认新技能开发")
        self.set_task_stage("等待开发")
        self.append_log(f"[workflow] 已新建技能任务：{task_dir}")
        self.update_action_buttons()
        self.update_task_health_panel()

    def develop_resume_key(self, prompt: str = "") -> str:
        if self.has_requirement_changed():
            workspace_root = self.normalize_path(self.workspace_var.get())
            return f"{workspace_root}::develop::{self.prompt_hash(prompt)}"
        target_key = self.current_target_key()
        if target_key:
            return target_key
        workspace_root = self.normalize_path(self.workspace_var.get())
        return f"{workspace_root}::develop::{self.prompt_hash(prompt)}"

    def active_task_target_keys(self, prompt: str = "") -> list[str]:
        keys = []
        current = "" if self.has_requirement_changed() else self.current_target_key()
        if current:
            keys.append(current)
        fallback = self.develop_resume_key(prompt)
        if fallback and fallback not in keys:
            keys.append(fallback)
        return keys

    def find_resumable_develop_task(self, prompt: str) -> tuple[str, dict[str, object]] | None:
        current_target = self.current_target_key()
        target_keys = self.active_task_target_keys(prompt)
        matched = self.active_task_service.find_resumable(
            step="develop",
            target_keys=target_keys,
            workspace_root=self.workspace_var.get().strip(),
            prompt_hash=self.prompt_hash(prompt),
            allow_workspace_fallback=not bool(current_target),
        )
        if matched:
            return matched
        if current_target:
            return None
        return self.active_task_service.find_resumable(
            step="develop",
            target_keys=self.active_task_target_keys(""),
            workspace_root=self.workspace_var.get().strip(),
            prompt_hash="",
            allow_workspace_fallback=True,
        )

    def build_resume_develop_prompt(self, original_prompt: str, task_info: dict[str, object]) -> str:
        task_dir = str(task_info.get("task_dir", "") or self.latest_task_dir_var.get().strip())
        payload = str(task_info.get("payload_path", "") or self.payload_var.get().strip())
        previous_backend = str(task_info.get("agent_backend", "") or "未知")
        context_block = self.build_local_task_context_block(task_dir, payload)
        return (
            "继续上一次未完成的技能开发任务，不要重新创建一套新的任务目录或新的脚本方案。\n"
            "优先检查并沿用已经存在的 temp_skill_workspace 任务目录、Lua 脚本、临时配置、payload、说明文档和测试文件。\n"
            "如果发现上次只完成了一部分，请在原有产物基础上补齐、修复、验证，并保持同一个技能方案继续推进。\n\n"
            f"上次执行后端: {previous_backend}\n"
            f"上次任务目录: {task_dir or '未识别'}\n"
            f"上次 payload: {payload or '未识别'}\n\n"
            f"{context_block}\n\n"
            "原始需求如下：\n"
            f"{original_prompt}"
        )

    def build_named_task_develop_prompt(self, original_prompt: str) -> str:
        task_dir = self.latest_task_dir_var.get().strip()
        payload = self.payload_var.get().strip()
        if not task_dir:
            return original_prompt
        return (
            "本次是工具中已确认命名的一轮技能开发，请严格使用下面这个任务目录作为本次所有临时产物的管理目录。\n"
            "不要把本次产物写到其他旧任务目录，也不要复用其他技能任务的 payload、临时 Excel、测试文件或 repair 目录。\n"
            f"本次任务目录: {task_dir}\n"
            f"本次 payload: {payload or '请写到任务目录/config/temp_excel_payload.json'}\n"
            "本次目录结构约定: config/ 放 payload 和临时配置；scripts/ 放临时 Lua/辅助脚本；tests/ 放测试；docs/ 放实现说明；"
            "excel_test_copy/ 放本次 Excel 副本；excel_backup/ 放本次正式回写备份。\n\n"
            f"{original_prompt}"
        )

    def build_local_task_context_block(self, task_dir: str, payload: str) -> str:
        lines = ["本地任务接力上下文（优先依赖这些本地产物，而不是重新从 0 扫描）："]
        handoff_text = self.task_handoff_service.read_handoff(task_dir)
        if handoff_text:
            lines.extend(
                [
                    "- 任务交接文件已存在，续接时必须优先读取并遵守:",
                    "```markdown",
                    handoff_text[-8000:],
                    "```",
                ]
            )
        memory = self.task_handoff_service.load_memory(task_dir)
        if memory:
            lines.extend(
                [
                    "- 结构化任务记忆已存在，跨模型续接时优先遵守:",
                    "```json",
                    json.dumps(memory, ensure_ascii=False, indent=2)[-8000:],
                    "```",
                ]
            )
        task_path = Path(task_dir) if task_dir else None
        if task_path and task_path.exists():
            lines.append(f"- 任务目录存在: {task_path}")
            artifact_names = sorted(path.name for path in task_path.iterdir() if path.is_file())
            if artifact_names:
                lines.append("- 已有产物: " + ", ".join(artifact_names[:20]))
        if payload and Path(payload).exists():
            lines.append(f"- payload 已存在: {payload}")
        output_file = self.default_output_file()
        if output_file.exists():
            try:
                text = output_file.read_text(encoding="utf-8", errors="replace").strip()
            except Exception:  # noqa: BLE001
                text = ""
            if text:
                excerpt = text[-4000:]
                lines.extend(
                    [
                        "- 上一次模型输出摘要:",
                        "```text",
                        excerpt,
                        "```",
                    ]
                )
        return "\n".join(lines)

    def task_step_labels(self) -> dict[str, str]:
        return {
            "develop": "技能开发",
            "audit": "本地预审",
            "compile": "本地编译",
            "test": "技能测试",
            "preview": "预览回写",
            "copy": "写入 Excel 副本",
            "real": "写回正式 Excel",
        }

    def write_task_handoff(self, *, status: str, current_step: str = "", next_step: str = "") -> None:
        task_dir = self.latest_task_dir_var.get().strip()
        if not task_dir or not Path(task_dir).exists():
            return
        flags = self.get_workflow_progress_flags()
        labels = self.task_step_labels()
        completed_steps = [labels[step] for step in self.workflow_step_order() if flags.get(step)]
        completed_step_keys = [step for step in self.workflow_step_order() if flags.get(step)]
        if not next_step:
            for step in self.workflow_step_order():
                if not flags.get(step):
                    next_step = labels[step]
                    break
            else:
                next_step = "已完成"
        artifacts = [str(path) for path in self.workspace_manager.find_task_artifacts(task_dir, limit=40)]
        recent_output = ""
        output_file = self.default_output_file()
        if output_file.exists():
            try:
                recent_output = output_file.read_text(encoding="utf-8", errors="replace").strip()[-6000:]
            except OSError:
                recent_output = ""
        settings = self.collect_settings()
        active_info = self.active_task_service.load().get(self.current_active_task_key, {}) if self.current_active_task_key else {}
        payload = {
            "status": status,
            "current_step": current_step,
            "next_step": next_step,
            "workspace_root": settings.workspace_root,
            "battle_root": self.battle_root_var.get().strip(),
            "task_dir": task_dir,
            "payload_path": self.payload_var.get().strip(),
            "agent_backend": settings.agent_backend,
            "model_name": settings.claude_model if settings.agent_backend == "claude" else settings.codex_model,
            "session_id": str(active_info.get("session_id", "") or ""),
            "completed_steps": completed_steps,
            "completed_step_keys": completed_step_keys,
            "artifacts": artifacts,
            "skill_description": settings.skill_description,
            "additional_constraints": settings.additional_constraints,
            "recent_output": recent_output,
        }
        written = self.task_handoff_service.write(task_dir, payload)
        if written:
            self.append_log(f"[handoff] 已更新任务交接文件: {written[1]}")
            self.update_task_health_panel()

    def mark_active_task_started(
        self,
        *,
        target_key: str,
        task_name: str,
        step: str,
        prompt: str = "",
        resumed_from: str = "",
    ) -> None:
        self.active_task_service.upsert(
            target_key,
            {
                "task_name": task_name,
                "step": step,
                "status": "running",
                "workspace_root": self.workspace_var.get().strip(),
                "battle_root": self.battle_root_var.get().strip(),
                "task_dir": self.latest_task_dir_var.get().strip(),
                "payload_path": self.payload_var.get().strip(),
                "prompt_hash": self.prompt_hash(prompt) if prompt else "",
                "resumed_from": resumed_from,
                "agent_backend": self.agent_backend_var.get().strip() or "codex",
            },
        )
        self.write_task_handoff(status="running", current_step=step)

    def update_active_task_session(self, target_key: str, session_id: str, session_file: str) -> None:
        self.active_task_service.update(
            target_key,
            session_id=session_id,
            session_file=session_file,
        )
        self.log_queue.put(f"[workflow-resume] 已记录 {self.current_backend_label()} session: {session_id}")
        self.write_task_handoff(status="running")

    def parse_history_timestamp(self, value: str) -> datetime | None:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    def get_workflow_reset_state(self) -> dict[str, str] | None:
        return self.workflow_state_service.get(self.current_target_key())

    def apply_workflow_reset(self) -> None:
        if self.is_task_running():
            messagebox.showwarning("提示", "当前有任务在执行，不能重置流程。")
            return
        target_key = self.current_target_key()
        if not target_key:
            messagebox.showwarning("提示", "当前没有可识别的任务目录或 payload，不能重置流程。")
            return

        selected = self.workflow_reset_var.get().strip()
        if selected == "按历史自动判断":
            self.workflow_state_service.clear(target_key)
            self.append_log("[workflow] 已清除当前目标的流程重置，恢复按历史自动判断。")
            self.status_var.set("已清除流程重置")
        else:
            step = self.task_name_to_step(selected)
            if not step:
                messagebox.showwarning("提示", "无效的流程重置目标。")
                return
            cleanup_paths = self.collect_workflow_reset_cleanup_paths(step)
            if cleanup_paths:
                preview = "\n".join(str(path) for path in cleanup_paths[:12])
                if len(cleanup_paths) > 12:
                    preview += f"\n... 另有 {len(cleanup_paths) - 12} 个文件"
                confirm = messagebox.askyesno(
                    "确认清理",
                    f"重置到“{selected}”会清除该步骤及后续步骤的旧产物，共 {len(cleanup_paths)} 个文件。\n\n{preview}\n\n是否继续？",
                )
                if not confirm:
                    self.append_log("[workflow] 已取消流程重置，未清理旧产物。")
                    return
                removed, failed = self.remove_workflow_reset_artifacts(cleanup_paths)
                self.append_log(f"[workflow] 重置清理完成：删除 {removed} 个旧产物，失败 {failed} 个。")
            self.active_task_service.clear(target_key)
            self.workflow_state_service.set(target_key, step)
            self.append_log(f"[workflow] 已将当前目标流程重置到：{selected}")
            self.status_var.set(f"已重置到：{selected}")

        self.stop_serial_workflow()
        self.refresh_current_task_artifacts()
        self.write_task_handoff(status="reset", current_step=step if selected != "按历史自动判断" else "")
        self.update_action_buttons()

    def collect_workflow_reset_cleanup_paths(self, reset_step: str) -> list[Path]:
        step_order = self.workflow_step_order()
        if reset_step not in step_order:
            return []

        workspace_root = self.workspace_var.get().strip()
        task_dir_value = self.latest_task_dir_var.get().strip()
        reset_index = step_order.index(reset_step)
        cleanup: list[Path] = []

        if task_dir_value and self.workspace_manager.belongs_to_temp_workspace(task_dir_value, workspace_root):
            task_dir = Path(task_dir_value)
            cleanup.extend(self.collect_task_dir_reset_artifacts(task_dir, reset_index, step_order))

        if reset_index <= step_order.index("copy"):
            cleanup.extend(self.collect_excel_copy_reset_artifacts(workspace_root))

        return self.unique_existing_paths(cleanup)

    def collect_task_dir_reset_artifacts(self, task_dir: Path, reset_index: int, step_order: list[str]) -> list[Path]:
        if not task_dir.exists() or not task_dir.is_dir():
            return []

        step_patterns = {
            "develop": (
                "config/temp_excel_payload.json",
                "temp_excel_payload.json",
                "docs/IMPLEMENTATION.md",
                "IMPLEMENTATION.md",
                "test_runtime_validation.lua",
                "action_*.lua",
                "buff_*.lua",
            ),
            "compile": (
                "config/temp_skill_config.lua",
                "temp_skill_config.lua",
                "tests/test_skill_temp.lua",
                "test_skill_temp.lua",
            ),
            "test": (
                "test_result*.json",
                "test_result*.log",
                "local_test*.json",
                "local_test*.log",
            ),
            "preview": (
                "excel_preview*.json",
                "excel_preview*.log",
                "writeback_preview*.json",
                "writeback_preview*.log",
            ),
        }

        cleanup: list[Path] = []
        for step in step_order[reset_index:]:
            for pattern in step_patterns.get(step, ()):
                cleanup.extend(path for path in task_dir.glob(pattern) if path.is_file())
        return cleanup

    def collect_excel_copy_reset_artifacts(self, workspace_root: str) -> list[Path]:
        copy_dir_value = self.copy_dir_var.get().strip()
        if not copy_dir_value or not self.workspace_manager.belongs_to_temp_workspace(copy_dir_value, workspace_root):
            return []

        copy_dir = Path(copy_dir_value)
        if not copy_dir.exists() or not copy_dir.is_dir():
            return []

        cleanup: list[Path] = []
        for workbook_value in (self.skill_excel_var.get().strip(), self.war_excel_var.get().strip()):
            if not workbook_value:
                continue
            workbook = Path(workbook_value)
            if not workbook.name:
                continue
            cleanup.extend(path for path in copy_dir.glob(workbook.name) if path.is_file())
            cleanup.extend(path for path in copy_dir.glob(f"{workbook.stem}_*{workbook.suffix}") if path.is_file())
        return cleanup

    def unique_existing_paths(self, paths: list[Path]) -> list[Path]:
        seen: set[str] = set()
        result: list[Path] = []
        for path in paths:
            try:
                resolved = str(path.resolve())
            except OSError:
                resolved = str(path)
            if resolved in seen or not path.exists() or not path.is_file():
                continue
            seen.add(resolved)
            result.append(path)
        return result

    def remove_workflow_reset_artifacts(self, paths: list[Path]) -> tuple[int, int]:
        removed = 0
        failed = 0
        for path in paths:
            try:
                path.unlink()
                removed += 1
                self.append_log(f"[workflow-cleanup] deleted: {path}")
            except OSError as exc:
                failed += 1
                self.append_log(f"[workflow-cleanup] failed: {path} :: {exc}")
        return removed, failed

    def mark_downstream_steps_dirty_after_develop(self) -> None:
        target_key = self.current_target_key()
        if not target_key:
            return
        cleanup_paths = self.collect_workflow_reset_cleanup_paths("audit")
        removed, failed = self.remove_workflow_reset_artifacts(cleanup_paths)
        self.workflow_state_service.set(target_key, "audit")
        self.active_task_service.clear(target_key)
        if cleanup_paths:
            self.append_log(
                f"[workflow] 开发/续写已更新产物，后续步骤将从“本地预审”重新执行；旧副本/预览产物清理 {removed} 个，失败 {failed} 个。"
            )
        else:
            self.append_log("[workflow] 开发/续写已更新产物，后续步骤将从“本地预审”重新执行。")

    def toggle_step_overview(self) -> None:
        self.step_overview_visible = not self.step_overview_visible
        self.update_step_overview_visibility()

    def toggle_workbench_advanced(self) -> None:
        self.workbench_advanced_visible = not self.workbench_advanced_visible
        self.update_workbench_advanced_visibility()

    def update_workbench_advanced_visibility(self) -> None:
        if not hasattr(self, "workbench_advanced_frame"):
            return
        if self.workbench_advanced_visible:
            self.workbench_advanced_frame.grid()
            self.workbench_advanced_button.configure(text="隐藏高级设置")
        else:
            self.workbench_advanced_frame.grid_remove()
            self.workbench_advanced_button.configure(text="显示高级设置")

    def update_step_overview_visibility(self) -> None:
        if not hasattr(self, "step_overview_frame"):
            return
        if self.step_overview_visible:
            self.step_overview_frame.grid()
            self.future_steps_frame.grid()
            self.step_overview_toggle_var.set("隐藏全览")
        else:
            self.step_overview_frame.grid_remove()
            self.future_steps_frame.grid_remove()
            self.step_overview_toggle_var.set("显示全览")

    def history_matches_current_target(self, entry: TaskHistoryEntry, task_dir: str, payload: str) -> bool:
        entry_task_dir = self.normalize_path(entry.task_dir)
        entry_payload = self.normalize_path(entry.payload_path)
        return (task_dir and entry_task_dir == task_dir) or (payload and entry_payload == payload)

    def get_workflow_progress_flags(self) -> dict[str, bool]:
        task_dir = self.normalize_path(self.latest_task_dir_var.get())
        payload = self.normalize_path(self.payload_var.get())
        flags = {
            "develop": False,
            "audit": False,
            "compile": False,
            "test": False,
            "preview": False,
            "copy": False,
            "real": False,
        }
        if self.has_requirement_changed():
            return flags

        matching_entries = [entry for entry in self.history_entries if self.history_matches_current_target(entry, task_dir, payload)]
        handoff_state = self.task_handoff_service.load_state(task_dir)
        for step in handoff_state.get("completed_step_keys", []):
            if step in flags:
                flags[step] = True

        reset_state = self.get_workflow_reset_state()
        reset_step = ""
        reset_applied_at: datetime | None = None
        if reset_state:
            reset_step = reset_state.get("step", "")
            reset_applied_at = self.parse_history_timestamp(reset_state.get("applied_at", ""))
            step_order = self.workflow_step_order()
            if reset_step in step_order:
                reset_index = step_order.index(reset_step)
                for step in step_order[:reset_index]:
                    flags[step] = True

        for entry in matching_entries:
            if reset_applied_at:
                entry_time = self.parse_history_timestamp(entry.timestamp)
                if entry_time and entry_time < reset_applied_at:
                    continue
            if entry.status_code != 0:
                continue

            if entry.task_name == "技能开发" and task_dir:
                flags["develop"] = True
            elif entry.task_name == "本地预审":
                flags["audit"] = True
            elif entry.task_name == "本地编译":
                flags["compile"] = True
            elif entry.task_name == "技能测试":
                flags["test"] = True
            elif entry.task_name == "预览回写":
                flags["preview"] = True
            elif entry.task_name == "写入 Excel 副本":
                flags["copy"] = True
            elif entry.task_name == "写回正式 Excel":
                flags["real"] = True
        if flags["develop"] and matching_entries:
            flags["audit"] = flags["audit"] or any(
                entry.task_name == "本地预审" and entry.status_code == 0 for entry in matching_entries
            )
        self.apply_artifact_readiness_to_flags(flags, task_dir, payload)
        return flags

    def apply_artifact_readiness_to_flags(self, flags: dict[str, bool], task_dir: str, payload: str) -> None:
        task_path = Path(task_dir) if task_dir else None
        payload_path = Path(payload) if payload else None

        has_task_dir = bool(task_path and task_path.exists() and task_path.is_dir())
        has_payload = bool(payload_path and payload_path.exists() and payload_path.is_file())
        has_develop_artifacts = bool(
            has_task_dir
            and has_payload
            and (
                (task_path / "docs" / "IMPLEMENTATION.md").is_file()
                or (task_path / "IMPLEMENTATION.md").is_file()
                or any(task_path.glob("action_*.lua"))
                or any(task_path.glob("buff_*.lua"))
            )
        )
        has_compiled_artifacts = bool(
            task_path
            and (
                (task_path / "config" / "temp_skill_config.lua").is_file()
                or (task_path / "temp_skill_config.lua").is_file()
            )
            and (
                (task_path / "tests" / "test_skill_temp.lua").is_file()
                or (task_path / "test_skill_temp.lua").is_file()
            )
        )
        has_test_artifacts = bool(
            task_path
            and (
                any(task_path.glob("test_result*.json"))
                or any(task_path.glob("test_result*.log"))
                or any(task_path.glob("local_test*.json"))
                or any(task_path.glob("local_test*.log"))
            )
        )
        has_preview_artifacts = bool(
            task_path
            and (
                any(task_path.glob("excel_preview*.json"))
                or any(task_path.glob("excel_preview*.log"))
                or any(task_path.glob("writeback_preview*.json"))
                or any(task_path.glob("writeback_preview*.log"))
            )
        )
        has_copy_outputs = self.has_excel_copy_outputs()

        if has_develop_artifacts:
            flags["develop"] = True
        if has_compiled_artifacts and flags["develop"]:
            flags["compile"] = True
        if has_test_artifacts and flags["develop"] and has_compiled_artifacts:
            flags["test"] = True
        if has_preview_artifacts and flags["test"]:
            flags["preview"] = True

        if flags["develop"] and not (has_task_dir and has_payload):
            flags["develop"] = False
        if flags["audit"] and not flags["develop"]:
            flags["audit"] = False
        if flags["compile"] and not (flags["develop"] and has_compiled_artifacts):
            flags["compile"] = False
        if flags["test"] and not (flags["develop"] and has_compiled_artifacts):
            flags["test"] = False
        if flags["preview"] and not flags["test"]:
            flags["preview"] = False
        if flags["copy"] and not (flags["preview"] and has_copy_outputs):
            flags["copy"] = False
        if flags["real"] and not (flags["preview"] and flags["copy"]):
            flags["real"] = False

    def has_excel_copy_outputs(self) -> bool:
        copy_dir_value = self.copy_dir_var.get().strip()
        if copy_dir_value:
            copy_dir = Path(copy_dir_value)
        else:
            task_dir_value = self.latest_task_dir_var.get().strip()
            copy_dir = Path(task_dir_value) / "excel_test_copy" if task_dir_value else Path()
        if not copy_dir.exists() or not copy_dir.is_dir():
            return False

        workbook_values = [self.skill_excel_var.get().strip(), self.war_excel_var.get().strip()]
        workbook_names = [Path(value).name for value in workbook_values if value and Path(value).name]
        xlsx_outputs = [
            path
            for path in copy_dir.glob("*.xlsx")
            if path.is_file() and not path.name.startswith("~$")
        ]
        if not workbook_names:
            return bool(xlsx_outputs)

        for name in workbook_names:
            if not any(path.is_file() for path in copy_dir.glob(name)):
                stem = Path(name).stem
                suffix = Path(name).suffix
                if any(path.is_file() for path in copy_dir.glob(f"{stem}_*{suffix}")):
                    return True
            else:
                return True
        return bool(xlsx_outputs)

    def build_workflow_state(self) -> dict[str, object]:
        task_dir = self.normalize_path(self.latest_task_dir_var.get())
        payload = self.normalize_path(self.payload_var.get())
        requirement_changed = self.has_requirement_changed()
        has_workspace = bool(self.workspace_var.get().strip() and self.battle_root_var.get().strip())
        task_dir_in_workspace = bool(task_dir and self.path_belongs_to_current_temp_workspace(task_dir))
        payload_in_workspace = bool(payload and self.path_belongs_to_current_temp_workspace(payload))
        has_task_dir = bool(task_dir and task_dir_in_workspace and Path(task_dir).exists())
        has_payload = bool(payload and payload_in_workspace and Path(payload).exists())
        busy = self.is_task_running()
        flags = self.get_workflow_progress_flags()
        resumable_develop = self.find_resumable_develop_task(self.prompt_text.get("1.0", "end").strip())
        if resumable_develop and not flags["develop"]:
            flags["develop"] = False
            flags["audit"] = False
            flags["compile"] = False
            flags["test"] = False
            flags["preview"] = False
            flags["copy"] = False
            flags["real"] = False
        selection_error = "" if requirement_changed else self.validate_current_workspace_selection()

        can_develop = has_workspace and not busy
        can_audit = has_workspace and has_task_dir and has_payload and flags["develop"] and not busy and not selection_error
        can_compile = has_workspace and has_payload and flags["develop"] and not busy and not selection_error
        can_test = has_workspace and has_task_dir and has_payload and flags["develop"] and not busy and not selection_error
        can_preview = has_workspace and has_payload and flags["test"] and not busy and not selection_error
        can_copy = has_workspace and has_payload and flags["preview"] and not busy and not selection_error
        can_real = has_workspace and has_payload and flags["preview"] and flags["copy"] and not busy and not selection_error

        if busy:
            recommended = ""
            next_message = "下一步：当前任务执行中，请等待完成或手动停止。"
        elif not has_workspace:
            recommended = ""
            next_message = "下一步：先定位工作目录和 battle_root。"
        elif selection_error:
            recommended = ""
            next_message = selection_error
        elif not flags["develop"]:
            recommended = "develop"
            if requirement_changed:
                next_message = "下一步：检测到技能描述已变更，请按新需求执行“开发技能”。"
            else:
                next_message = "下一步：执行“开发技能（Codex）”。"
        elif not has_task_dir or not has_payload:
            recommended = ""
            next_message = "下一步：刷新并确认本次开发产物目录与 payload。"
        elif not flags["audit"]:
            recommended = "audit"
            next_message = "下一步：先执行“本地预审”，确认 payload、脚本引用和产物结构都完整。"
        elif not flags["compile"]:
            recommended = "compile"
            next_message = "下一步：执行“本地编译”，先产出 temp_skill_config.lua 和 smoke test。"
        elif not flags["test"]:
            recommended = "test"
            next_message = "下一步：执行“技能测试（本地）”，确认技能链路可跑通。"
        elif not flags["preview"]:
            recommended = "preview"
            next_message = "下一步：先做“仅预览回写”，确认 Excel 写回内容。"
        elif not flags["copy"]:
            recommended = "copy"
            next_message = "下一步：写入 Excel 副本，先在副本里检查落表结果。"
        elif not flags["real"]:
            recommended = "real"
            if self.serial_include_real_var.get():
                next_message = "下一步：确认副本无误后，再执行“写回正式 Excel”。"
            else:
                next_message = "下一步：当前安全模式不会把正式写回纳入串行流程；请人工确认后手动执行“写回正式 Excel”，或先勾选高风险选项。"
        else:
            recommended = "develop"
            next_message = "下一步：当前链路已完成；如果要开发新技能，可以重新执行技能开发。"

        return {
            "flags": flags,
            "can_develop": can_develop,
            "can_audit": can_audit,
            "can_compile": can_compile,
            "can_test": can_test,
            "can_preview": can_preview,
            "can_copy": can_copy,
            "can_real": can_real,
            "busy": busy,
            "next_message": next_message,
            "recommended": recommended,
            "reset_state": self.get_workflow_reset_state(),
            "requirement_changed": requirement_changed,
        }

    def step_to_task_name(self, step_key: str) -> str:
        mapping = {
            "develop": "技能开发",
            "audit": "本地预审",
            "compile": "本地编译",
            "test": "技能测试",
            "preview": "预览回写",
            "copy": "写入 Excel 副本",
            "real": "写回正式 Excel",
        }
        return mapping.get(step_key, step_key)

    def task_name_to_step(self, task_name: str) -> str:
        mapping = {
            "技能开发": "develop",
            "续接修复": "develop",
            "本地预审": "audit",
            "本地编译": "compile",
            "技能测试": "test",
            "预览回写": "preview",
            "写入 Excel 副本": "copy",
            "写回正式 Excel": "real",
        }
        return mapping.get(task_name, "")

    def build_serial_steps(self, start_step: str) -> list[str]:
        ordered_steps = ["develop", "audit", "compile", "test", "preview", "copy"]
        if self.serial_include_real_var.get():
            ordered_steps.append("real")
        if start_step not in ordered_steps:
            return []
        return ordered_steps[ordered_steps.index(start_step) :]

    def stop_serial_workflow(self, reason: str = "") -> None:
        self.serial_workflow_active = False
        self.serial_current_step = ""
        self.serial_pending_steps = []
        if reason:
            self.append_log(f"[serial] {reason}")

    def run_serial_workflow(self) -> None:
        state = self.build_workflow_state()
        if state["busy"]:
            messagebox.showwarning("提示", "当前已有任务在执行，不能启动串行流程。")
            return
        if not self.validate_workspace():
            return

        start_step = self.recommended_action_key or str(state["recommended"])
        steps = self.build_serial_steps(start_step)
        if not steps:
            messagebox.showwarning("提示", str(state["next_message"]))
            return

        self.serial_workflow_active = True
        self.serial_current_step = ""
        self.serial_pending_steps = steps
        self.append_log("[serial] 启动串行流程：" + " -> ".join(self.step_to_task_name(step) for step in steps))
        self.next_action_var.set("下一步：串行流程已启动，系统会自动推进到下一个关键节点。")
        self.update_action_buttons()
        self.root.after(100, self.run_next_serial_step)

    def run_next_serial_step(self) -> None:
        if not self.serial_workflow_active:
            return
        if self.is_task_running():
            return
        if not self.serial_pending_steps:
            payload_path = self.payload_var.get().strip()
            task_dir = self.latest_task_dir_var.get().strip()
            self.stop_serial_workflow("串行流程已完成。")
            self.update_action_buttons()
            detail = "串行流程已完成。"
            if task_dir:
                detail += f"\n\n最新任务目录:\n{task_dir}"
            if payload_path and Path(payload_path).exists():
                detail += f"\n\n当前 payload:\n{payload_path}"
            messagebox.showinfo("完成", detail)
            return

        step = self.serial_pending_steps[0]
        state = self.build_workflow_state()
        can_map = {
            "develop": bool(state["can_develop"]),
            "audit": bool(state["can_audit"]),
            "compile": bool(state["can_compile"]),
            "test": bool(state["can_test"]),
            "preview": bool(state["can_preview"]),
            "copy": bool(state["can_copy"]),
            "real": bool(state["can_real"]),
        }
        if state["flags"].get(step):
            self.serial_pending_steps.pop(0)
            self.root.after(100, self.run_next_serial_step)
            return
        if not can_map.get(step):
            self.stop_serial_workflow(f"串行流程停止：步骤“{self.step_to_task_name(step)}”当前不可执行。")
            self.update_action_buttons()
            messagebox.showwarning("提示", str(state["next_message"]))
            return

        self.serial_current_step = step
        self.append_log(f"[serial] 自动执行步骤：{self.step_to_task_name(step)}")
        if step == "develop":
            self.run_develop()
        elif step == "audit":
            self.run_local_audit()
        elif step == "compile":
            self.run_local_compile()
        elif step == "test":
            self.run_test()
        elif step == "preview":
            self.write_excel_dry_run()
        elif step == "copy":
            self.write_excel_copy()
        elif step == "real":
            self.write_excel_real()

    def handle_serial_task_result(self, task_name: str, code: int) -> bool:
        if not self.serial_workflow_active:
            return False

        step = self.task_name_to_step(task_name)
        if not step:
            self.stop_serial_workflow("串行流程停止：无法识别当前步骤。")
            self.update_action_buttons()
            return True

        if self.serial_pending_steps and self.serial_pending_steps[0] == step:
            self.serial_pending_steps.pop(0)

        if code != 0:
            detail = f"串行流程已终止：{task_name} 执行失败。"
            if self.last_task_error_message:
                detail += f"\n\n错误详情:\n{self.last_task_error_message}"
            self.stop_serial_workflow(f"串行流程终止：步骤“{task_name}”执行失败。")
            self.update_action_buttons()
            detail += f"\n\n完整日志:\n{self.full_log_path}"
            self.show_log_tab()
            messagebox.showwarning("提示", detail)
            return True

        if step == "copy" and "real" in self.serial_pending_steps and self.serial_include_real_var.get():
            go_on = messagebox.askyesno(
                "继续确认",
                "Excel 副本写入已完成。是否继续执行“写回正式 Excel”？",
            )
            if not go_on:
                self.stop_serial_workflow("串行流程暂停：用户在副本检查后选择不继续写回正式 Excel。")
                self.update_action_buttons()
                return True

        if not self.serial_pending_steps:
            payload_path = self.payload_var.get().strip()
            task_dir = self.latest_task_dir_var.get().strip()
            self.stop_serial_workflow("串行流程已完成。")
            self.update_action_buttons()
            detail = "串行流程已完成。"
            if task_dir:
                detail += f"\n\n最新任务目录:\n{task_dir}"
            if payload_path and Path(payload_path).exists():
                detail += f"\n\n当前 payload:\n{payload_path}"
            messagebox.showinfo("完成", detail)
            return True

        self.update_action_buttons()
        self.root.after(200, self.run_next_serial_step)
        return True

    def step_status_text(self, step_key: str, can_run: bool, flags: dict[str, bool]) -> str:
        if self.task_name_to_step(self.current_task_name) == step_key and self.is_task_running():
            return "执行中"
        if flags.get(step_key):
            return "已完成"
        if can_run:
            return "可执行"
        return "等待前序"

    def update_action_buttons(self) -> None:
        if not hasattr(self, "develop_button"):
            return

        state = self.build_workflow_state()
        flags = state["flags"]
        current_step = ""
        if state["busy"]:
            current_step = self.task_name_to_step(self.current_task_name)
        else:
            current_step = str(state["recommended"])

        self.develop_button.configure(
            state="normal" if (not state["busy"] and current_step == "develop" and state["can_develop"]) else "disabled"
        )
        self.audit_button.configure(
            state="normal" if (not state["busy"] and current_step == "audit" and state["can_audit"]) else "disabled"
        )
        self.compile_button.configure(
            state="normal" if (not state["busy"] and current_step == "compile" and state["can_compile"]) else "disabled"
        )
        self.test_button.configure(
            state="normal" if (not state["busy"] and current_step == "test" and state["can_test"]) else "disabled"
        )
        self.preview_button.configure(
            state="normal" if (not state["busy"] and current_step == "preview" and state["can_preview"]) else "disabled"
        )
        self.copy_button.configure(
            state="normal" if (not state["busy"] and current_step == "copy" and state["can_copy"]) else "disabled"
        )
        self.real_button.configure(
            state="normal" if (not state["busy"] and current_step == "real" and state["can_real"]) else "disabled"
        )
        self.quick_real_button.configure(state="normal" if (not state["busy"] and state["can_real"]) else "disabled")
        self.stop_button.configure(state="normal" if state["busy"] else "disabled")
        self.serial_button.configure(
            state="normal" if (not state["busy"] and bool(state["recommended"])) else "disabled"
        )
        self.reset_button.configure(state="normal" if not state["busy"] else "disabled")
        self.step_overview_button.configure(state="disabled" if state["busy"] else "normal")
        if hasattr(self, "local_audit_button"):
            audit_enabled = bool(self.workspace_var.get().strip() and self.battle_root_var.get().strip()) and not state["busy"]
            self.local_audit_button.configure(state="normal" if audit_enabled else "disabled")
        if hasattr(self, "local_compile_button"):
            compile_enabled = (
                bool(self.workspace_var.get().strip() and self.battle_root_var.get().strip())
                and bool(self.payload_var.get().strip())
                and not state["busy"]
            )
            self.local_compile_button.configure(state="normal" if compile_enabled else "disabled")

        self.recommended_action_key = str(state["recommended"])
        reset_state = state.get("reset_state")
        if isinstance(reset_state, dict) and reset_state.get("step"):
            self.workflow_reset_var.set(self.step_to_task_name(str(reset_state["step"])))
        else:
            self.workflow_reset_var.set("按历史自动判断")
        if self.serial_workflow_active:
            if self.serial_pending_steps:
                pending = " -> ".join(self.step_to_task_name(step) for step in self.serial_pending_steps)
                self.next_action_var.set(f"下一步：串行流程进行中，待执行 {pending}")
            else:
                self.next_action_var.set("下一步：串行流程收尾中。")
        else:
            self.next_action_var.set(str(state["next_message"]))
        self.next_step_button.configure(
            state="normal" if self.recommended_action_key and not state["busy"] else "disabled"
        )

        step_label_map = {
            "develop": "1. 开发技能（Codex）",
            "audit": "2. 本地预审",
            "compile": "3. 本地编译",
            "test": "4. 技能测试（本地）",
            "preview": "5. 仅预览回写",
            "copy": "6. 写入 Excel 副本",
            "real": "7. 写回正式 Excel",
        }
        if state["busy"]:
            current_label = step_label_map.get(current_step, "当前任务")
            self.current_step_title_var.set(f"当前步骤：{current_label}（执行中）")
            self.current_step_desc_var.set("当前步骤正在执行。请等待完成，或手动停止当前任务。")
            self.current_step_action_var.set("执行中")
            self.current_step_button.configure(state="disabled", textvariable=self.current_step_action_var)
        elif self.recommended_action_key:
            current_label = step_label_map.get(self.recommended_action_key, self.recommended_action_key)
            self.current_step_title_var.set(f"当前步骤：{current_label}")
            self.current_step_desc_var.set(str(state["next_message"]))
            self.current_step_action_var.set(f"执行：{current_label}")
            self.current_step_button.configure(
                state="normal",
                textvariable=self.current_step_action_var,
            )
        else:
            self.current_step_title_var.set("当前步骤：等待人工处理")
            self.current_step_desc_var.set(str(state["next_message"]))
            self.current_step_action_var.set("当前无自动步骤")
            self.current_step_button.configure(state="disabled", textvariable=self.current_step_action_var)

        summary = " -> ".join(
            [
                f"开发[{self.step_status_text('develop', bool(state['can_develop']), flags)}]",
                f"预审[{self.step_status_text('audit', bool(state['can_audit']), flags)}]",
                f"编译[{self.step_status_text('compile', bool(state['can_compile']), flags)}]",
                f"测试[{self.step_status_text('test', bool(state['can_test']), flags)}]",
                f"预览[{self.step_status_text('preview', bool(state['can_preview']), flags)}]",
                f"副本[{self.step_status_text('copy', bool(state['can_copy']), flags)}]",
                f"正式[{self.step_status_text('real', bool(state['can_real']), flags)}]",
            ]
        )
        self.workflow_summary_var.set(f"流程状态：{summary}")

    def run_recommended_next_step(self) -> None:
        action = self.recommended_action_key
        if action == "develop":
            self.run_develop()
        elif action == "audit":
            self.run_local_audit()
        elif action == "compile":
            self.run_local_compile()
        elif action == "test":
            self.run_test()
        elif action == "preview":
            self.write_excel_dry_run()
        elif action == "copy":
            self.write_excel_copy()
        elif action == "real":
            self.write_excel_real()

    def get_selected_payload(self, listbox: tk.Listbox | None = None) -> Path | None:
        source = listbox or self.payload_listbox
        selection = source.curselection()
        if not selection:
            if self.payload_var.get().strip():
                return Path(self.payload_var.get().strip())
            return None
        index = selection[0]
        if index >= len(self.recent_payloads):
            return None
        return self.recent_payloads[index]

    def get_selected_task_dir(self, listbox: tk.Listbox | None = None) -> Path | None:
        source = listbox or self.task_dir_listbox
        selection = source.curselection()
        if not selection:
            if self.latest_task_dir_var.get().strip():
                return Path(self.latest_task_dir_var.get().strip())
            return None
        index = selection[0]
        if index >= len(self.recent_task_dirs):
            return None
        return self.recent_task_dirs[index]

    def on_recent_payload_select(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        if self.syncing_recent_lists:
            return
        source = _event.widget if _event and isinstance(_event.widget, tk.Listbox) else None
        selected = self.get_selected_payload(source)
        if selected:
            self.sync_payload_selection(str(selected))

    def on_recent_task_dir_select(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        if self.syncing_recent_lists:
            return
        source = _event.widget if _event and isinstance(_event.widget, tk.Listbox) else None
        selected = self.get_selected_task_dir(source)
        if selected:
            self.sync_task_dir_selection(str(selected))

    def use_selected_payload(self, listbox: tk.Listbox | None = None) -> None:
        selected = self.get_selected_payload(listbox)
        if not selected:
            messagebox.showwarning("提示", "当前没有可用的 payload 记录")
            return
        self.sync_payload_selection(str(selected))
        self.status_var.set("已选择 payload")

    def use_selected_task_dir(self, listbox: tk.Listbox | None = None) -> None:
        selected = self.get_selected_task_dir(listbox)
        if not selected:
            messagebox.showwarning("提示", "当前没有可用的任务目录")
            return
        self.sync_task_dir_selection(str(selected))
        self.status_var.set("已选择任务目录")

    def auto_discover_payload(self) -> None:
        payload_candidates = self.workspace_manager.find_payload_candidates(self.workspace_var.get())
        if not payload_candidates:
            messagebox.showwarning("提示", "没有在 temp_skill_workspace 下发现 payload 文件")
            return
        self.sync_payload_selection(str(payload_candidates[0]))
        self.refresh_temp_workspace_views()
        self.status_var.set("已自动定位最新 payload")

    def open_selected_payload(self) -> None:
        path = self.get_selected_payload()
        if not path:
            messagebox.showwarning("提示", "当前没有可打开的 payload 文件")
            return
        if not path.exists():
            messagebox.showwarning("提示", f"payload 文件不存在:\n{path}")
            return
        self.open_file_with_fallback(path)

    def open_file_with_fallback(self, path: Path) -> None:
        try:
            os.startfile(str(path))
            return
        except Exception as start_error:  # noqa: BLE001
            if path.suffix.lower() in {".json", ".log", ".txt", ".md", ".lua", ".csv"}:
                try:
                    subprocess.Popen(["notepad.exe", str(path)], **self.hidden_subprocess_kwargs())
                    return
                except Exception as fallback_error:  # noqa: BLE001
                    messagebox.showerror("错误", f"无法打开文件:\n{path}\n\n{fallback_error}")
                    return
            messagebox.showerror("错误", f"无法打开文件:\n{path}\n\n{start_error}")

    def hidden_subprocess_kwargs(self) -> dict:
        if os.name != "nt":
            return {}
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {
            "startupinfo": startupinfo,
            "creationflags": subprocess.CREATE_NO_WINDOW,
        }

    def open_selected_task_dir(self, listbox: tk.Listbox | None = None) -> None:
        path = self.get_selected_task_dir(listbox)
        if not path:
            messagebox.showwarning("提示", "当前没有可打开的任务目录")
            return
        if not path.exists():
            messagebox.showwarning("提示", "任务目录不存在")
            return
        try:
            os.startfile(str(path))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", str(exc))

    def open_latest_task_dir(self) -> None:
        self.open_selected_task_dir()

    def get_selected_artifact(self) -> Path | None:
        selection = self.artifact_listbox.curselection()
        if not selection:
            if self.current_task_artifacts:
                return self.current_task_artifacts[0]
            return None
        index = selection[0]
        if index >= len(self.current_task_artifacts):
            return None
        return self.current_task_artifacts[index]

    def on_artifact_select(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        selected = self.get_selected_artifact()
        if selected:
            self.artifact_summary_var.set(f"当前选中: {selected.name}")

    def open_selected_artifact(self) -> None:
        path = self.get_selected_artifact()
        if not path:
            messagebox.showwarning("提示", "当前没有可打开的产物文件")
            return
        if not path.exists():
            messagebox.showwarning("提示", "产物文件不存在")
            return
        self.open_file_with_fallback(path)

    def open_selected_artifact_parent(self) -> None:
        path = self.get_selected_artifact()
        if not path:
            messagebox.showwarning("提示", "当前没有可打开目录的产物文件")
            return
        parent = path.parent
        if not parent.exists():
            messagebox.showwarning("提示", "产物所在目录不存在")
            return
        try:
            os.startfile(str(parent))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", str(exc))

    def use_selected_artifact_as_payload(self) -> None:
        path = self.get_selected_artifact()
        if not path:
            messagebox.showwarning("提示", "当前没有可用的产物文件")
            return
        if path.suffix.lower() != ".json":
            messagebox.showwarning("提示", "只有 JSON 文件才能作为 payload 使用")
            return
        self.payload_var.set(str(path))
        self.status_var.set("已将选中文件设为 payload")
        self.update_action_buttons()

    def refresh_history_view(self) -> None:
        self.history_entries = self.history_service.load()
        self.refresh_history_filter_options()
        self.apply_history_filters()
        self.update_action_buttons()

    def refresh_history_filter_options(self) -> None:
        task_values = ["全部任务"] + sorted({entry.task_name for entry in self.history_entries if entry.task_name})
        self.history_task_filter_box.configure(values=task_values)
        if self.history_task_filter_var.get() not in task_values:
            self.history_task_filter_var.set("全部任务")
        if self.history_status_filter_var.get() not in {"全部结果", "成功", "失败"}:
            self.history_status_filter_var.set("全部结果")
        if self.history_view_mode_var.get() not in {"明细记录", "按技能聚合"}:
            self.history_view_mode_var.set("按技能聚合")

    def apply_history_filters(self) -> None:
        selected_entry = self.get_selected_history_entry()
        selected_key = self.history_entry_identity(selected_entry) if selected_entry else ""
        active_key = self.history_entry_identity(self.active_repair_entry) if self.active_repair_entry else ""
        filtered_entries = self.filtered_history_entries()
        self.history_display_rows = self.build_history_display_rows(filtered_entries)
        self.history_listbox.delete(0, "end")
        for row in self.history_display_rows:
            self.history_listbox.insert("end", str(row["title"]))

        self.history_summary_var.set(
            f"共 {len(self.history_entries)} 条历史，当前显示 {len(self.history_display_rows)} 条"
        )
        if self.history_display_rows:
            selected_index = self.find_history_row_index(active_key or selected_key)
            if selected_index < 0:
                selected_index = 0
            self.history_listbox.selection_set(selected_index)
            self.show_history_row_detail(self.history_display_rows[selected_index])
        else:
            self.show_history_text("没有符合筛选条件的历史记录")

    def reset_history_filters(self) -> None:
        self.history_search_var.set("")
        self.history_task_filter_var.set("全部任务")
        self.history_status_filter_var.set("全部结果")
        self.history_view_mode_var.set("按技能聚合")
        self.apply_history_filters()

    def filtered_history_entries(self) -> list[TaskHistoryEntry]:
        keyword = self.history_search_var.get().strip().lower()
        task_filter = self.history_task_filter_var.get()
        status_filter = self.history_status_filter_var.get()

        entries = self.history_entries
        if task_filter != "全部任务":
            entries = [entry for entry in entries if entry.task_name == task_filter]
        if status_filter != "全部结果":
            entries = [entry for entry in entries if entry.status_text == status_filter]
        if keyword:
            entries = [entry for entry in entries if keyword in self.history_search_blob(entry)]
        return entries

    def history_search_blob(self, entry: TaskHistoryEntry) -> str:
        values = [
            entry.timestamp,
            entry.task_name,
            entry.status_text,
            entry.workspace_root,
            entry.battle_root,
            entry.template_name,
            entry.scene_label,
            entry.model_preset_key,
            entry.model_name,
            entry.codex_extra_args,
            entry.payload_path,
            entry.task_dir,
            entry.output_file,
            entry.skill_description,
            entry.protected_files,
            entry.additional_constraints,
            "\n".join(entry.artifacts),
        ]
        return "\n".join(values).lower()

    def build_history_display_rows(self, entries: list[TaskHistoryEntry]) -> list[dict[str, object]]:
        if self.history_view_mode_var.get() == "按技能聚合":
            return self.build_grouped_history_rows(entries)
        return [{"kind": "entry", "title": self.format_history_title(entry), "entry": entry} for entry in entries]

    def build_grouped_history_rows(self, entries: list[TaskHistoryEntry]) -> list[dict[str, object]]:
        groups: dict[str, list[TaskHistoryEntry]] = {}
        for entry in entries:
            groups.setdefault(self.history_session_key(entry), []).append(entry)

        rows: list[dict[str, object]] = []
        sorted_groups = sorted(groups.values(), key=lambda item: item[0].timestamp if item else "", reverse=True)
        for group_entries in sorted_groups:
            group_entries = sorted(group_entries, key=lambda entry: entry.timestamp, reverse=True)
            primary = self.best_repair_entry(group_entries)
            latest = group_entries[0]
            success_count = sum(1 for entry in group_entries if entry.status_code == 0)
            skill_title = self.extract_skill_title(primary.skill_description or latest.skill_description)
            task_name = Path(primary.task_dir).name if primary.task_dir else Path(primary.payload_path).parent.name if primary.payload_path else "未记录目录"
            title = (
                f"{skill_title} | {task_name} | {len(group_entries)} 条 | "
                f"成功 {success_count} | 最新 {latest.timestamp} {latest.task_name}"
            )
            rows.append({"kind": "group", "title": title, "entries": group_entries, "entry": primary})
        return rows

    def history_session_key(self, entry: TaskHistoryEntry) -> str:
        task_dir = self.normalize_path(entry.task_dir)
        if task_dir:
            return "task:" + task_dir
        payload_path = self.normalize_path(entry.payload_path)
        if payload_path:
            return "payload:" + payload_path
        if entry.session_id:
            return "session:" + entry.session_id
        seed = "\n".join([entry.workspace_root, entry.skill_description, entry.timestamp[:10]])
        return "desc:" + hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()

    def history_entry_identity(self, entry: TaskHistoryEntry | None) -> str:
        if not entry:
            return ""
        return self.history_session_key(entry)

    def find_history_row_index(self, target_key: str) -> int:
        if not target_key:
            return -1
        for index, row in enumerate(self.history_display_rows):
            entry = self.history_row_primary_entry(row)
            if entry and self.history_entry_identity(entry) == target_key:
                return index
        return -1

    def best_repair_entry(self, entries: list[TaskHistoryEntry]) -> TaskHistoryEntry:
        for entry in entries:
            if entry.session_id and entry.task_name in {"技能开发", "续接修复"}:
                return entry
        for entry in entries:
            if entry.session_id:
                return entry
        return entries[0]

    def history_entry_location(self, entry: TaskHistoryEntry) -> str:
        if entry.task_dir:
            return entry.task_dir
        if entry.payload_path:
            return str(Path(entry.payload_path).parent)
        return "无"

    def format_history_title(self, entry: TaskHistoryEntry) -> str:
        title = self.extract_skill_title(entry.skill_description)
        return f"{entry.timestamp} | {entry.task_name} | {entry.status_text} | {title}"

    def extract_skill_title(self, description: str) -> str:
        normalized = description.strip().replace("\r\n", "\n")
        for line in normalized.splitlines():
            line = line.strip()
            if line:
                return line[:48]
        return "未填写技能描述"

    def get_selected_history_entry(self) -> TaskHistoryEntry | None:
        selection = self.history_listbox.curselection()
        if not selection:
            if not self.history_display_rows:
                return None
            row = self.history_display_rows[0]
            return self.history_row_primary_entry(row)
        index = selection[0]
        if index >= len(self.history_display_rows):
            return None
        return self.history_row_primary_entry(self.history_display_rows[index])

    def get_selected_history_row(self) -> dict[str, object] | None:
        selection = self.history_listbox.curselection()
        if not selection:
            return self.history_display_rows[0] if self.history_display_rows else None
        index = selection[0]
        if index >= len(self.history_display_rows):
            return None
        return self.history_display_rows[index]

    def history_row_primary_entry(self, row: dict[str, object]) -> TaskHistoryEntry | None:
        if row.get("kind") == "entry":
            return row.get("entry") if isinstance(row.get("entry"), TaskHistoryEntry) else None
        entries = row.get("entries")
        if isinstance(entries, list) and entries:
            typed_entries = [entry for entry in entries if isinstance(entry, TaskHistoryEntry)]
            return self.best_repair_entry(typed_entries) if typed_entries else None
        return None

    def on_history_select(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        row = self.get_selected_history_row()
        if row:
            self.show_history_row_detail(row)
            entry = self.history_row_primary_entry(row)
            if entry:
                self.activate_repair_session(entry)

    def show_history_text(self, text: str) -> None:
        self.history_detail_text.configure(state="normal")
        self.history_detail_text.delete("1.0", "end")
        self.history_detail_text.insert("1.0", text)
        self.history_detail_text.configure(state="disabled")

    def show_repair_chat_text(self, text: str) -> None:
        if not hasattr(self, "repair_chat_text"):
            return
        self.repair_chat_text.configure(state="normal")
        self.repair_chat_text.delete("1.0", "end")
        self.repair_chat_text.insert("1.0", self.format_repair_chat_timeline(text))
        self.repair_chat_text.configure(state="disabled")

    def format_repair_chat_timeline(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return "这个技能会话还没有修复对话。"
        blocks = re.split(r"\n(?=## )", text)
        rendered: list[str] = []
        for block in blocks:
            lines = block.strip().splitlines()
            if not lines:
                continue
            heading = lines[0].removeprefix("## ").strip()
            body = "\n".join(lines[1:]).strip()
            rendered.append(f"【{heading}】")
            rendered.append(body or "(空)")
            rendered.append("")
        return "\n".join(rendered).rstrip()

    def show_history_detail(self, entry: TaskHistoryEntry) -> None:
        artifact_text = "\n".join(entry.artifacts) if entry.artifacts else "无"
        detail = (
            f"时间: {entry.timestamp}\n"
            f"任务: {entry.task_name}\n"
            f"结果: {entry.status_text} (code={entry.status_code})\n"
            f"工作目录: {entry.workspace_root}\n"
            f"battle_root: {entry.battle_root}\n"
            f"模板: {entry.template_name}\n"
            f"场景: {entry.scene_label}\n"
            f"模型预设: {entry.model_preset_key}\n"
            f"模型名: {entry.model_name}\n"
            f"额外参数: {entry.codex_extra_args or '无'}\n"
            f"Codex session: {entry.session_id or '无'}\n"
            f"Session 文件: {entry.session_file or '无'}\n"
            f"Payload: {entry.payload_path or '无'}\n"
            f"任务目录: {entry.task_dir or '无'}\n"
            f"归档目录: {entry.archive_dir or '无'}\n"
            f"归档状态: {'可用' if entry.archive_dir and Path(entry.archive_dir).exists() else '无'}\n"
            f"输出文件: {entry.output_file or '无'}\n"
            f"去重写回: {'是' if entry.dedupe_existing else '否'}\n\n"
            f"技能描述:\n{entry.skill_description or '无'}\n\n"
            f"保护文件:\n{entry.protected_files or '无'}\n\n"
            f"额外约束:\n{entry.additional_constraints or '无'}\n\n"
            f"产物列表:\n{artifact_text}\n\n"
            f"修复对话:\n{self.repair_chat_preview_for_entry(entry)}"
        )
        self.show_history_text(detail)

    def show_history_row_detail(self, row: dict[str, object]) -> None:
        if row.get("kind") == "entry":
            entry = self.history_row_primary_entry(row)
            if entry:
                self.show_history_detail(entry)
                self.show_repair_chat_for_entry(entry)
            return

        entries = row.get("entries")
        if not isinstance(entries, list):
            self.show_history_text("聚合记录为空")
            return

        typed_entries = [entry for entry in entries if isinstance(entry, TaskHistoryEntry)]
        if not typed_entries:
            self.show_history_text("聚合记录为空")
            return

        latest = typed_entries[0]
        primary = self.best_repair_entry(typed_entries)
        success_count = sum(1 for entry in typed_entries if entry.status_code == 0)
        lines = [
            f"技能标题: {self.extract_skill_title(primary.skill_description or latest.skill_description)}",
            f"会话目录: {self.history_entry_location(primary)}",
            f"修复会话: {primary.session_id or '未记录'}",
            f"记录数量: {len(typed_entries)}",
            f"成功数量: {success_count}",
            f"失败数量: {len(typed_entries) - success_count}",
            f"最近时间: {latest.timestamp}",
            f"最近任务: {latest.task_name}",
            f"最近 Payload: {latest.payload_path or '无'}",
            f"最近任务目录: {latest.task_dir or '无'}",
            f"最近归档目录: {latest.archive_dir or '无'}",
            "",
            "记录明细:",
        ]
        for entry in typed_entries:
            lines.append(
                f"- {entry.timestamp} | {entry.task_name} | {entry.status_text} | "
                f"{entry.model_name or entry.model_preset_key}"
            )
        lines.extend(
            [
                "",
                "技能描述:",
                primary.skill_description or latest.skill_description or "无",
                "",
                "修复对话:",
                self.repair_chat_preview_for_entry(primary),
            ]
        )
        self.show_history_text("\n".join(lines))
        self.show_repair_chat_for_entry(primary)

    def apply_selected_history(self) -> None:
        entry = self.get_selected_history_entry()
        if not entry:
            messagebox.showwarning("提示", "当前没有可回填的历史记录")
            return

        self.workspace_var.set(entry.workspace_root or self.workspace_var.get())
        if entry.template_name:
            self.template_var.set(template_label_from_key(entry.template_name))
        if entry.scene_label:
            self.scene_var.set(entry.scene_label)
        if entry.model_preset_key:
            self.model_preset_key_var.set(entry.model_preset_key)
            self.model_preset_label_var.set(self.get_preset_label(entry.model_preset_key))
        self.codex_model_var.set(entry.model_name)
        self.codex_extra_args_var.set(entry.codex_extra_args)
        self.payload_var.set(entry.payload_path)
        self.latest_task_dir_var.set(entry.task_dir)
        self.dedupe_var.set(entry.dedupe_existing)

        self.suppress_requirement_change = True
        try:
            self.description_text.delete("1.0", "end")
            self.description_text.insert("1.0", entry.skill_description)
            self.protected_text.delete("1.0", "end")
            self.protected_text.insert("1.0", entry.protected_files)
            self.constraints_text.delete("1.0", "end")
            self.constraints_text.insert("1.0", entry.additional_constraints)
        finally:
            self.suppress_requirement_change = False

        self.refresh_battle_root()
        self.refresh_model_note()
        self.refresh_command_preview()
        self.refresh_prompt()
        self.accept_current_requirement_context()
        self.status_var.set("已回填历史记录")
        self.update_action_buttons()

    def open_selected_history_task_dir(self) -> None:
        entry = self.get_selected_history_entry()
        if not entry or not entry.task_dir:
            messagebox.showwarning("提示", "历史记录里没有任务目录")
            return
        path = Path(entry.task_dir)
        if not path.exists():
            messagebox.showwarning("提示", "历史任务目录不存在")
            return
        try:
            os.startfile(str(path))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", str(exc))

    def open_selected_history_payload(self) -> None:
        entry = self.get_selected_history_entry()
        if not entry or not entry.payload_path:
            messagebox.showwarning("提示", "历史记录里没有 payload")
            return
        path = Path(entry.payload_path)
        if not path.exists():
            messagebox.showwarning("提示", "历史 payload 不存在")
            return
        try:
            os.startfile(str(path))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", str(exc))

    def open_selected_history_archive_dir(self) -> None:
        entry = self.get_selected_history_entry()
        if not entry or not entry.archive_dir:
            messagebox.showwarning("提示", "历史记录里没有归档目录")
            return
        path = Path(entry.archive_dir)
        if not path.exists():
            messagebox.showwarning("提示", "历史归档目录不存在")
            return
        try:
            os.startfile(str(path))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", str(exc))

    def repair_chat_path_for_entry(self, entry: TaskHistoryEntry) -> Path | None:
        if entry.task_dir and Path(entry.task_dir).exists():
            return Path(entry.task_dir) / "repair" / "_repair_chat.md"
        if entry.payload_path and Path(entry.payload_path).exists():
            payload_parent = Path(entry.payload_path).parent
            task_root = payload_parent.parent if payload_parent.name == "config" else payload_parent
            return task_root / "repair" / "_repair_chat.md"
        if entry.archive_dir and Path(entry.archive_dir).exists():
            return Path(entry.archive_dir) / "repair" / "_repair_chat.md"
        return None

    def show_repair_chat_for_entry(self, entry: TaskHistoryEntry) -> None:
        chat_path = self.repair_chat_path_for_entry(entry)
        if not chat_path or not chat_path.exists():
            self.show_repair_chat_text("")
            return
        try:
            self.show_repair_chat_text(chat_path.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            self.show_repair_chat_text(f"读取会话记录失败: {exc}")

    def repair_chat_preview_for_entry(self, entry: TaskHistoryEntry, max_chars: int = 4000) -> str:
        chat_path = self.repair_chat_path_for_entry(entry)
        if not chat_path or not chat_path.exists():
            return "无"
        try:
            text = chat_path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception as exc:  # noqa: BLE001
            return f"读取失败: {exc}"
        if not text:
            return "无"
        if len(text) <= max_chars:
            return text
        return "[前文省略，仅显示最近对话]\n" + text[-max_chars:]

    def append_repair_chat(self, entry: TaskHistoryEntry, role: str, body: str, attachments: list[Path] | None = None) -> Path | None:
        chat_path = self.repair_chat_path_for_entry(entry)
        if not chat_path:
            return None
        chat_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "",
            f"## {role} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            body.strip() or "(空)",
            "",
        ]
        if attachments:
            lines.append("附件：")
            for path in attachments:
                lines.append(f"- {path}")
            lines.append("")
        with chat_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        if self.active_repair_entry is entry:
            self.show_repair_chat_for_entry(entry)
        return chat_path

    def set_selected_history_as_repair_session(self) -> None:
        entry = self.get_selected_history_entry()
        if not entry:
            messagebox.showwarning("提示", "请先在左侧选择一条历史记录。")
            return
        self.activate_repair_session(entry)

    def set_current_target_as_repair_session(self) -> None:
        task_dir = self.latest_task_dir_var.get().strip()
        payload = self.payload_var.get().strip()
        if not task_dir and not payload:
            messagebox.showwarning("提示", "当前还没有任务目录或 payload。")
            return
        if not self.history_entries:
            entry = self.build_repair_entry_from_current_task()
            if entry:
                self.activate_repair_session(entry)
                if hasattr(self, "notebook"):
                    self.notebook.select(1)
                messagebox.showinfo("修复会话", "已基于当前任务目录创建修复会话，可以继续发送修复消息。")
                return
        for entry in self.history_entries:
            if self.history_matches_current_target(entry, self.normalize_path(task_dir), self.normalize_path(payload)):
                self.activate_repair_session(entry)
                if hasattr(self, "notebook"):
                    self.notebook.select(1)
                messagebox.showinfo("修复会话", "已切换到“技能会话”，可以连续粘贴日志/截图并发送。")
                return
        entry = self.build_repair_entry_from_current_task()
        if entry:
            self.activate_repair_session(entry)
            if hasattr(self, "notebook"):
                self.notebook.select(1)
            messagebox.showinfo("修复会话", "没有匹配到本机历史，已改用当前任务目录创建修复会话。")
            return
        messagebox.showwarning("提示", "没有找到当前任务对应的历史记录，请先刷新历史或在技能会话里手动选择。")

    def build_repair_entry_from_current_task(self) -> TaskHistoryEntry | None:
        task_dir = self.latest_task_dir_var.get().strip()
        payload = self.payload_var.get().strip()
        if not task_dir and payload:
            task_dir = str(self.workspace_manager.task_dir_for_payload(payload))
        context = self.load_task_context(task_dir) if task_dir else {}
        if not context and not payload:
            return None
        if not payload and task_dir:
            discovered = self.workspace_manager.find_primary_payload_for_dir(task_dir)
            payload = str(discovered) if discovered else ""
        artifacts = [str(path) for path in self.workspace_manager.find_task_artifacts(task_dir, limit=40)] if task_dir else []
        return TaskHistoryEntry(
            timestamp=context.get("updated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            task_name="技能开发",
            status_code=0 if context.get("status") == "completed" else -1,
            status_text=context.get("status") or "local-task",
            workspace_root=self.workspace_var.get().strip(),
            battle_root=self.battle_root_var.get().strip(),
            template_name=self.current_template_key(),
            scene_label=self.scene_var.get().strip(),
            agent_backend=context.get("agent_backend") or self.agent_backend_var.get().strip() or "codex",
            model_preset_key=self.model_preset_key_var.get().strip(),
            model_name=context.get("model_name") or (self.claude_model_var.get().strip() if self.agent_backend_var.get() == "claude" else self.codex_model_var.get().strip()),
            codex_extra_args=self.claude_extra_args_var.get().strip() if self.agent_backend_var.get() == "claude" else self.codex_extra_args_var.get().strip(),
            payload_path=payload,
            task_dir=task_dir,
            output_file=str(self.default_output_file()),
            archive_dir="",
            skill_description=context.get("requirement") or self.get_text(self.description_text),
            protected_files=self.get_text(self.protected_text),
            additional_constraints=context.get("constraints") or self.get_text(self.constraints_text),
            dedupe_existing=self.dedupe_var.get(),
            session_id=context.get("session_id", ""),
            session_file="",
            artifacts=artifacts,
        )

    def activate_repair_session(self, entry: TaskHistoryEntry) -> None:
        entry = self.repair_entry_with_local_context(entry)
        self.active_repair_entry = entry
        self.repair_session_var.set(
            f"当前会话：{self.extract_skill_title(entry.skill_description)} | {entry.timestamp}"
        )
        if entry.workspace_root:
            self.workspace_var.set(entry.workspace_root)
        if entry.payload_path:
            payload_path = Path(entry.payload_path)
            if not payload_path.exists() and entry.task_dir:
                replacement = self.workspace_manager.find_primary_payload_for_dir(entry.task_dir)
                self.payload_var.set(str(replacement) if replacement else entry.payload_path)
            else:
                self.payload_var.set(entry.payload_path)
        if entry.task_dir:
            self.latest_task_dir_var.set(entry.task_dir)
            self.workspace_manager.ensure_task_layout(entry.task_dir)
        self.suppress_requirement_change = True
        try:
            if entry.skill_description:
                self.description_text.delete("1.0", "end")
                self.description_text.insert("1.0", entry.skill_description)
            if entry.additional_constraints:
                self.constraints_text.delete("1.0", "end")
                self.constraints_text.insert("1.0", entry.additional_constraints)
            self.refresh_prompt()
            self.accept_current_requirement_context()
        finally:
            self.suppress_requirement_change = False
        self.status_var.set("已选择修复会话")
        self.show_repair_chat_for_entry(entry)
        self.append_log(f"[repair] 已选择修复会话: {entry.task_dir or entry.payload_path or entry.timestamp}")

    def repair_entry_with_local_context(self, entry: TaskHistoryEntry) -> TaskHistoryEntry:
        task_dir = entry.task_dir.strip()
        payload = entry.payload_path.strip()
        if not task_dir and payload:
            task_dir = str(self.workspace_manager.task_dir_for_payload(payload))
        if not task_dir:
            current_task_dir = self.latest_task_dir_var.get().strip()
            if current_task_dir and Path(current_task_dir).exists():
                task_dir = current_task_dir
        if not payload and task_dir:
            discovered = self.workspace_manager.find_primary_payload_for_dir(task_dir)
            if discovered:
                payload = str(discovered)
        context = self.load_task_context(task_dir) if task_dir else {}
        return replace(
            entry,
            task_dir=task_dir,
            payload_path=payload,
            workspace_root=entry.workspace_root or self.workspace_var.get().strip(),
            battle_root=entry.battle_root or self.battle_root_var.get().strip(),
            agent_backend=entry.agent_backend or context.get("agent_backend") or self.agent_backend_var.get().strip() or "codex",
            model_name=entry.model_name or context.get("model_name") or (
                self.claude_model_var.get().strip()
                if self.agent_backend_var.get() == "claude"
                else self.codex_model_var.get().strip()
            ),
            skill_description=entry.skill_description or context.get("requirement") or self.get_text(self.description_text),
            additional_constraints=entry.additional_constraints or context.get("constraints") or self.get_text(self.constraints_text),
            session_id=entry.session_id or context.get("session_id", ""),
        )

    def add_repair_session_attachments(self) -> None:
        selected = filedialog.askopenfilenames(
            parent=self.root,
            title="选择日志或截图",
            filetypes=[
                ("日志和图片", "*.log *.txt *.md *.json *.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                ("图片", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                ("日志文本", "*.log *.txt *.md *.json *.lua *.csv"),
                ("所有文件", "*.*"),
            ],
        )
        for path in selected:
            if path and path not in self.repair_attachment_paths:
                self.repair_attachment_paths.append(path)
        self.refresh_repair_attachment_list()

    def paste_repair_clipboard(self, _event: tk.Event[tk.Misc] | None = None) -> str | None:
        image_path = self.save_clipboard_image_attachment()
        if image_path:
            self.repair_attachment_paths.append(str(image_path))
            self.refresh_repair_attachment_list()
            self.append_log(f"[repair] 已从剪贴板粘贴截图: {image_path}")
            return "break"

        file_paths = self.read_clipboard_file_attachments()
        if file_paths:
            added = 0
            for path in file_paths:
                if path not in self.repair_attachment_paths:
                    self.repair_attachment_paths.append(path)
                    added += 1
            self.refresh_repair_attachment_list()
            if added:
                self.append_log(f"[repair] 已从剪贴板加入 {added} 个文件附件")
            return "break"

        return None

    def save_clipboard_image_attachment(self) -> Path | None:
        try:
            from PIL import ImageGrab  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001
            return None

        try:
            clipboard_data = ImageGrab.grabclipboard()
        except Exception:  # noqa: BLE001
            return None

        if not hasattr(clipboard_data, "save"):
            return None

        out_dir = self.clipboard_attachment_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"clipboard_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        try:
            clipboard_data.save(out_path, "PNG")
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning("提示", f"剪贴板截图保存失败：{exc}")
            return None
        return out_path

    def read_clipboard_file_attachments(self) -> list[str]:
        try:
            from PIL import ImageGrab  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001
            return []

        try:
            clipboard_data = ImageGrab.grabclipboard()
        except Exception:  # noqa: BLE001
            return []

        if not isinstance(clipboard_data, list):
            return []
        paths: list[str] = []
        for item in clipboard_data:
            path = Path(str(item))
            if path.exists() and path.is_file():
                paths.append(str(path))
        return paths

    def clipboard_attachment_dir(self) -> Path:
        if self.active_repair_entry:
            chat_path = self.repair_chat_path_for_entry(self.active_repair_entry)
            if chat_path:
                return chat_path.parent / "clipboard"
        return self.data_dir / "repair_attachments" / "_clipboard"

    def clear_repair_session_attachments(self) -> None:
        self.repair_attachment_paths = []
        self.refresh_repair_attachment_list()

    def refresh_repair_attachment_list(self) -> None:
        if not hasattr(self, "repair_attachment_listbox"):
            return
        self.repair_attachment_listbox.delete(0, "end")
        for path in self.repair_attachment_paths:
            self.repair_attachment_listbox.insert("end", path)
        self.repair_attachment_status_var.set(f"附件：{len(self.repair_attachment_paths)} 个")

    def ask_history_fix_input(self, entry: TaskHistoryEntry) -> tuple[str, list[str]] | None:
        dialog = tk.Toplevel(self.root)
        dialog.title("续接修复")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("760x520")
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        dialog.rowconfigure(3, weight=1)

        ttk.Label(
            dialog,
            text=f"当前历史任务：{self.extract_skill_title(entry.skill_description)}",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))

        issue_text = tk.Text(dialog, height=10, wrap="word")
        issue_text.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        issue_text.insert(
            "1.0",
            "在这里粘贴问题说明、关键战报日志、复现方式；也可以用下方按钮添加完整日志或截图文件。\n",
        )

        attachment_frame = ttk.LabelFrame(dialog, text="日志 / 截图附件")
        attachment_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        attachment_frame.columnconfigure(0, weight=1)
        attachments: list[str] = []
        attachment_list = tk.Listbox(attachment_frame, height=6, exportselection=False)
        attachment_list.grid(row=0, column=0, rowspan=3, sticky="ew", padx=6, pady=6)

        def refresh_attachment_list() -> None:
            attachment_list.delete(0, "end")
            for path in attachments:
                attachment_list.insert("end", path)

        def add_attachments() -> None:
            selected = filedialog.askopenfilenames(
                parent=dialog,
                title="选择日志或截图",
                filetypes=[
                    ("日志和图片", "*.log *.txt *.md *.json *.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                    ("图片", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                    ("日志文本", "*.log *.txt *.md *.json *.lua *.csv"),
                    ("所有文件", "*.*"),
                ],
            )
            for path in selected:
                if path and path not in attachments:
                    attachments.append(path)
            refresh_attachment_list()

        def remove_attachment() -> None:
            selection = list(attachment_list.curselection())
            for index in reversed(selection):
                if 0 <= index < len(attachments):
                    del attachments[index]
            refresh_attachment_list()

        ttk.Button(attachment_frame, text="添加文件", command=add_attachments).grid(
            row=0, column=1, sticky="ew", padx=6, pady=(6, 3)
        )
        ttk.Button(attachment_frame, text="移除选中", command=remove_attachment).grid(
            row=1, column=1, sticky="ew", padx=6, pady=3
        )

        result: dict[str, object] = {"ok": False}

        def submit() -> None:
            result["ok"] = True
            result["issue"] = issue_text.get("1.0", "end").strip()
            result["attachments"] = list(attachments)
            dialog.destroy()

        def cancel() -> None:
            dialog.destroy()

        button_row = ttk.Frame(dialog)
        button_row.grid(row=4, column=0, sticky="e", padx=12, pady=12)
        ttk.Button(button_row, text="开始修复", command=submit).pack(side="left", padx=6)
        ttk.Button(button_row, text="取消", command=cancel).pack(side="left")
        dialog.protocol("WM_DELETE_WINDOW", cancel)

        self.root.wait_window(dialog)
        if not result.get("ok"):
            return None
        return str(result.get("issue", "") or ""), list(result.get("attachments", []) or [])

    def prepare_repair_attachments(self, entry: TaskHistoryEntry, attachment_paths: list[str]) -> list[Path]:
        if not attachment_paths:
            return []
        if entry.task_dir and Path(entry.task_dir).exists():
            root = Path(entry.task_dir) / "repair" / "attachments"
        elif entry.archive_dir and Path(entry.archive_dir).exists():
            root = Path(entry.archive_dir) / "repair" / "attachments"
        else:
            root = self.data_dir / "repair_attachments"
        out_dir = root / datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir.mkdir(parents=True, exist_ok=True)

        copied: list[Path] = []
        for raw_path in attachment_paths:
            src = Path(raw_path)
            if not src.exists() or not src.is_file():
                self.append_log(f"[repair] 附件不存在，已跳过: {src}")
                continue
            dst = out_dir / src.name
            counter = 1
            while dst.exists():
                dst = out_dir / f"{src.stem}_{counter}{src.suffix}"
                counter += 1
            try:
                shutil.copy2(src, dst)
                copied.append(dst)
            except Exception as exc:  # noqa: BLE001
                self.append_log(f"[repair] 附件复制失败: {src} :: {exc}")
        return copied

    def build_repair_attachment_section(self, attachments: list[Path]) -> str:
        if not attachments:
            return "无"

        lines = ["附件已复制到任务目录，优先结合这些文件定位问题："]
        for path in attachments:
            suffix = path.suffix.lower()
            kind = "截图/图片" if suffix in self.REPAIR_IMAGE_SUFFIXES else "日志/文本"
            lines.append(f"- [{kind}] {path}")

        for path in attachments:
            if path.suffix.lower() not in self.REPAIR_TEXT_SUFFIXES:
                continue
            excerpt = self.read_repair_text_excerpt(path)
            if not excerpt:
                continue
            lines.extend(
                [
                    "",
                    f"### 日志片段：{path.name}",
                    "```text",
                    excerpt,
                    "```",
                ]
            )
        return "\n".join(lines)

    def read_repair_text_excerpt(self, path: Path, max_chars: int = 30000) -> str:
        try:
            text = decode_process_output(path.read_bytes())
        except Exception:  # noqa: BLE001
            return ""
        text = text.strip()
        if len(text) <= max_chars:
            return text
        return "[前文省略，仅保留文件尾部]\n" + text[-max_chars:]

    def build_history_fix_prompt(
        self,
        entry: TaskHistoryEntry,
        issue_text: str,
        attachments: list[Path] | None = None,
    ) -> str:
        attachment_section = self.build_repair_attachment_section(attachments or [])
        local_context_root = entry.task_dir if entry.task_dir and Path(entry.task_dir).exists() else entry.archive_dir
        local_context = self.build_local_task_context_block(local_context_root, entry.payload_path)
        return (
            "Use $family-battle-skill-writer\n\n"
            "这是针对已完成技能开发任务的续接修复。不要从 0 重新扫描或重新设计整套技能，"
            "优先沿用原 session、原任务目录、已有 Lua、临时配置、payload、测试文件和知识索引。\n"
            "请根据用户提供的战报日志、截图说明或复现描述定位问题；先判断是否配置问题，"
            "如果不是配置问题，再检查对应 BUFF/ACTION 实现并做最小修复。\n\n"
            f"原任务目录: {entry.task_dir or '未记录'}\n"
            f"归档目录: {entry.archive_dir or '未记录'}\n"
            f"原 payload: {entry.payload_path or '未记录'}\n"
            f"原输出文件: {entry.output_file or '未记录'}\n"
            f"原执行后端: {entry.agent_backend or 'codex'}\n"
            f"原 session: {entry.session_id or '未记录'}\n\n"
            f"{local_context}\n\n"
            "用户反馈 / 日志 / 截图说明:\n"
            f"{issue_text.strip() or '用户未填写具体反馈，请先读取原任务产物和最近日志，找出明显异常后继续。'}\n\n"
            "附件 / 证据文件:\n"
            f"{attachment_section}\n\n"
            "如果附件里包含图片，请优先查看图片内容；如果当前模型/运行环境无法直接读取图片，"
            "请根据用户文字说明和附件文件名继续定位，并在结果里说明图片未能直接解析。\n\n"
            "过程输出要求:\n"
            "1. 开始后先输出“开始定位”，说明会检查哪些目录、配置、脚本或日志。\n"
            "2. 每完成一个关键阶段都要输出简短中文进度，例如“已定位到疑似配置问题/脚本问题/战报问题”。\n"
            "3. 如果读取了关键文件或命中关键函数，要说明文件路径和判断依据，但不要整段粘贴源码。\n"
            "4. 如果进行了修改，必须说明改了哪些文件、为什么改、对原技能流程有什么影响。\n"
            "5. 结束时必须给出“修复总结”，包含：问题原因、修改文件、关键改动、验证结果、仍需人工确认的风险。\n"
            "6. 不要只输出一句完成，也不要静默长时间分析；长任务至少阶段性汇报当前正在做什么。\n\n"
            "原始技能需求:\n"
            f"{entry.skill_description or '未记录'}\n\n"
            "原始额外约束:\n"
            f"{entry.additional_constraints or '未记录'}\n"
        )

    def run_selected_history_fix(self) -> None:
        if self.is_task_running():
            messagebox.showwarning("提示", "当前有任务正在执行，请先等待或停止。")
            return
        entry = self.get_selected_history_entry()
        if not entry:
            messagebox.showwarning("提示", "请选择一条历史记录。")
            return

        fix_input = self.ask_history_fix_input(entry)
        if fix_input is None:
            return
        issue_text, attachment_paths = fix_input
        self.start_repair_fix(entry, issue_text, attachment_paths)

    def run_active_repair_session_fix(self) -> None:
        if self.is_task_running():
            messagebox.showwarning("提示", "当前有任务正在执行，请先等待或停止。")
            return
        if not self.active_repair_entry:
            self.set_selected_history_as_repair_session()
            if not self.active_repair_entry:
                return
        issue_text = self.repair_issue_text.get("1.0", "end").strip()
        placeholder = "在这里粘贴问题说明、战报日志或复现步骤；截图后直接 Ctrl+V 即可加入附件。"
        if issue_text == placeholder:
            issue_text = ""
        if not issue_text and not self.repair_attachment_paths:
            messagebox.showwarning("提示", "请先填写问题说明，或添加日志/截图附件。")
            return
        entry = self.active_repair_entry
        attachment_paths = list(self.repair_attachment_paths)
        self.start_repair_fix(entry, issue_text, attachment_paths)
        self.repair_issue_text.delete("1.0", "end")
        self.clear_repair_session_attachments()

    def start_repair_fix(self, entry: TaskHistoryEntry, issue_text: str, attachment_paths: list[str]) -> None:
        entry = self.repair_entry_with_local_context(entry)
        self.active_repair_entry = entry
        self.workspace_var.set(entry.workspace_root or self.workspace_var.get())
        if entry.payload_path:
            self.payload_var.set(entry.payload_path)
        if entry.task_dir:
            self.latest_task_dir_var.set(entry.task_dir)
        elif entry.archive_dir:
            self.append_log(f"[repair] 原临时任务目录已清理，将使用归档上下文辅助修复: {entry.archive_dir}")
        if entry.template_name:
            self.template_var.set(template_label_from_key(entry.template_name))
        if entry.scene_label:
            self.scene_var.set(entry.scene_label)
        if entry.model_preset_key:
            self.model_preset_key_var.set(entry.model_preset_key)
            self.model_preset_label_var.set(self.get_preset_label(entry.model_preset_key))
        if entry.model_name:
            if self.agent_backend_var.get() == "claude":
                self.claude_model_var.set(entry.model_name)
            else:
                self.codex_model_var.set(entry.model_name)
        if entry.codex_extra_args:
            if self.agent_backend_var.get() == "claude":
                self.claude_extra_args_var.set(entry.codex_extra_args)
            else:
                self.codex_extra_args_var.set(entry.codex_extra_args)
        self.suppress_requirement_change = True
        try:
            self.description_text.delete("1.0", "end")
            self.description_text.insert("1.0", entry.skill_description)
            self.protected_text.delete("1.0", "end")
            self.protected_text.insert("1.0", entry.protected_files)
            self.constraints_text.delete("1.0", "end")
            self.constraints_text.insert("1.0", entry.additional_constraints)
            self.refresh_prompt()
            self.accept_current_requirement_context()
        finally:
            self.suppress_requirement_change = False
        if not self.validate_workspace():
            return

        attachments = self.prepare_repair_attachments(entry, attachment_paths)
        if attachments:
            self.append_log("[repair] 已保存附件：\n" + "\n".join(str(path) for path in attachments))
        self.pending_repair_chat_path = self.append_repair_chat(entry, "用户", issue_text, attachments)

        run_prompt = self.prompt_for_current_backend(self.build_history_fix_prompt(entry, issue_text, attachments))
        active_key = (self.normalize_path(entry.task_dir) or self.normalize_path(entry.payload_path) or self.develop_resume_key(run_prompt)) + "::fix"
        same_backend = (entry.agent_backend or "codex") == (self.agent_backend_var.get().strip() or "codex")
        has_local_context = bool(entry.task_dir or entry.payload_path or entry.archive_dir)
        resume_session_id = entry.session_id.strip() if same_backend and not has_local_context else ""
        resume_last = same_backend and not bool(resume_session_id) and not has_local_context
        if same_backend and has_local_context:
            self.append_log("[repair] 当前任务没有记录原 session_id，将使用本地任务目录上下文开启修复，不续接最近 session。")
        if resume_last:
            confirm = messagebox.askyesno(
                "未记录 session",
                f"该历史记录没有保存 {self.current_backend_label()} session_id，将尝试续接最近的 {self.current_backend_label()} session，可能不是原任务。是否继续？",
            )
            if not confirm:
                return

        self.last_task_error_message = ""
        if not same_backend:
            self.append_log(
                f"[workflow-resume] 修复任务后端已从 {entry.agent_backend or 'codex'} 切到 {self.agent_backend_var.get().strip() or 'codex'}，改用本地任务上下文接力。"
            )
        self.save_settings()
        self.current_task_name = "续接修复"
        self.current_active_task_key = active_key
        self.mark_active_task_started(
            target_key=active_key,
            task_name="续接修复",
            step="develop",
            prompt=run_prompt,
            resumed_from=resume_session_id,
        )
        self.current_task_started_at = datetime.now()
        self.status_var.set(f"{self.current_backend_label()} 修复中")
        self.set_task_stage("基于历史任务修复中")
        self.append_log("[task] 开始续接历史任务修复")
        self.update_action_buttons()

        def on_complete(code: int) -> None:
            self.root.after(0, lambda: self.finish_task("续接修复", code))

        preset = get_preset(self.model_preset_key_var.get())
        run_prompt = self.prompt_for_current_backend(run_prompt)
        try:
            if self.agent_backend_var.get() == "claude":
                self.claude_runner.run_claude(
                    prompt=run_prompt,
                    workspace_root=self.workspace_var.get().strip(),
                    output_file=str(self.default_output_file()),
                    log_queue=self.log_queue,
                    on_complete=on_complete,
                    executable_path=self.claude_executable_var.get().strip(),
                    model=self.claude_model_var.get().strip(),
                    extra_args=self.claude_extra_args_var.get().strip(),
                    resume_session_id=resume_session_id,
                    resume_last=resume_last,
                    on_session_detected=lambda session_id, session_file: self.update_active_task_session(
                        active_key,
                        session_id,
                        session_file,
                    ),
                )
            else:
                self.codex_runner.run_codex(
                    prompt=run_prompt,
                    workspace_root=self.workspace_var.get().strip(),
                    output_file=str(self.default_output_file()),
                    log_queue=self.log_queue,
                    on_complete=on_complete,
                    executable_path=self.codex_executable_var.get().strip(),
                    model=self.codex_model_var.get().strip(),
                    extra_args=self.codex_extra_args_var.get().strip(),
                    preset_args=preset.preset_args,
                    resume_session_id=resume_session_id,
                    resume_last=resume_last,
                    on_session_detected=lambda session_id, session_file: self.update_active_task_session(
                        active_key,
                        session_id,
                        session_file,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", str(exc))
            self.status_var.set("就绪")
            self.active_task_service.update(active_key, status="failed")
            self.current_task_name = ""
            self.current_active_task_key = ""
            self.current_task_started_at = None
            self.update_action_buttons()

    def build_history_entry(self, task_name: str, code: int) -> TaskHistoryEntry:
        settings = self.collect_settings()
        status_text = "成功" if code == 0 else "失败"
        artifacts = [str(path) for path in self.current_task_artifacts[:10]]
        active_info = {}
        if self.current_active_task_key:
            active_info = self.active_task_service.load().get(self.current_active_task_key, {})
        return TaskHistoryEntry(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            task_name=task_name,
            status_code=code,
            status_text=status_text,
            workspace_root=settings.workspace_root,
            battle_root=self.battle_root_var.get().strip(),
            template_name=settings.template_name,
            scene_label=settings.scene_label,
            agent_backend=settings.agent_backend,
            model_preset_key=settings.model_preset_key,
            model_name=settings.claude_model if settings.agent_backend == "claude" else settings.codex_model,
            codex_extra_args=settings.claude_extra_args if settings.agent_backend == "claude" else settings.codex_extra_args,
            payload_path=settings.payload_path,
            task_dir=settings.last_task_dir,
            output_file=str(self.default_output_file()),
            archive_dir=self.current_archive_dir,
            skill_description=settings.skill_description,
            protected_files=settings.protected_files,
            additional_constraints=settings.additional_constraints,
            dedupe_existing=settings.dedupe_existing,
            session_id=str(active_info.get("session_id", "") or ""),
            session_file=str(active_info.get("session_file", "") or ""),
            artifacts=artifacts,
        )

    def get_text(self, widget: tk.Text) -> str:
        return widget.get("1.0", "end").strip()

    def current_template_key(self) -> str:
        return template_key_from_label(self.template_var.get().strip())

    def refresh_prompt(self) -> None:
        template_name = self.current_template_key()
        prompt = build_prompt(
            template_name,
            self.get_text(self.description_text) if hasattr(self, "description_text") else "",
            self.get_text(self.protected_text) if hasattr(self, "protected_text") else "",
            self.get_text(self.constraints_text) if hasattr(self, "constraints_text") else "",
        )
        if hasattr(self, "template_hint_var"):
            self.template_hint_var.set(TEMPLATE_OPTIONS.get(template_name, ""))
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", prompt)

    def copy_prompt(self) -> None:
        prompt = self.prompt_text.get("1.0", "end").strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(prompt)
        self.status_var.set("Prompt 已复制到剪贴板")

    def collect_settings(self) -> AppSettings:
        return AppSettings(
            workspace_root=self.workspace_var.get().strip(),
            config_dir=self.config_dir_var.get().strip(),
            skill_excel_path=self.skill_excel_var.get().strip(),
            war_excel_path=self.war_excel_var.get().strip(),
            backup_dir=self.backup_dir_var.get().strip(),
            copy_dir=self.copy_dir_var.get().strip(),
            payload_path=self.payload_var.get().strip(),
            template_name=self.current_template_key(),
            agent_backend=self.agent_backend_var.get().strip() or "codex",
            model_preset_key=self.model_preset_key_var.get().strip(),
            codex_executable=self.codex_executable_var.get().strip(),
            claude_executable=self.claude_executable_var.get().strip(),
            python_executable=self.python_executable_var.get().strip(),
            codex_model=self.codex_model_var.get().strip(),
            codex_extra_args=self.codex_extra_args_var.get().strip(),
            claude_model=self.claude_model_var.get().strip(),
            claude_extra_args=self.claude_extra_args_var.get().strip(),
            scene_label=self.scene_var.get().strip(),
            dedupe_existing=self.dedupe_var.get(),
            serial_include_real_writeback=self.serial_include_real_var.get(),
            skill_description=self.get_text(self.description_text),
            additional_constraints=self.get_text(self.constraints_text),
            protected_files=self.get_text(self.protected_text),
            last_prompt=self.prompt_text.get("1.0", "end").strip(),
            last_output_file=str(self.default_output_file()),
            last_task_dir=self.latest_task_dir_var.get().strip(),
        )

    def save_settings(self) -> None:
        self.settings = self.collect_settings()
        self.settings_service.save(self.settings)
        self.refresh_command_preview()
        self.status_var.set("设置已保存")

    def write_full_log(self, text: str) -> None:
        self.full_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.full_log_path.open("a", encoding="utf-8") as fp:
            fp.write(text)

    def append_log(self, text: str) -> None:
        self.last_log_at = datetime.now()
        self.last_log_time_var.set(self.last_log_at.strftime("%H:%M:%S"))
        full_text = self.timestamp_log_text(text)
        self.write_full_log(full_text if full_text.endswith("\n") else full_text + "\n")
        visible_text = self.visible_log_text(text)
        if not visible_text:
            return
        self.log_text.insert("end", visible_text)
        if not visible_text.endswith("\n"):
            self.log_text.insert("end", "\n")
        self.trim_log_if_needed()
        self.log_text.see("end")
        self.append_workbench_log(visible_text)

    def timestamp_log_text(self, text: str) -> str:
        stamp = datetime.now().strftime("[%H:%M:%S]")
        lines = text.splitlines()
        if not lines:
            return stamp
        return "\n".join(f"{stamp} {line}" if line else stamp for line in lines)

    def visible_log_text(self, text: str) -> str:
        visible = [line for line in text.splitlines() if self.is_core_log_line(line)]
        if not visible:
            return ""
        return self.timestamp_log_text("\n".join(visible))

    def is_core_log_line(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if stripped.startswith(self.CORE_LOG_PREFIXES):
            return True
        return any(token in stripped for token in self.CORE_LOG_CONTAINS)

    def append_workbench_log(self, text: str) -> None:
        if not hasattr(self, "workbench_log_text"):
            return
        self.workbench_log_text.configure(state="normal")
        self.workbench_log_text.insert("end", text)
        if not text.endswith("\n"):
            self.workbench_log_text.insert("end", "\n")
        self.trim_text_widget_lines(self.workbench_log_text, 300)
        self.workbench_log_text.see("end")
        self.workbench_log_text.configure(state="disabled")

    def show_log_tab(self) -> None:
        if hasattr(self, "notebook"):
            try:
                self.notebook.select(2)
            except Exception:  # noqa: BLE001
                return
        if hasattr(self, "log_text"):
            self.log_text.see("end")

    def clear_visible_log(self) -> None:
        self.log_text.delete("1.0", "end")
        if hasattr(self, "workbench_log_text"):
            self.workbench_log_text.configure(state="normal")
            self.workbench_log_text.delete("1.0", "end")
            self.workbench_log_text.configure(state="disabled")
        self.write_full_log("[log-ui] visible log cleared\n")

    def open_full_log_file(self) -> None:
        if self.full_log_path.exists():
            try:
                os.startfile(str(self.full_log_path))
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("错误", str(exc))
        else:
            messagebox.showwarning("提示", "完整日志文件尚未生成。")

    def open_log_directory(self) -> None:
        if self.log_dir.exists():
            try:
                os.startfile(str(self.log_dir))
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("错误", str(exc))
        else:
            messagebox.showwarning("提示", "日志目录不存在。")

    def poll_logs(self) -> None:
        self.flush_log_queue(max_batches=1)
        self.root.after(self.LOG_FLUSH_INTERVAL_MS, self.poll_logs)

    def poll_runtime_status(self) -> None:
        if self.current_task_name and self.current_task_started_at:
            delta = datetime.now() - self.current_task_started_at
            total_seconds = max(0, int(delta.total_seconds()))
            minutes, seconds = divmod(total_seconds, 60)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                self.elapsed_var.set(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            else:
                self.elapsed_var.set(f"{minutes:02d}:{seconds:02d}")

            if self.last_log_at:
                idle_seconds = max(0, int((datetime.now() - self.last_log_at).total_seconds()))
                if idle_seconds >= 300:
                    self.runtime_hint_var.set(
                        f"当前任务: {self.current_task_name}，已连续 {idle_seconds} 秒没有新日志；如果产物目录也没有更新，建议停止后重试。"
                    )
                elif idle_seconds >= 60:
                    self.runtime_hint_var.set(
                        f"当前任务: {self.current_task_name}，最近 {idle_seconds} 秒没有新日志，通常仍在模型推理或脚本处理中。"
                    )
                elif idle_seconds >= 15:
                    self.runtime_hint_var.set(
                        f"当前任务: {self.current_task_name}，最近 {idle_seconds} 秒没有新日志，请继续等待。"
                    )
                else:
                    self.runtime_hint_var.set(
                        f"当前任务: {self.current_task_name}，最近一次日志距今 {idle_seconds} 秒。"
                    )
            else:
                self.runtime_hint_var.set(f"当前任务: {self.current_task_name}，尚未收到日志输出。")
        else:
            self.elapsed_var.set("00:00")
            if self.last_log_at:
                self.runtime_hint_var.set(f"最近一次日志时间: {self.last_log_at.strftime('%H:%M:%S')}")
            else:
                self.runtime_hint_var.set("等待开始任务。")

        self.root.after(self.STATUS_TICK_MS, self.poll_runtime_status)

    def set_task_stage(self, stage: str) -> None:
        self.stage_var.set(stage)

    def flush_log_queue(self, max_batches: int | None = 1) -> None:
        lines: list[str] = []
        consumed = 0
        limit = None if max_batches is None else self.LOG_BATCH_SIZE * max_batches
        while limit is None or consumed < limit:
            try:
                lines.append(self.log_queue.get_nowait())
                consumed += 1
            except queue.Empty:
                break
        if lines:
            safe_lines = self.log_sanitizer.sanitize_lines(lines)
            if safe_lines:
                self.append_log("\n".join(safe_lines) + "\n")

    def trim_log_if_needed(self) -> None:
        self.trim_text_widget_lines(self.log_text, self.LOG_MAX_LINES)

    def trim_text_widget_lines(self, widget: tk.Text, max_lines: int) -> None:
        try:
            line_count = int(widget.index("end-1c").split(".")[0])
        except Exception:  # noqa: BLE001
            return
        if line_count <= max_lines:
            return
        lines_to_trim = line_count - max_lines
        widget.delete("1.0", f"{lines_to_trim + 1}.0")

    def validate_workspace(self) -> bool:
        if not self.workspace_var.get().strip():
            messagebox.showerror("错误", "请先选择工作目录")
            return False
        if not self.battle_root_var.get().strip():
            messagebox.showerror("错误", "当前工作目录下未识别到 xgame_server/service/battle")
            return False
        return True

    def stop_current_task(self) -> None:
        stopped = False
        if self.current_agent_is_running():
            stopped = self.stop_current_agent()
        elif self.local_script_runner.is_running():
            stopped = self.local_script_runner.stop_running()
        elif self.writeback_service.is_running():
            stopped = self.writeback_service.stop_running()

        if stopped:
            if self.serial_workflow_active:
                self.stop_serial_workflow("串行流程已被手动停止。")
            if self.current_active_task_key:
                self.active_task_service.update(
                    self.current_active_task_key,
                    status="interrupted",
                    task_dir=self.latest_task_dir_var.get().strip(),
                    payload_path=self.payload_var.get().strip(),
                )
            self.current_task_name = ""
            self.current_active_task_key = ""
            self.current_task_started_at = None
            self.status_var.set("就绪")
            self.set_task_stage("已手动停止")
            self.append_log("[task] 已手动停止当前任务")
            self.update_action_buttons()
            messagebox.showinfo("提示", "已停止当前任务")
        else:
            messagebox.showwarning("提示", "当前没有正在运行的任务")

    def build_local_script_args(self) -> list[str]:
        args = [
            "--workspace-root",
            self.workspace_var.get().strip(),
        ]
        battle_root = self.battle_root_var.get().strip()
        if battle_root:
            args.extend(["--battle-root", battle_root])
        task_dir = self.latest_task_dir_var.get().strip()
        if task_dir:
            args.extend(["--task-dir", task_dir])
        payload = self.payload_var.get().strip()
        if payload:
            args.extend(["--payload", payload])
        return args

    def run_local_script_task(
        self,
        *,
        task_name: str,
        stage_name: str,
        status_text: str,
        log_text: str,
        script_name: str,
    ) -> None:
        self.last_task_error_message = ""
        self.save_settings()
        self.current_task_name = task_name
        self.current_active_task_key = self.current_target_key()
        self.mark_active_task_started(
            target_key=self.current_active_task_key,
            task_name=task_name,
            step=self.task_name_to_step(task_name),
        )
        self.current_task_started_at = datetime.now()
        self.status_var.set(status_text)
        self.set_task_stage(stage_name)
        self.append_log(log_text)
        self.update_action_buttons()

        def on_complete(code: int) -> None:
            self.root.after(0, lambda: self.finish_task(task_name, code))

        try:
            self.local_script_runner.run_script(
                script_path=str(self.bundled_script_path(script_name)),
                script_args=self.build_local_script_args(),
                python_executable=self.python_executable_var.get().strip(),
                workdir=self.workspace_var.get().strip(),
                log_queue=self.log_queue,
                on_complete=on_complete,
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", str(exc))
            self.status_var.set("就绪")
            if self.current_active_task_key:
                self.active_task_service.update(self.current_active_task_key, status="failed")
            self.current_task_name = ""
            self.current_active_task_key = ""
            self.current_task_started_at = None
            self.update_action_buttons()

    def run_local_audit(self) -> None:
        if self.is_task_running():
            messagebox.showwarning("提示", "当前已有任务在执行，请等待完成后再执行本地预审。")
            return
        if not self.validate_workspace():
            return
        payload = self.payload_var.get().strip()
        if not payload or not Path(payload).exists():
            messagebox.showerror("错误", "请先选择有效的 temp_excel_payload.json，再执行本地预审。")
            return
        self.run_local_script_task(
            task_name="本地预审",
            stage_name="本地技能预审中",
            status_text="本地预审中",
            log_text="[task] 开始执行本地预审",
            script_name="run_local_skill_audit.py",
        )

    def run_local_compile(self) -> None:
        if self.is_task_running():
            messagebox.showwarning("提示", "当前已有任务在执行，请等待完成后再执行本地编译。")
            return
        if not self.validate_workspace():
            return
        payload = self.payload_var.get().strip()
        if not payload or not Path(payload).exists():
            messagebox.showerror("错误", "请先选择有效的 temp_excel_payload.json，再执行本地编译。")
            return
        self.run_local_script_task(
            task_name="本地编译",
            stage_name="本地技能编译中",
            status_text="本地编译中",
            log_text="[task] 开始执行本地编译",
            script_name="run_local_skill_compile.py",
        )

    def run_develop(self) -> None:
        state = self.build_workflow_state()
        if not state["can_develop"]:
            messagebox.showwarning("提示", str(state["next_message"]))
            return
        if not self.validate_workspace():
            return
        prompt = self.prompt_text.get("1.0", "end").strip()
        if not prompt:
            messagebox.showerror("错误", "Prompt 不能为空")
            return
        if state.get("requirement_changed"):
            self.sync_changed_requirement_to_current_task()
        resume_match = self.find_resumable_develop_task(prompt)
        resume_key = ""
        resume_session_id = ""
        resume_last = False
        run_prompt = prompt
        if resume_match:
            resume_key, resume_info = resume_match
            previous_backend = str(resume_info.get("agent_backend", "") or "codex")
            current_backend = self.agent_backend_var.get().strip() or "codex"
            if previous_backend == current_backend:
                resume_session_id = str(resume_info.get("session_id", "") or "")
                resume_last = not bool(resume_session_id)
            else:
                resume_session_id = ""
                resume_last = False
            run_prompt = self.build_resume_develop_prompt(prompt, resume_info)
            task_dir = str(resume_info.get("task_dir", "") or "")
            payload_path = str(resume_info.get("payload_path", "") or "")
            selected_task_dir = self.normalize_path(self.latest_task_dir_var.get())
            if selected_task_dir and task_dir and self.normalize_path(task_dir) != selected_task_dir:
                self.append_log(
                    f"[workflow-guard] 已阻止跨任务续接：当前={selected_task_dir}，候选={task_dir}"
                )
                resume_match = None
                resume_key = ""
                resume_session_id = ""
                resume_last = False
                run_prompt = self.build_named_task_develop_prompt(prompt)
            else:
                if task_dir and Path(task_dir).exists():
                    self.latest_task_dir_var.set(task_dir)
                if payload_path and Path(payload_path).exists():
                    self.payload_var.set(payload_path)
                self.append_log(
                    "[workflow-resume] 命中未完成的技能开发任务，"
                    + (
                        f"同后端续接 session={resume_session_id}"
                        if resume_session_id
                        else (
                            f"后端已从 {previous_backend} 切到 {current_backend}，改用本地任务上下文接力"
                            if previous_backend != current_backend
                            else f"将尝试续接最近的 {self.current_backend_label()} session"
                        )
                    )
                )
        else:
            run_prompt = self.build_named_task_develop_prompt(prompt)
        active_key = resume_key or self.develop_resume_key(prompt)
        self.last_task_error_message = ""
        self.save_settings()
        self.current_task_name = "技能开发"
        self.current_active_task_key = active_key
        self.mark_active_task_started(
            target_key=active_key,
            task_name="技能开发",
            step="develop",
            prompt=prompt,
            resumed_from=resume_session_id,
        )
        self.current_task_started_at = datetime.now()
        self.status_var.set(f"{self.current_backend_label()} 开发中")
        self.set_task_stage("代码审计 / 生成中")
        self.append_log("[task] 开始执行技能开发")
        self.update_action_buttons()

        def on_complete(code: int) -> None:
            self.root.after(0, lambda: self.finish_task("技能开发", code))

        preset = get_preset(self.model_preset_key_var.get())
        try:
            if self.agent_backend_var.get() == "claude":
                self.claude_runner.run_claude(
                    prompt=run_prompt,
                    workspace_root=self.workspace_var.get().strip(),
                    output_file=str(self.default_output_file()),
                    log_queue=self.log_queue,
                    on_complete=on_complete,
                    executable_path=self.claude_executable_var.get().strip(),
                    model=self.claude_model_var.get().strip(),
                    extra_args=self.claude_extra_args_var.get().strip(),
                    resume_session_id=resume_session_id,
                    resume_last=resume_last,
                    on_session_detected=lambda session_id, session_file: self.update_active_task_session(
                        active_key,
                        session_id,
                        session_file,
                    ),
                )
            else:
                self.codex_runner.run_codex(
                    prompt=run_prompt,
                    workspace_root=self.workspace_var.get().strip(),
                    output_file=str(self.default_output_file()),
                    log_queue=self.log_queue,
                    on_complete=on_complete,
                    executable_path=self.codex_executable_var.get().strip(),
                    model=self.codex_model_var.get().strip(),
                    extra_args=self.codex_extra_args_var.get().strip(),
                    preset_args=preset.preset_args,
                    resume_session_id=resume_session_id,
                    resume_last=resume_last,
                    on_session_detected=lambda session_id, session_file: self.update_active_task_session(
                        active_key,
                        session_id,
                        session_file,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", str(exc))
            self.status_var.set("就绪")
            if self.current_active_task_key:
                self.active_task_service.update(self.current_active_task_key, status="failed")
            self.current_task_name = ""
            self.current_active_task_key = ""
            self.current_task_started_at = None
            self.update_action_buttons()

    def run_test(self) -> None:
        state = self.build_workflow_state()
        if not state["can_test"]:
            messagebox.showwarning("提示", str(state["next_message"]))
            return
        if not self.validate_workspace():
            return
        self.run_local_script_task(
            task_name="技能测试",
            stage_name="本地技能测试中",
            status_text="本地测试中",
            log_text="[task] 开始执行技能测试（本地脚本）",
            script_name="run_local_skill_test.py",
        )

    def write_excel_copy(self) -> None:
        self.run_writeback(write_copy=True, dry_run=False)

    def write_excel_real(self) -> None:
        preview_summary = self.writeback_service.last_summary_lines
        if preview_summary:
            summary_text = "\n".join(preview_summary[:12])
            if len(preview_summary) > 12:
                summary_text += f"\n... 另有 {len(preview_summary) - 12} 行摘要"
            if not messagebox.askyesno(
                "确认写回正式 Excel",
                "将按最近一次预览结果写回正式 Excel：\n\n"
                f"{summary_text}\n\n"
                "请确认副本检查无误后继续。",
            ):
                return
        self.run_writeback(write_copy=False, dry_run=False)

    def write_excel_dry_run(self) -> None:
        self.run_writeback(write_copy=False, dry_run=True)

    def run_writeback(self, write_copy: bool, dry_run: bool) -> None:
        state = self.build_workflow_state()
        if dry_run:
            allowed = bool(state["can_preview"])
        elif write_copy:
            allowed = bool(state["can_copy"])
        else:
            allowed = bool(state["can_real"])
        if not allowed:
            messagebox.showwarning("提示", str(state["next_message"]))
            return

        payload_path = self.payload_var.get().strip()
        if not payload_path:
            messagebox.showerror("错误", "请先选择 temp_excel_payload.json")
            return
        if not Path(payload_path).exists():
            messagebox.showerror("错误", "payload 文件不存在")
            return
        selection_error = self.validate_current_workspace_selection()
        if selection_error:
            messagebox.showerror("错误", selection_error)
            return
        self.refresh_config_excel_paths(show_error=False)
        if not self.skill_excel_var.get().strip() or not Path(self.skill_excel_var.get().strip()).exists():
            messagebox.showerror("错误", "配置目录下未找到技能 Excel，请先确认配置目录。")
            return
        if not self.war_excel_var.get().strip() or not Path(self.war_excel_var.get().strip()).exists():
            messagebox.showerror("错误", "配置目录下未找到战报 Excel，请先确认配置目录。")
            return
        if write_copy and not self.copy_dir_var.get().strip():
            messagebox.showerror("错误", "写入 Excel 副本前，请先设置副本输出目录。")
            return
        self.save_settings()
        action_name = "写入 Excel 副本" if write_copy else ("预览回写" if dry_run else "写回正式 Excel")
        self.current_task_name = action_name
        self.current_active_task_key = self.current_target_key()
        self.mark_active_task_started(
            target_key=self.current_active_task_key,
            task_name=action_name,
            step=self.task_name_to_step(action_name),
        )
        self.current_task_started_at = datetime.now()
        self.status_var.set(action_name + " 中")
        self.set_task_stage("Excel 写回中")
        self.append_log(f"[task] 开始执行 {action_name}")
        self.update_action_buttons()

        def on_complete(code: int) -> None:
            self.root.after(0, lambda: self.finish_task(action_name, code))

        try:
            self.writeback_service.run_writeback(
                payload_path=payload_path,
                skill_excel_path=self.skill_excel_var.get().strip(),
                war_excel_path=self.war_excel_var.get().strip(),
                backup_dir=self.backup_dir_var.get().strip(),
                copy_dir=self.copy_dir_var.get().strip(),
                dedupe_existing=self.dedupe_var.get(),
                dry_run=dry_run,
                write_copy=write_copy,
                python_executable=self.python_executable_var.get().strip(),
                log_queue=self.log_queue,
                on_complete=on_complete,
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", str(exc))
            if self.current_active_task_key:
                self.active_task_service.update(self.current_active_task_key, status="failed")
            self.current_task_name = ""
            self.current_active_task_key = ""
            self.current_task_started_at = None
            self.status_var.set("就绪")
            self.update_action_buttons()

    def finish_task(self, task_name: str, code: int) -> None:
        serial_context = self.serial_workflow_active
        self.flush_log_queue(max_batches=None)
        remaining_safe_lines = self.log_sanitizer.flush()
        if remaining_safe_lines:
            self.append_log("\n".join(remaining_safe_lines) + "\n")
        self.refresh_temp_workspace_views(force_latest=code == 0 and self.task_name_to_step(task_name) == "develop")
        if self.codex_runner.last_error_message:
            self.last_task_error_message = self.codex_runner.last_error_message
        elif self.claude_runner.last_error_message:
            self.last_task_error_message = self.claude_runner.last_error_message
        elif self.local_script_runner.last_error_message:
            self.last_task_error_message = self.local_script_runner.last_error_message
        elif self.writeback_service.last_error_message:
            self.last_task_error_message = self.writeback_service.last_error_message
        if code == 0 and self.task_name_to_step(task_name) == "real":
            self.current_archive_dir = self.archive_current_task()
        if code == 0 and self.task_name_to_step(task_name) == "develop":
            self.mark_downstream_steps_dirty_after_develop()
        history_entry = self.build_history_entry(task_name, code)
        self.history_entries = self.history_service.append(history_entry)
        self.refresh_history_view()
        if task_name == "续接修复" and self.active_repair_entry:
            assistant_text = ""
            output_file = self.default_output_file()
            if output_file.exists():
                try:
                    assistant_text = output_file.read_text(encoding="utf-8", errors="replace").strip()
                except Exception as exc:  # noqa: BLE001
                    assistant_text = f"读取模型输出失败: {exc}"
            if not assistant_text:
                assistant_text = f"修复任务结束，退出码: {code}"
            if self.last_task_error_message:
                assistant_text += f"\n\n错误详情:\n{self.last_task_error_message}"
            self.append_repair_chat(self.active_repair_entry, "模型", assistant_text)
            if history_entry.task_dir or history_entry.payload_path or history_entry.session_id:
                self.active_repair_entry = history_entry
                self.repair_session_var.set(
                    f"当前会话：{self.extract_skill_title(history_entry.skill_description)} | {history_entry.timestamp}"
                )
                self.show_repair_chat_for_entry(history_entry)
            self.pending_repair_chat_path = None
        if task_name in {"预览回写", "写入 Excel 副本", "写回正式 Excel"}:
            if self.writeback_service.last_summary_lines:
                self.append_log("\n".join(self.writeback_service.last_summary_lines))
            if self.writeback_service.last_verify_lines:
                self.append_log("\n".join(self.writeback_service.last_verify_lines))
        self.settings = self.collect_settings()
        self.settings_service.save(self.settings)
        if self.current_active_task_key:
            self.active_task_service.update(
                self.current_active_task_key,
                status="completed" if code == 0 else "failed",
                task_dir=self.latest_task_dir_var.get().strip(),
                payload_path=self.payload_var.get().strip(),
            )
        self.write_task_handoff(
            status="completed" if code == 0 else "failed",
            current_step=self.task_name_to_step(task_name),
        )
        self.current_task_name = ""
        self.current_active_task_key = ""
        self.current_archive_dir = ""
        self.current_task_started_at = None
        self.status_var.set("就绪")
        self.set_task_stage("已完成" if code == 0 else "执行失败")
        self.append_log(f"[task] {task_name}结束，退出码: {code}")
        if code == 0 and self.task_name_to_step(task_name) == "real":
            self.finalize_after_real_writeback()
        self.update_action_buttons()
        if serial_context:
            self.handle_serial_task_result(task_name, code)
            return
        if code == 0:
            payload_path = self.payload_var.get().strip()
            task_dir = self.latest_task_dir_var.get().strip()
            detail = f"{task_name}完成"
            if task_dir:
                artifact_count = len(self.current_task_artifacts)
                detail += f"\n\n最新任务目录:\n{task_dir}\n\n已识别产物数量: {artifact_count}"
            if task_name == "本地预审":
                if payload_path and Path(payload_path).exists():
                    detail += f"\n\n当前 payload:\n{payload_path}"
                detail += "\n\n本地预审不会请求模型，可先根据日志确认复用情况、产物完整性和测试脚本就绪状态。"
            elif task_name == "本地编译":
                if task_dir:
                    detail += "\n\n本地编译会覆盖当前任务目录中的 temp_skill_config.lua 和 test_skill_temp.lua。"
                if payload_path and Path(payload_path).exists():
                    detail += f"\n\n当前 payload:\n{payload_path}"
            elif payload_path and Path(payload_path).exists():
                detail += f"\n\n已生成 payload:\n{payload_path}\n\n可以继续执行“写入 Excel 副本”或“写回正式 Excel”。"
            messagebox.showinfo("完成", detail)
        else:
            detail = f"{task_name}结束，但退出码为 {code}"
            if self.last_task_error_message:
                detail += f"\n\n错误详情:\n{self.last_task_error_message}"
            detail += f"\n\n完整日志:\n{self.full_log_path}"
            self.show_log_tab()
            messagebox.showwarning("提示", detail)

    def finalize_after_real_writeback(self) -> None:
        self.append_log("[finalize] 正式 Excel 写回成功，开始收尾。")
        self.rebuild_battle_knowledge_index()
        self.sync_bundled_skill_runtime()
        removed, failed = self.cleanup_after_real_writeback()
        self.append_log(f"[finalize] 临时产物清理完成：删除 {removed} 项，失败 {failed} 项。")
        self.refresh_temp_workspace_views(force_latest=False)

    def archive_current_task(self) -> str:
        task_dir_value = self.latest_task_dir_var.get().strip()
        if not task_dir_value:
            return ""
        task_dir = Path(task_dir_value)
        if not task_dir.exists() or not task_dir.is_dir():
            return ""
        archive_root = self.data_dir / "task_archives"
        archive_root.mkdir(parents=True, exist_ok=True)
        safe_name = task_dir.name or "task"
        archive_dir = archive_root / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}"
        counter = 1
        while archive_dir.exists():
            archive_dir = archive_root / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}_{counter}"
            counter += 1
        archive_dir.mkdir(parents=True, exist_ok=True)
        keep_patterns = (
            "config/temp_excel_payload.json",
            "docs/IMPLEMENTATION.md",
            "task_state.json",
            "task_handoff.md",
            "repair/_repair_chat.md",
            "*.lua",
            "*.json",
            "*.md",
            "*.log",
        )
        copied = 0
        for pattern in keep_patterns:
            for source in task_dir.glob(pattern):
                if not source.is_file():
                    continue
                destination = archive_dir / source.relative_to(task_dir)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    continue
                shutil.copy2(source, destination)
                copied += 1
        for folder_name in ("scripts", "tests", "logs"):
            source_dir = task_dir / folder_name
            if source_dir.exists() and source_dir.is_dir():
                shutil.copytree(source_dir, archive_dir / folder_name, dirs_exist_ok=True)
        for folder_name in ("repair/attachments", "repair/clipboard"):
            source_dir = task_dir / folder_name
            if source_dir.exists() and source_dir.is_dir():
                shutil.copytree(source_dir, archive_dir / folder_name)
        self.append_log(f"[archive] 已归档正式落表任务: {archive_dir}，文件 {copied} 个")
        return str(archive_dir)

    def rebuild_battle_knowledge_index(self) -> None:
        battle_root = self.battle_root_var.get().strip()
        if not battle_root or not Path(battle_root).exists():
            self.append_log("[finalize] 跳过知识索引重建：battle_root 不存在。")
            return

        script_path = self.bundled_skill_service.installed_skill_path("family-battle-skill-writer") / "scripts" / "build_battle_knowledge_index.py"
        if not script_path.exists():
            self.append_log(f"[finalize] 跳过知识索引重建：脚本不存在 {script_path}")
            return

        try:
            python_exe = self.writeback_service.resolve_python_executable(self.python_executable_var.get().strip())
            env = os.environ.copy()
            env.setdefault("PYTHONIOENCODING", "utf-8")
            env.setdefault("PYTHONUTF8", "1")
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [python_exe, str(script_path), "--battle-root", battle_root],
                cwd=str(Path(battle_root)),
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=120,
                check=False,
            )
            output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
            if output:
                self.append_log(output + "\n")
            if result.returncode == 0:
                self.append_log("[finalize] battle knowledge index 已重建。")
            else:
                self.append_log(f"[finalize] battle knowledge index 重建失败，退出码: {result.returncode}")
        except Exception as exc:  # noqa: BLE001
            self.append_log(f"[finalize] battle knowledge index 重建异常: {exc}")

    def sync_bundled_skill_runtime(self) -> None:
        try:
            results = self.bundled_skill_service.sync_all()
            if not results:
                self.append_log("[finalize] 没有发现 bundled skills，跳过同步。")
                return
            for result in results:
                self.append_log(f"[finalize] skill {result.action}: {result.name} -> {result.destination}")
        except Exception as exc:  # noqa: BLE001
            self.append_log(f"[finalize] bundled skill 同步失败: {exc}")

    def cleanup_after_real_writeback(self) -> tuple[int, int]:
        temp_root = self.workspace_manager.temp_workspace_root(self.workspace_var.get().strip())
        if not temp_root:
            self.append_log("[finalize] 跳过临时清理：temp_skill_workspace 不存在。")
            return 0, 0

        candidates: list[Path] = []
        task_dir = self.latest_task_dir_var.get().strip()
        if task_dir:
            candidates.append(Path(task_dir))

        copy_dir = self.copy_dir_var.get().strip()
        if copy_dir:
            candidates.append(Path(copy_dir))

        global_root = self.workspace_manager.global_workspace_dir(temp_root)
        for name in ("excel_test_copy", "excel_reorder_test_copy", "excel_writeback_test"):
            candidates.append(global_root / name)

        removed = 0
        failed = 0
        seen: set[str] = set()
        for candidate in candidates:
            try:
                resolved = candidate.expanduser().resolve()
                root = temp_root.resolve()
                if str(resolved) in seen:
                    continue
                seen.add(str(resolved))
                resolved.relative_to(root)
                if not resolved.exists():
                    continue
                if resolved.name == "_battle_knowledge_cache":
                    continue
                if resolved.name == "excel_backup":
                    continue
                if resolved.is_dir():
                    shutil.rmtree(resolved)
                else:
                    resolved.unlink()
                removed += 1
                self.append_log(f"[finalize] removed temp artifact: {resolved}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.append_log(f"[finalize] failed to remove temp artifact {candidate}: {exc}")

        self.payload_var.set("")
        self.latest_task_dir_var.set("")
        return removed, failed

    def open_output_file(self) -> None:
        output_file = self.default_output_file()
        if output_file.exists():
            try:
                os.startfile(str(output_file))
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("错误", str(exc))
        else:
            messagebox.showwarning("提示", "尚未生成输出文件")

    def on_close(self) -> None:
        try:
            if self.codex_runner.is_running():
                self.codex_runner.stop_running()
            if self.claude_runner.is_running():
                self.claude_runner.stop_running()
            if self.local_script_runner.is_running():
                self.local_script_runner.stop_running()
            if self.writeback_service.is_running():
                self.writeback_service.stop_running()
            self.save_settings()
        finally:
            self.root.destroy()


def run_app() -> None:
    root = tk.Tk()
    app = SkillWriterApp(root)
    app.refresh_prompt()
    root.mainloop()
