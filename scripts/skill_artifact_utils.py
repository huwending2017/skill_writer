from __future__ import annotations

import json
import re
import ast
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


PAYLOAD_SHEET_NAMES = ("skill", "skill_global", "skill_stage", "buff", "war_paper")
LEGACY_PAYLOAD_SHEET_ALIASES = {
    "data_skill": "skill",
    "data_skill_global": "skill_global",
    "data_skill_stage": "skill_stage",
    "data_buff": "buff",
    "data_war_paper": "war_paper",
    "skills": "skill",
    "stages": "skill_stage",
    "buffs": "buff",
    "war_papers": "war_paper",
}


def ensure_payload_rows(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept both the canonical rows payload and older sheet-at-root payloads."""

    rows = payload.get("rows")
    if isinstance(rows, dict):
        return payload

    detected_rows: dict[str, Any] = {}
    for sheet_name in PAYLOAD_SHEET_NAMES:
        sheet_rows = payload.get(sheet_name)
        if isinstance(sheet_rows, list):
            detected_rows[sheet_name] = sheet_rows
    for legacy_name, sheet_name in LEGACY_PAYLOAD_SHEET_ALIASES.items():
        legacy_value = payload.get(legacy_name)
        sheet_rows = None
        if isinstance(legacy_value, list):
            sheet_rows = legacy_value
        elif isinstance(legacy_value, dict) and isinstance(legacy_value.get("rows"), list):
            sheet_rows = legacy_value.get("rows")
        if sheet_rows is not None and sheet_name not in detected_rows:
            detected_rows[sheet_name] = sheet_rows

    if not detected_rows:
        return payload

    normalized = {
        key: value
        for key, value in payload.items()
        if key not in PAYLOAD_SHEET_NAMES and key not in LEGACY_PAYLOAD_SHEET_ALIASES and key != "rows"
    }
    normalized["rows"] = detected_rows
    return normalized


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

JSONISH_LIST_FRAGMENT_RE = re.compile(r"\[[^\[\]\r\n]*['\"][^\[\]\r\n]*\]")
JSONISH_DICT_FRAGMENT_RE = re.compile(r"\{[^{}\r\n]*[:=][^{}\r\n]*\}")


def _is_excel_config_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _excel_config_scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _excel_config_literal_text(value: Any) -> str | None:
    if isinstance(value, dict):
        return "" if not value else None
    if isinstance(value, (list, tuple)):
        if all(_is_excel_config_scalar(item) for item in value):
            return ",".join(_excel_config_scalar_text(item) for item in value)
        if all(isinstance(item, (list, tuple)) for item in value):
            groups: list[str] = []
            for item in value:
                if not all(_is_excel_config_scalar(part) for part in item):
                    return None
                groups.append(",".join(_excel_config_scalar_text(part) for part in item))
            return "|".join(groups)
    return None


def normalize_excel_config_literals_in_string(value: str) -> str:
    """Convert accidental JSON/Python list fragments into Excel config text.

    Example: 2,5,["ATK",10000],5032605 -> 2,5,ATK,10000,5032605.
    """

    def replace(match: re.Match[str]) -> str:
        fragment = match.group(0)
        try:
            parsed = ast.literal_eval(fragment)
        except (SyntaxError, ValueError):
            return fragment
        text = _excel_config_literal_text(parsed)
        return text if text is not None else fragment

    return JSONISH_LIST_FRAGMENT_RE.sub(replace, value)


def normalize_excel_config_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = ensure_payload_rows(payload)
    rows = payload.get("rows")
    if not isinstance(rows, dict):
        return payload

    normalized = dict(payload)
    normalized_rows: dict[str, Any] = {}
    for sheet_name, sheet_rows in rows.items():
        if not isinstance(sheet_rows, list):
            normalized_rows[sheet_name] = sheet_rows
            continue
        normalized_sheet_rows: list[Any] = []
        for row in sheet_rows:
            if not isinstance(row, dict):
                normalized_sheet_rows.append(row)
                continue
            normalized_row: dict[str, Any] = {}
            for field, value in row.items():
                if isinstance(value, str):
                    normalized_row[field] = normalize_excel_config_literals_in_string(value)
                elif isinstance(value, dict):
                    text = _excel_config_literal_text(value)
                    normalized_row[field] = text if text is not None else value
                else:
                    normalized_row[field] = value
            normalized_sheet_rows.append(normalized_row)
        normalized_rows[sheet_name] = normalized_sheet_rows
    normalized["rows"] = normalized_rows
    return normalized


def find_invalid_excel_config_literals(payload: dict[str, Any], limit: int = 30) -> list[str]:
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
            for field, value in row.items():
                if isinstance(value, dict) and value:
                    findings.append(f"{sheet_name}[{index}] key={row_key} field={field} uses dict literal; use comma/pipe config text")
                elif isinstance(value, str):
                    normalized = normalize_excel_config_literals_in_string(value)
                    if normalized != value:
                        findings.append(
                            f"{sheet_name}[{index}] key={row_key} field={field} contains JSON/Python list syntax: {value[:120]}"
                        )
                    elif JSONISH_DICT_FRAGMENT_RE.search(value):
                        findings.append(
                            f"{sheet_name}[{index}] key={row_key} field={field} contains dict-like syntax: {value[:120]}"
                        )
                if len(findings) >= limit:
                    return findings
    return findings


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

    min_chinese_comments = max(12, min(36, len(logic_lines) // 4))
    if len(chinese_comment_lines) < min_chinese_comments:
        errors.append(
            f"{path.name} 中文注释不足：当前 {len(chinese_comment_lines)} 行，至少需要 {min_chinese_comments} 行"
        )

    inline_chinese_comments = [
        line for line in lines
        if re.match(r"\s+--.*[\u4e00-\u9fff]", line)
    ]
    min_inline_comments = max(6, min(24, len(logic_lines) // 12))
    if len(inline_chinese_comments) < min_inline_comments:
        errors.append(
            f"{path.name} 函数内部关键逻辑注释不足：当前 {len(inline_chinese_comments)} 行，至少需要 {min_inline_comments} 行；关键 if/return、层数变化、缓存读写、监听注册、战报清理和伤害改写处需要就地中文注释"
        )

    required_keywords = {
        "参数": "缺少参数含义说明",
        "事件": "缺少事件/触发时机说明",
        "状态": "缺少状态读写说明",
        "异常": "缺少异常/短路保护说明",
        "战报": "缺少战报插入说明",
    }
    comment_text = "\n".join(chinese_comment_lines)
    for keyword, message in required_keywords.items():
        if keyword not in comment_text:
            errors.append(f"{path.name} {message}")

    if "local function debug_log" in text or "debug_log(" in text:
        errors.append(f"{path.name} 不允许使用 debug_log 包装函数；请在真实分支行直接调用 DEBUG(\"[技能名]\", ...)，保证战斗日志行号指向实际逻辑")

    inserts_back_to_current_skill = (
        "insert_effect_list(extern.skill" in text
        or "insert_effect_list(script.extern.skill" in text
        or re.search(r"local\s+\w+\s*=\s*\(?script\.extern\s+and\s+script\.extern\.skill", text)
        and re.search(r"insert_effect_list\(\s*\w+\s*,\s*nil\s*\)", text)
    )
    if "make_effect_records" in text and "extern.skill" in text and not inserts_back_to_current_skill:
        errors.append(
            f"{path.name} 存在事件/驻留 Buff 战报写入，但未看到 insert_effect_list(extern.skill, nil)；"
            "响应其他技能或伤害事件的战报必须插回当前 extern.skill，否则前端可能不展示或顺序漂移"
        )

    if "BUFF_OVERLYING_EFFECT_FUNC" in text and re.search(r"\bruntime\.\w+\s*=\s*extern\.overlying\b", text):
        errors.append(
            f"{path.name} 不允许把显示 Buff 的 extern.overlying 反写到 runtime；显示层只能由真实状态单向刷新，避免显示 Buff 清理/重建时误清业务层数"
        )

    if "DEBUG(" not in text:
        errors.append(f"{path.name} 缺少 DEBUG 排障日志，生成脚本必须在关键分支直接输出调试信息")

    missing_function_comments = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not (stripped.startswith("local function ") or stripped.startswith("function INTERFACE:")):
            continue
        previous = "\n".join(lines[max(0, index - 3):index])
        if not re.search(r"--.*[\u4e00-\u9fff]", previous):
            missing_function_comments.append(stripped)
    if missing_function_comments:
        preview = "; ".join(missing_function_comments[:5])
        errors.append(f"{path.name} 存在未被中文注释覆盖的函数: {preview}")

    return errors
