from __future__ import annotations

import json
import re
import ast
import hashlib
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
JSON_FILE_ENCODINGS = ("utf-8-sig", "utf-8", "utf-16", "utf-16-le", "utf-16-be", "gb18030", "gbk", "cp936")


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
    data = path.read_bytes()
    for encoding in JSON_FILE_ENCODINGS:
        try:
            text = data.decode(encoding).lstrip("\ufeff").replace("\x00", "")
            return json.loads(text)
        except (LookupError, UnicodeDecodeError, json.JSONDecodeError):
            continue
    text = data.decode("utf-8", errors="replace").lstrip("\ufeff").replace("\x00", "")
    return json.loads(text)


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

WAR_PAPER_DESC_ALIASES = (
    "desc1",
    "desc",
    "effect_desc",
    "report_desc",
    "report_text",
    "text",
    "content",
)
WAR_PAPER_NAME_ALIASES = (
    "name",
    "record_name",
    "war_name",
    "report_name",
    "enum_name",
    "record_key",
    "key",
)
WAR_PAPER_ACTION_KEYWORDS = (
    ("未触发", "fail"),
    ("触发", "trigger"),
    ("发动", "trigger"),
    ("获得", "gain"),
    ("失去", "loss"),
    ("增加", "add"),
    ("降低", "reduce"),
    ("减少", "reduce"),
    ("消失", "remove"),
    ("移除", "remove"),
    ("开始", "start"),
    ("结束", "end"),
    ("恢复", "restore"),
    ("驱散", "dispel"),
    ("伤害", "damage"),
    ("治疗", "cure"),
)
BUFF_NAME_SUFFIXES = (
    "核心",
    "属性",
    "破甲",
    "治疗提升",
    "智谋伤害",
    "受伤增加",
    "状态",
    "效果",
    "Buff",
    "BUFF",
)
SAFE_WAR_PAPER_NAME_RE = re.compile(r"^[A-Za-z_][0-9A-Za-z_]*$")
CJK_TEXT_RE = re.compile(r"[\u3400-\u9fff]")
PLACEHOLDER_ONLY_SLUG_RE = re.compile(r"^(s|d|f|u|x)(_(s|d|f|u|x))*$")

VALID_SKILL_TYPES = {1, 2, 3, 4, 6, 7}
DEFAULT_SKILL_TYPE = 4

SKILL_DESC_ALIASES = (
    "desc",
    "description",
    "skill_desc",
    "skill_description",
)

SKILL_DE_DESC_ALIASES = (
    "de_desc",
    "detail_desc",
    "detailed_desc",
    "skill_analysis",
    "analysis",
)

SKILL_TYPE_TEXT_FIELDS = (
    "skill_type_name",
    "skill_type_text",
    "skill_kind",
    "category",
    "skill_category",
    "type_name",
    "type",
    "desc",
    "de_desc",
    "description",
    "skill_description",
    "name",
)

SKILL_TYPE_KEYWORDS = (
    ("指挥", 1),
    ("主动", 2),
    ("突击", 3),
    ("被动", 4),
    ("兵种", 6),
    ("阵法", 7),
)

STAGE_ALIASES = (
    "stage",
    "stage_id",
    "stage_index",
    "phase",
    "step",
    "id",
)


def first_non_empty_text(row: dict[str, Any], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def is_safe_war_paper_name(value: Any) -> bool:
    """Return true when war_paper.name can be used as data_war_paper.<name>."""

    if not isinstance(value, str):
        return False
    text = value.strip()
    return bool(SAFE_WAR_PAPER_NAME_RE.fullmatch(text)) and not CJK_TEXT_RE.search(text)


def ascii_slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    parts = re.findall(r"[0-9A-Za-z]+", text)
    return "_".join(part for part in parts if part)


def fallback_war_paper_name(row: dict[str, Any]) -> str:
    skill_part = row.get("skill_id") or row.get("skill") or row.get("owner_skill_id")
    record_part = row.get("ID") or row.get("id") or row.get("record_id")
    if record_part not in (None, ""):
        base = f"war_report_{record_part}"
        return re.sub(r"[^0-9A-Za-z_]", "_", base)
    desc_text = first_non_empty_text(row, WAR_PAPER_DESC_ALIASES + WAR_PAPER_NAME_ALIASES)
    slug = ascii_slug(desc_text)
    if slug and not PLACEHOLDER_ONLY_SLUG_RE.fullmatch(slug):
        base = f"war_{skill_part}_{slug}" if skill_part not in (None, "") else f"war_{slug}"
    else:
        digest = hashlib.sha1(
            json.dumps(row, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:8]
        base = f"war_{skill_part}_{digest}" if skill_part not in (None, "") else f"war_report_{digest}"
    base = re.sub(r"[^0-9A-Za-z_]", "_", base)
    if not re.match(r"^[A-Za-z_]", base):
        base = f"war_{base}"
    return base


def cjk_base_name(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)|（[^）]*）", "", text)
    text = re.sub(r"\s+", "", text)
    return text


def add_war_name_hint(hints: dict[str, str], chinese_name: Any, ascii_name: Any) -> None:
    if not is_safe_war_paper_name(ascii_name):
        return
    base = cjk_base_name(chinese_name)
    if not base or not CJK_TEXT_RE.search(base):
        return
    safe_name = str(ascii_name).strip()
    hints.setdefault(base, safe_name)
    for suffix in BUFF_NAME_SUFFIXES:
        if base.endswith(suffix) and len(base) > len(suffix):
            hints.setdefault(base[: -len(suffix)], safe_name)


def build_war_paper_name_hints(rows: dict[str, Any]) -> dict[str, str]:
    hints: dict[str, str] = {}
    for sheet_name in ("buff", "skill_stage"):
        sheet_rows = rows.get(sheet_name, [])
        if not isinstance(sheet_rows, list):
            continue
        for row in sheet_rows:
            if not isinstance(row, dict):
                continue
            script_name = row.get("script")
            if not is_safe_war_paper_name(script_name):
                continue
            for field in ("name", "desc", "buff_desc", "de_desc"):
                add_war_name_hint(hints, row.get(field), script_name)
    for row in rows.get("skill", []) if isinstance(rows.get("skill"), list) else []:
        if not isinstance(row, dict):
            continue
        # If a model already emitted an ASCII helper field for the skill, reuse it.
        for ascii_field in ("script", "lua_name", "enum_name", "key_name"):
            ascii_name = row.get(ascii_field)
            if not is_safe_war_paper_name(ascii_name):
                continue
            for field in ("name", "desc", "de_desc"):
                add_war_name_hint(hints, row.get(field), ascii_name)
    return hints


def infer_war_action_suffix(row: dict[str, Any]) -> str:
    text = " ".join(
        str(row.get(field) or "")
        for field in WAR_PAPER_NAME_ALIASES + WAR_PAPER_DESC_ALIASES
    )
    for keyword, suffix in WAR_PAPER_ACTION_KEYWORDS:
        if keyword in text:
            return suffix
    return "report"


def infer_readable_war_paper_name(row: dict[str, Any], hints: dict[str, str] | None = None) -> str | None:
    if not hints:
        return None
    text = " ".join(
        str(row.get(field) or "")
        for field in WAR_PAPER_NAME_ALIASES + WAR_PAPER_DESC_ALIASES
    )
    best_match = ""
    best_ascii = ""
    for chinese_name, ascii_name in hints.items():
        if chinese_name and chinese_name in text and len(chinese_name) > len(best_match):
            best_match = chinese_name
            best_ascii = ascii_name
    if not best_ascii:
        return None
    return f"{best_ascii}_{infer_war_action_suffix(row)}"


def infer_skill_type(row: dict[str, Any]) -> int | None:
    for field in SKILL_TYPE_TEXT_FIELDS:
        value = row.get(field)
        if value is None:
            continue
        text = str(value)
        for keyword, skill_type in SKILL_TYPE_KEYWORDS:
            if keyword in text:
                return skill_type
    return None


def normalize_skill_type_field(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    raw_value = normalized.get("skill_type")
    try:
        skill_type = int(raw_value)
    except (TypeError, ValueError):
        skill_type = None
    if skill_type in VALID_SKILL_TYPES:
        normalized["skill_type"] = skill_type
        return normalized

    inferred = infer_skill_type(normalized)
    normalized["skill_type"] = inferred or DEFAULT_SKILL_TYPE
    if raw_value not in (None, ""):
        normalized["_skill_type_normalized_from"] = raw_value
    return normalized


def normalize_skill_display_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Keep skill desc/de_desc populated before formal Excel writeback."""

    normalized = normalize_skill_type_field(row)
    desc = first_non_empty_text(normalized, SKILL_DESC_ALIASES)
    de_desc = first_non_empty_text(normalized, SKILL_DE_DESC_ALIASES)
    fallback_text = first_non_empty_text(
        normalized,
        (
            "name",
            "skill_name",
            "title",
            "remark",
            "beizhu",
            "beizhu2",
        ),
    )
    if desc and not str(normalized.get("desc") or "").strip():
        normalized["desc"] = desc
    if de_desc and not str(normalized.get("de_desc") or "").strip():
        normalized["de_desc"] = de_desc
    if not str(normalized.get("desc") or "").strip() and str(normalized.get("de_desc") or "").strip():
        normalized["desc"] = normalized["de_desc"]
    if not str(normalized.get("de_desc") or "").strip() and str(normalized.get("desc") or "").strip():
        normalized["de_desc"] = normalized["desc"]
    if fallback_text and not str(normalized.get("desc") or "").strip():
        normalized["desc"] = fallback_text
    if fallback_text and not str(normalized.get("de_desc") or "").strip():
        normalized["de_desc"] = str(normalized.get("desc") or fallback_text)
    return normalized


def parse_stage_from_key(row: dict[str, Any]) -> int | None:
    key = str(row.get("key") or "").strip()
    parts = key.split("_")
    if len(parts) >= 3:
        try:
            stage = int(parts[1])
        except ValueError:
            return None
        if stage > 0:
            return stage
    return None


def normalize_skill_stage_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize skill_stage phase id and prevent accidental stage=0 writes."""

    normalized = dict(row)
    stage = None
    for field in STAGE_ALIASES:
        value = normalized.get(field)
        if value in (None, ""):
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            stage = parsed
            break
    if stage is None:
        stage = parse_stage_from_key(normalized)
    if stage is None:
        stage = 1
    normalized["stage"] = stage
    return normalized


def normalize_war_paper_display_fields(
    row: dict[str, Any],
    name_hints: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Ensure custom war-report rows use ASCII enum names and visible text in desc1."""

    normalized = dict(row)
    raw_name = first_non_empty_text(normalized, WAR_PAPER_NAME_ALIASES)

    if not str(normalized.get("desc1") or "").strip():
        for field in WAR_PAPER_DESC_ALIASES:
            value = normalized.get(field)
            if isinstance(value, str) and value.strip():
                normalized["desc1"] = value
                break
        if (
            not str(normalized.get("desc1") or "").strip()
            and isinstance(raw_name, str)
            and CJK_TEXT_RE.search(raw_name)
        ):
            normalized["desc1"] = raw_name

    if is_safe_war_paper_name(normalized.get("name")):
        return normalized
    for field in WAR_PAPER_NAME_ALIASES:
        value = normalized.get(field)
        if is_safe_war_paper_name(value):
            normalized["name"] = str(value).strip()
            return normalized
    readable_name = infer_readable_war_paper_name(normalized, name_hints)
    if readable_name and is_safe_war_paper_name(readable_name):
        if raw_name:
            normalized["_war_paper_name_normalized_from"] = raw_name
        normalized["name"] = readable_name
        return normalized
    if raw_name:
        normalized["_war_paper_name_normalized_from"] = raw_name
    normalized["name"] = fallback_war_paper_name(normalized)
    return normalized


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
    war_paper_name_hints = build_war_paper_name_hints(rows)
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
            if sheet_name == "skill":
                normalized_row = normalize_skill_display_fields(normalized_row)
            elif sheet_name == "skill_stage":
                normalized_row = normalize_skill_stage_fields(normalized_row)
            elif sheet_name == "war_paper":
                normalized_row = normalize_war_paper_display_fields(normalized_row, war_paper_name_hints)
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
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    comment_lines = []
    chinese_comment_lines = []
    chinese_block_comment_lines = []
    logic_lines = []
    in_block_comment = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if in_block_comment:
            comment_lines.append(stripped)
            if re.search(r"[\u4e00-\u9fff]", stripped):
                chinese_comment_lines.append(stripped)
                chinese_block_comment_lines.append(stripped)
            if "]]" in stripped:
                in_block_comment = False
            continue
        if stripped.startswith("--[["):
            in_block_comment = "]]" not in stripped
            comment_lines.append(stripped)
            if re.search(r"[\u4e00-\u9fff]", stripped):
                chinese_comment_lines.append(stripped)
                chinese_block_comment_lines.append(stripped)
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

    inline_chinese_comments = []
    in_block_comment = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("--[["):
            in_block_comment = "]]" not in stripped
            continue
        if in_block_comment:
            if "]]" in stripped:
                in_block_comment = False
            continue
        if re.match(r"\s+--.*[\u4e00-\u9fff]", line):
            inline_chinese_comments.append(line)
    min_inline_comments = max(6, min(24, len(logic_lines) // 12))
    if len(inline_chinese_comments) < min_inline_comments:
        errors.append(
            f"{path.name} 函数内部关键逻辑注释不足：当前 {len(inline_chinese_comments)} 行，至少需要 {min_inline_comments} 行；关键 if/return、层数变化、缓存读写、监听注册、战报清理和伤害改写处需要就地中文注释"
        )

    required_keywords = {
        ("参数",): "缺少参数含义说明",
        ("事件", "触发"): "缺少事件/触发时机说明",
        ("状态",): "缺少状态读写说明",
        ("异常", "短路", "保护"): "缺少异常/短路保护说明",
        ("战报",): "缺少战报插入说明",
    }
    comment_text = "\n".join(chinese_comment_lines)
    for keywords, message in required_keywords.items():
        if not any(keyword in comment_text for keyword in keywords):
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
