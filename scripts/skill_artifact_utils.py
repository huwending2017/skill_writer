from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PRIMARY_PAYLOAD_NAME = "temp_excel_payload.json"
RUNTIME_TEST_NAME = "test_runtime_validation.lua"
TEMP_CONFIG_NAME = "temp_skill_config.lua"
IMPLEMENTATION_NAME = "IMPLEMENTATION.md"
CONFIG_DIR_NAME = "config"
SCRIPTS_DIR_NAME = "scripts"
TESTS_DIR_NAME = "tests"
DOCS_DIR_NAME = "docs"
GLOBAL_DIR_NAME = "_global"
OPERATIONAL_DIR_NAMES = {
    GLOBAL_DIR_NAME,
    "excel_backup",
    "excel_test_copy",
    "excel_reorder_test_copy",
    "excel_writeback_test",
    "__pycache__",
    ".pycache_tmp",
    "_battle_knowledge_cache",
}


@dataclass
class TaskContext:
    workspace_root: Path
    battle_root: Path
    temp_root: Path
    task_dir: Path
    payload_path: Path | None
    runtime_test_path: Path | None
    knowledge_index_path: Path | None

    def config_path(self, file_name: str) -> Path:
        return preferred_task_path(self.task_dir, CONFIG_DIR_NAME, file_name)

    def tests_path(self, file_name: str) -> Path:
        return preferred_task_path(self.task_dir, TESTS_DIR_NAME, file_name)

    def docs_path(self, file_name: str) -> Path:
        return preferred_task_path(self.task_dir, DOCS_DIR_NAME, file_name)

    def temp_config_path(self) -> str:
        return str(self.task_dir / CONFIG_DIR_NAME / TEMP_CONFIG_NAME).replace("\\", "/")


def resolve_battle_root(workspace_root: Path) -> Path:
    direct_candidates = [
        workspace_root / "xgame_server" / "service" / "battle",
        workspace_root / "service" / "battle",
        workspace_root,
    ]
    for candidate in direct_candidates:
        if (candidate / "module").exists() and (candidate / "service").exists():
            return candidate

    matches = list(workspace_root.rglob("xgame_server/service/battle"))
    if matches:
        return matches[0]

    nested = list(workspace_root.rglob("service/battle"))
    if nested:
        return nested[0]

    raise FileNotFoundError(f"cannot resolve battle_root from workspace: {workspace_root}")


def find_recent_task_dir(temp_root: Path) -> Path | None:
    if not temp_root.exists():
        return None

    candidates = [
        path
        for path in temp_root.iterdir()
        if path.is_dir() and path.name.lower() not in OPERATIONAL_DIR_NAMES
    ]
    if not candidates:
        return None

    def sort_key(path: Path) -> tuple[float, float, str]:
        payload = path / PRIMARY_PAYLOAD_NAME
        payload_mtime = payload.stat().st_mtime if payload.exists() else 0.0
        dir_mtime = path.stat().st_mtime
        return (payload_mtime, dir_mtime, path.name.lower())

    return sorted(candidates, key=sort_key, reverse=True)[0]


def preferred_task_path(task_dir: Path, folder: str, file_name: str) -> Path:
    canonical = task_dir / folder / file_name
    legacy = task_dir / file_name
    if canonical.exists() or not legacy.exists():
        return canonical
    return legacy


def resolve_task_context(
    workspace_root_value: str,
    battle_root_value: str = "",
    task_dir_value: str = "",
    payload_value: str = "",
) -> TaskContext:
    workspace_root = Path(workspace_root_value).expanduser().resolve()
    if not workspace_root.exists():
        raise FileNotFoundError(f"workspace_root not found: {workspace_root}")

    battle_root = (
        Path(battle_root_value).expanduser().resolve()
        if battle_root_value.strip()
        else resolve_battle_root(workspace_root)
    )
    temp_root = battle_root / "temp_skill_workspace"
    if not temp_root.exists():
        raise FileNotFoundError(f"temp_skill_workspace not found: {temp_root}")

    payload_path = Path(payload_value).expanduser().resolve() if payload_value.strip() else None

    if task_dir_value.strip():
        task_dir = Path(task_dir_value).expanduser().resolve()
    elif payload_path is not None:
        task_dir = payload_path.parent
    else:
        latest = find_recent_task_dir(temp_root)
        if latest is None:
            raise FileNotFoundError(f"no task dir found in temp workspace: {temp_root}")
        task_dir = latest

    if not task_dir.exists():
        raise FileNotFoundError(f"task_dir not found: {task_dir}")
    if payload_path is None:
        guessed_payload = preferred_task_path(task_dir, CONFIG_DIR_NAME, PRIMARY_PAYLOAD_NAME)
        payload_path = guessed_payload if guessed_payload.exists() else None

    runtime_test_path = preferred_task_path(task_dir, TESTS_DIR_NAME, RUNTIME_TEST_NAME)
    if not runtime_test_path.exists():
        runtime_test_path = None

    knowledge_index_path = temp_root / GLOBAL_DIR_NAME / "_battle_knowledge_cache" / "battle_knowledge_index.json"
    if not knowledge_index_path.exists():
        legacy_knowledge_index_path = temp_root / "_battle_knowledge_cache" / "battle_knowledge_index.json"
        knowledge_index_path = legacy_knowledge_index_path if legacy_knowledge_index_path.exists() else None

    return TaskContext(
        workspace_root=workspace_root,
        battle_root=battle_root,
        temp_root=temp_root,
        task_dir=task_dir,
        payload_path=payload_path,
        runtime_test_path=runtime_test_path,
        knowledge_index_path=knowledge_index_path,
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


USER_VISIBLE_PAYLOAD_FIELDS = {
    "name",
    "desc",
    "de_desc",
    "buff_desc",
    "desc1",
    "effect_desc",
    "beizhu2",
    "param1",
    "param2",
    "param3",
    "param4",
    "param5",
    "param6",
    "param7",
    "param8",
}


def find_suspicious_question_mark_fields(payload: dict[str, Any], limit: int = 20) -> list[str]:
    rows = payload.get("rows")
    if not isinstance(rows, dict):
        return []

    findings: list[str] = []
    for sheet_name, sheet_rows in rows.items():
        if not isinstance(sheet_rows, list):
            continue
        for index, row in enumerate(sheet_rows, start=1):
            if not isinstance(row, dict):
                continue
            row_key = row.get("key") or row.get("name") or row.get("id") or index
            for field in USER_VISIBLE_PAYLOAD_FIELDS:
                value = row.get(field)
                if not isinstance(value, str):
                    continue
                if "??" in value or value.count("?") >= 3:
                    findings.append(f"{sheet_name}[{index}] key={row_key} field={field} value={value[:80]}")
                    if len(findings) >= limit:
                        return findings
    return findings


def existing_action_paths(battle_root: Path, task_dir: Path, script_name: str) -> list[Path]:
    candidates = [
        battle_root / "module" / "actions_new" / f"action_{script_name}.lua",
        task_dir / SCRIPTS_DIR_NAME / f"action_{script_name}.lua",
        task_dir / f"action_{script_name}.lua",
    ]
    return [path for path in candidates if path.exists()]


def existing_buff_paths(battle_root: Path, task_dir: Path, script_name: str) -> list[Path]:
    candidates = [
        battle_root / "module" / "buffs_new" / f"buff_{script_name}.lua",
        task_dir / SCRIPTS_DIR_NAME / f"buff_{script_name}.lua",
        task_dir / f"buff_{script_name}.lua",
    ]
    return [path for path in candidates if path.exists()]


def collect_task_lua_scripts(task_dir: Path) -> list[Path]:
    roots = (task_dir, task_dir / SCRIPTS_DIR_NAME, task_dir / TESTS_DIR_NAME, task_dir / CONFIG_DIR_NAME)
    paths: list[Path] = []
    for root in roots:
        if root.exists():
            paths.extend(path for path in root.glob("*.lua") if path.is_file())
    return sorted(set(paths))


def task_name_tokens(task_dir: Path) -> set[str]:
    tokens = set()
    for item in re.split(r"[^0-9A-Za-z]+", task_dir.name.lower()):
        if len(item) >= 3:
            tokens.add(item)
    return tokens


def is_task_owned_lua_script(task_dir: Path, path: Path) -> bool:
    try:
        if path.resolve().parent in {task_dir.resolve(), (task_dir / SCRIPTS_DIR_NAME).resolve()}:
            return True
    except OSError:
        pass

    tokens = task_name_tokens(task_dir)
    if not tokens:
        return False

    stem = path.stem.lower()
    matched = [token for token in tokens if token in stem]
    return len(matched) >= 2


def audit_lua_chinese_comments(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    comment_lines = []
    chinese_comment_lines = []
    logic_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("--"):
            comment_lines.append(stripped)
            if re.search(r"[\u4e00-\u9fff]", stripped):
                chinese_comment_lines.append(stripped)
            continue
        logic_lines.append(stripped)

    errors: list[str] = []
    if "??" in text or text.count("?") >= 3:
        errors.append(f"{path.name} 存在疑似乱码问号，请先修复编码后再继续")

    if len(logic_lines) < 8:
        return errors

    min_chinese_comments = max(8, min(24, len(logic_lines) // 6))
    if len(chinese_comment_lines) < min_chinese_comments:
        errors.append(
            f"{path.name} 中文注释不足：当前 {len(chinese_comment_lines)} 行，至少需要 {min_chinese_comments} 行"
        )

    required_keywords = {
        "参数": "缺少参数含义说明",
        "事件": "缺少事件/触发时机说明",
        "战报": "缺少战报插入说明",
    }
    comment_text = "\n".join(chinese_comment_lines)
    for keyword, message in required_keywords.items():
        if keyword not in comment_text:
            errors.append(f"{path.name} {message}")

    return errors
