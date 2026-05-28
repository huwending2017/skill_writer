from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from payload_text_repair import auto_repair_payload_text_fields
from skill_artifact_utils import (
    TaskContext,
    ensure_payload_rows,
    load_json,
    normalize_excel_config_payload,
    normalize_skill_display_fields,
    normalize_skill_stage_fields,
    normalize_war_paper_display_fields,
)


DEFAULT_MAX_LEVEL = 10
SHORT_MAX_LEVEL = 1


@dataclass
class CompileResult:
    task_dir: Path
    payload_path: Path
    temp_config_path: Path
    smoke_test_path: Path
    skill_keys: list[str]
    stage_keys: list[str]
    buff_keys: list[str]
    war_keys: list[str]


def derive_skill_key(row: dict[str, Any]) -> str:
    return f"{row['id']}_{row['skill_lv']}"


def derive_stage_key(row: dict[str, Any]) -> str:
    stage = row.get("stage", row.get("id"))
    return f"{row['skill_id']}_{stage}_{row['skill_level']}"


def derive_stage_legacy_key(row: dict[str, Any]) -> str:
    stage = row.get("stage", row.get("id"))
    return f"{row['skill_id']}_{row['skill_level']}_{stage}"


def derive_buff_key(row: dict[str, Any]) -> str:
    return f"{row['id']}_{row['level']}"


def derive_war_key(row: dict[str, Any]) -> str:
    if row.get("name"):
        return str(row["name"])
    return str(row.get("ID", row.get("id", "")))


def normalize_row(sheet_name: str, raw_row: dict[str, Any]) -> dict[str, Any]:
    row = dict(raw_row)
    if sheet_name == "skill":
        row = normalize_skill_display_fields(row)
        row["key"] = derive_skill_key(row)
    elif sheet_name == "skill_stage":
        row = normalize_skill_stage_fields(row)
        row["key"] = derive_stage_key(row)
        row["legacy_key"] = derive_stage_legacy_key(row)
    elif sheet_name == "buff":
        if "update_life" not in row and "opportunity" in row:
            row["update_life"] = row["opportunity"]
        row["key"] = derive_buff_key(row)
    elif sheet_name == "war_paper":
        if "record_id" in row and "ID" not in row:
            row["ID"] = row["record_id"]
        if "record_name" in row and "name" not in row:
            row["name"] = row["record_name"]
        if "id" in row and "ID" not in row:
            row["ID"] = row["id"]
        row = normalize_war_paper_display_fields(row)
    return row


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


MAX_LEVEL_FIELDS = ("max_lv", "max_level", "skill_max_lv", "skill_max_level", "level_max")
CATEGORY_FIELDS = ("skill_category", "category", "source_type", "skill_source", "skill_kind", "kind")


def _explicit_max_levels(rows: list[dict[str, Any]]) -> list[int]:
    levels: list[int] = []
    for row in rows:
        for field in MAX_LEVEL_FIELDS:
            if row.get(field) is None:
                continue
            level = _to_int(row.get(field), -1)
            if level >= 0:
                levels.append(level)
    return levels


def _category_default_max_level(rows: list[dict[str, Any]], default: int = DEFAULT_MAX_LEVEL) -> int:
    for row in rows:
        for field in CATEGORY_FIELDS:
            value = row.get(field)
            if not isinstance(value, str):
                continue
            if "兵书" in value or "装备" in value:
                return SHORT_MAX_LEVEL
            if "自带" in value:
                return DEFAULT_MAX_LEVEL
    return default


def _expand_skill_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        skill_id = _to_int(row.get("id"), -1)
        grouped.setdefault(skill_id, []).append(dict(row))

    expanded: list[dict[str, Any]] = []
    for skill_id in sorted(grouped):
        group = grouped[skill_id]
        template = max(group, key=lambda item: _to_int(item.get("skill_lv"), 0))
        explicit_max_levels = _explicit_max_levels(group)
        if explicit_max_levels:
            max_lv = max(explicit_max_levels)
        else:
            max_lv = max(
                _category_default_max_level(group),
                max(_to_int(item.get("skill_lv"), 0) for item in group),
            )
        by_level = {_to_int(item.get("skill_lv"), 0): dict(item) for item in group}
        for level in range(0, max_lv + 1):
            row = dict(by_level.get(level, template))
            row["id"] = skill_id
            row["skill_lv"] = level
            row["max_lv"] = max_lv
            expanded.append(normalize_row("skill", row))
    return expanded


def _expand_stage_rows(rows: list[dict[str, Any]], skill_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    skill_max_levels = {
        _to_int(row.get("id"), -1): _to_int(row.get("max_lv"), DEFAULT_MAX_LEVEL)
        for row in skill_rows
    }
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in rows:
        skill_id = _to_int(row.get("skill_id"), -1)
        normalized_row = normalize_skill_stage_fields(row)
        stage = _to_int(normalized_row.get("stage"), 1)
        grouped.setdefault((skill_id, stage), []).append(dict(row))

    expanded: list[dict[str, Any]] = []
    for (skill_id, stage) in sorted(grouped):
        group = grouped[(skill_id, stage)]
        template = max(group, key=lambda item: _to_int(item.get("skill_level"), 0))
        max_lv = skill_max_levels.get(
            skill_id,
            max(_to_int(item.get("skill_level"), DEFAULT_MAX_LEVEL) for item in group),
        )
        by_level = {_to_int(item.get("skill_level"), 0): dict(item) for item in group}
        for level in range(0, max_lv + 1):
            row = dict(by_level.get(level, template))
            row["skill_id"] = skill_id
            row["stage"] = stage
            row["skill_level"] = level
            expanded.append(normalize_row("skill_stage", row))
    return expanded


def _infer_buff_max_level(buff_id: int, group: list[dict[str, Any]], skill_rows: list[dict[str, Any]]) -> int:
    known_levels = [_to_int(item.get("level"), -1) for item in group]
    known_max = max([level for level in known_levels if level >= 0], default=-1)

    matching_skill_max: list[int] = []
    buff_id_text = str(buff_id)
    for skill_row in skill_rows:
        skill_id = _to_int(skill_row.get("id"), -1)
        if skill_id < 0:
            continue
        if buff_id_text.startswith(str(skill_id)):
            matching_skill_max.append(_to_int(skill_row.get("max_lv"), DEFAULT_MAX_LEVEL))

    if matching_skill_max:
        return max(matching_skill_max)

    explicit_max_levels = _explicit_max_levels(group)
    if explicit_max_levels:
        return max(explicit_max_levels)

    return max(known_max, _category_default_max_level(group))


def _expand_buff_rows(rows: list[dict[str, Any]], skill_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    skill_rows = skill_rows or []
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        buff_id = _to_int(row.get("id"), -1)
        grouped.setdefault(buff_id, []).append(dict(row))

    expanded: list[dict[str, Any]] = []
    for buff_id in sorted(grouped):
        group = grouped[buff_id]
        template = max(group, key=lambda item: _to_int(item.get("level"), 0))
        max_lv = _infer_buff_max_level(buff_id, group, skill_rows)
        by_level = {_to_int(item.get("level"), 0): dict(item) for item in group}
        for level in range(0, max_lv + 1):
            row = dict(by_level.get(level, template))
            row["id"] = buff_id
            row["level"] = level
            row["max_lv"] = max_lv
            expanded.append(normalize_row("buff", row))
    return expanded


RUNTIME_FLAT_LIST_FIELDS: dict[str, set[str]] = {
    "skill": {"fit_arms", "study_need", "special_param", "person", "inherit_hero"},
}

RUNTIME_GROUPED_LIST_FIELDS: dict[str, set[str]] = {
    "skill_stage": {"param"},
    "buff": {"param"},
}


def _coerce_excel_config_token(token: str) -> Any:
    text = token.strip()
    if text == "":
        return ""
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        if "." in text:
            number = float(text)
            return int(number) if number.is_integer() else number
        return int(text)
    except ValueError:
        return text


def _parse_flat_excel_config(value: str) -> list[Any]:
    stripped = value.strip()
    if not stripped:
        return []
    return [_coerce_excel_config_token(part) for part in stripped.split(",") if part.strip()]


def _parse_grouped_excel_config(value: str) -> list[list[Any]]:
    stripped = value.strip()
    if not stripped:
        return []
    groups: list[list[Any]] = []
    for group_text in stripped.split("|"):
        group_text = group_text.strip()
        if not group_text:
            continue
        groups.append([_coerce_excel_config_token(part) for part in group_text.split(",") if part.strip()])
    return groups


def coerce_runtime_row(sheet_name: str, raw_row: dict[str, Any]) -> dict[str, Any]:
    row = dict(raw_row)
    for field in RUNTIME_FLAT_LIST_FIELDS.get(sheet_name, set()):
        value = row.get(field)
        if isinstance(value, str):
            row[field] = _parse_flat_excel_config(value)
    for field in RUNTIME_GROUPED_LIST_FIELDS.get(sheet_name, set()):
        value = row.get(field)
        if isinstance(value, str):
            row[field] = _parse_grouped_excel_config(value)
    return row


def expand_payload_rows(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows", {})
    skill_rows = [normalize_row("skill", row) for row in rows.get("skill", [])]
    skill_rows = _expand_skill_rows(skill_rows)
    stage_rows = [normalize_row("skill_stage", row) for row in rows.get("skill_stage", [])]
    stage_rows = _expand_stage_rows(stage_rows, skill_rows)
    buff_rows = [normalize_row("buff", row) for row in rows.get("buff", [])]
    buff_rows = _expand_buff_rows(buff_rows, skill_rows)
    war_rows = [normalize_row("war_paper", row) for row in rows.get("war_paper", [])]

    expanded_payload = dict(payload)
    expanded_payload["rows"] = {
        "skill": skill_rows,
        "skill_stage": stage_rows,
        "buff": buff_rows,
        "war_paper": war_rows,
    }
    return expanded_payload


def to_lua(value: Any, indent: int = 0) -> str:
    pad = " " * indent
    next_pad = " " * (indent + 4)

    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    if isinstance(value, list):
        if not value:
            return "{}"
        items = [f"{next_pad}{to_lua(item, indent + 4)}" for item in value]
        return "{\n" + ",\n".join(items) + f"\n{pad}" + "}"
    if isinstance(value, dict):
        if not value:
            return "{}"
        chunks: list[str] = []
        for key, item in value.items():
            key_text = key if isinstance(key, str) and key.isidentifier() else f"[{to_lua(key)}]"
            chunks.append(f"{next_pad}{key_text} = {to_lua(item, indent + 4)}")
        return "{\n" + ",\n".join(chunks) + f"\n{pad}" + "}"
    raise TypeError(f"unsupported value type: {type(value)!r}")


def build_temp_config_text(ctx: TaskContext, payload: dict[str, Any]) -> tuple[str, list[str], list[str], list[str], list[str]]:
    rows = payload["rows"]
    normalized_skill = [coerce_runtime_row("skill", normalize_row("skill", row)) for row in rows.get("skill", [])]
    normalized_stage = [coerce_runtime_row("skill_stage", normalize_row("skill_stage", row)) for row in rows.get("skill_stage", [])]
    normalized_buff = [coerce_runtime_row("buff", normalize_row("buff", row)) for row in rows.get("buff", [])]
    normalized_war = [normalize_row("war_paper", row) for row in rows.get("war_paper", [])]

    skill_keys = [str(row["key"]) for row in normalized_skill]
    stage_keys = [str(row["key"]) for row in normalized_stage]
    buff_keys = [str(row["key"]) for row in normalized_buff]
    war_keys = [derive_war_key(row) for row in normalized_war]

    lines = [
        "local M = {}",
        "",
        "-- 这个文件由本地 payload 编译器自动生成。",
        "-- 作用：把 temp_excel_payload.json 中的临时 skill / stage / buff / war_paper 配置注入到 data_* 全局表。",
        "-- 说明：",
        "-- 1. 这里只做“临时注入”，不改正式 Excel 导表。",
        "-- 2. 如果后续 payload 更新，可再次执行“本地编译”覆盖本文件。",
        "-- 3. 如果技能需要更强的运行时断言，可额外保留或补写 test_runtime_validation.lua。",
        "",
        f"local PAYLOAD_SOURCE = {to_lua(str(ctx.payload_path))}",
        "",
        f"local TEMP_SKILL_ROWS = {to_lua(normalized_skill)}",
        "",
        f"local TEMP_STAGE_ROWS = {to_lua(normalized_stage)}",
        "",
        f"local TEMP_BUFF_ROWS = {to_lua(normalized_buff)}",
        "",
        f"local TEMP_WAR_ROWS = {to_lua(normalized_war)}",
        "",
        "local function inject_rows(target, rows, key_field, fallback_index)",
        "    for _, row in ipairs(rows) do",
        "        local key = row[key_field]",
        "        if key == nil and fallback_index and row[fallback_index] ~= nil then",
        "            key = row[fallback_index]",
        "        end",
        "        if key ~= nil then",
        "            target[tostring(key)] = row",
        "            local legacy_key = row.legacy_key",
        "            if legacy_key ~= nil and tostring(legacy_key) ~= tostring(key) then",
        "                target[tostring(legacy_key)] = row",
        "            end",
        "        end",
        "    end",
        "end",
        "",
        "function M.inject()",
        "    data_skill = data_skill or {}",
        "    data_skill_stage = data_skill_stage or {}",
        "    data_buff = data_buff or {}",
        "    data_war_paper = data_war_paper or {}",
        "",
        "    inject_rows(data_skill, TEMP_SKILL_ROWS, 'key', 'id')",
        "    inject_rows(data_skill_stage, TEMP_STAGE_ROWS, 'key', 'skill_id')",
        "    inject_rows(data_buff, TEMP_BUFF_ROWS, 'key', 'id')",
        "    inject_rows(data_war_paper, TEMP_WAR_ROWS, 'name', 'ID')",
        "end",
        "",
        "function M.rows()",
        "    return {",
        "        skill = TEMP_SKILL_ROWS,",
        "        stage = TEMP_STAGE_ROWS,",
        "        buff = TEMP_BUFF_ROWS,",
        "        war_paper = TEMP_WAR_ROWS,",
        "    }",
        "end",
        "",
        "function M.describe()",
        "    return {",
        f"        payload_source = {to_lua(str(ctx.payload_path))},",
        f"        task_dir = {to_lua(str(ctx.task_dir))},",
        f"        skill_keys = {to_lua(skill_keys)},",
        f"        stage_keys = {to_lua(stage_keys)},",
        f"        buff_keys = {to_lua(buff_keys)},",
        f"        war_keys = {to_lua(war_keys)},",
        "    }",
        "end",
        "",
        "return M",
        "",
    ]
    return "\n".join(lines), skill_keys, stage_keys, buff_keys, war_keys


def build_smoke_test_text(ctx: TaskContext, result: CompileResult) -> str:
    temp_config_rel = os.path.relpath(
        result.temp_config_path,
        result.smoke_test_path.parent,
    ).replace("\\", "/")
    lines = [
        "package.path = package.path",
        '    .. ";./?.lua"',
        '    .. ";./service/?.lua"',
        '    .. ";./service/?/init.lua"',
        '    .. ";./service/?/?.lua"',
        '    .. ";./xgame_server/?.lua"',
        '    .. ";./xgame_server/service/?.lua"',
        '    .. ";./xgame_server/service/?/init.lua"',
        '    .. ";./xgame_server/service/?/?.lua"',
        '    .. ";./xgame_server/service/?/?/?.lua"',
        "",
        "local function assert_equal(actual, expected, message)",
        "    if actual ~= expected then",
        '        error(string.format("%s expected=%s actual=%s", message, tostring(expected), tostring(actual)))',
        "    end",
        "end",
        "",
        "local function assert_true(value, message)",
        "    if not value then",
        "        error(message)",
        "    end",
        "end",
        "",
        "-- 这个脚本由本地 payload 编译器自动生成。",
        "-- 它只做注入层 smoke test，不验证完整战斗运行时行为。",
        "-- 如果目录中存在 test_runtime_validation.lua，本地测试入口会优先执行那份更强的验证脚本。",
        "",
        "data_skill = {}",
        "data_skill_stage = {}",
        "data_buff = {}",
        "data_war_paper = {}",
        "",
        f"local config = dofile({to_lua(temp_config_rel)})",
        "config.inject()",
        "local meta = config.describe()",
        "",
        f"assert_equal(meta.payload_source, {to_lua(str(result.payload_path))}, 'payload source')",
        f"assert_equal(meta.task_dir, {to_lua(str(result.task_dir))}, 'task dir')",
    ]

    for key in result.skill_keys:
        lines.append(f"assert_true(type(data_skill[{to_lua(key)}]) == 'table', 'skill row injected: {key}')")
    for key in result.stage_keys:
        lines.append(f"assert_true(type(data_skill_stage[{to_lua(key)}]) == 'table', 'stage row injected: {key}')")
    for key in result.buff_keys:
        lines.append(f"assert_true(type(data_buff[{to_lua(key)}]) == 'table', 'buff row injected: {key}')")
    for key in result.war_keys:
        lines.append(f"assert_true(data_war_paper[{to_lua(key)}] ~= nil, 'war row injected: {key}')")

    lines.extend(
        [
            "",
            "print('payload_compiled_smoke_test passed')",
            "",
        ]
    )
    return "\n".join(lines)


def compile_payload_to_artifacts(ctx: TaskContext) -> CompileResult:
    if ctx.payload_path is None or not ctx.payload_path.exists():
        raise FileNotFoundError("temp_excel_payload.json not found")

    payload = ensure_payload_rows(load_json(ctx.payload_path))
    if "rows" not in payload or not isinstance(payload["rows"], dict):
        raise ValueError("payload must contain rows object")
    payload = normalize_excel_config_payload(payload)
    payload = expand_payload_rows(payload)
    payload, repair_notes = auto_repair_payload_text_fields(payload, ctx.task_dir)
    for item in repair_notes:
        print(f"[compile-repair] {item}")
    ctx.payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    temp_config_text, skill_keys, stage_keys, buff_keys, war_keys = build_temp_config_text(ctx, payload)
    temp_config_path = ctx.task_dir / "config" / "temp_skill_config.lua"
    temp_config_path.parent.mkdir(parents=True, exist_ok=True)
    temp_config_path.write_text(temp_config_text, encoding="utf-8")

    result = CompileResult(
        task_dir=ctx.task_dir,
        payload_path=ctx.payload_path,
        temp_config_path=temp_config_path,
        smoke_test_path=ctx.task_dir / "tests" / "test_skill_temp.lua",
        skill_keys=skill_keys,
        stage_keys=stage_keys,
        buff_keys=buff_keys,
        war_keys=war_keys,
    )
    smoke_test_text = build_smoke_test_text(ctx, result)
    result.smoke_test_path.parent.mkdir(parents=True, exist_ok=True)
    result.smoke_test_path.write_text(smoke_test_text, encoding="utf-8")
    return result
