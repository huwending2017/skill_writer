#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from payload_compiler import expand_payload_rows
from payload_text_repair import auto_repair_payload_text_fields
from skill_artifact_utils import (
    IMPLEMENTATION_NAME,
    TEMP_CONFIG_NAME,
    VALID_SKILL_TYPES,
    audit_lua_chinese_comments,
    collect_task_lua_scripts,
    existing_action_paths,
    existing_buff_paths,
    find_invalid_excel_config_literals,
    find_suspicious_question_mark_fields,
    ensure_payload_rows,
    is_task_owned_lua_script,
    is_safe_war_paper_name,
    load_json,
    normalize_excel_config_payload,
    resolve_task_context,
)

FORBIDDEN_RUNTIME_REFERENCES = ("test_skill_temp", "temp_skill_workspace", "roll_skill_dice")
NON_PRODUCTION_LUA_NAMES = {"test_skill_temp.lua", "test_runtime_validation.lua", "temp_skill_config.lua"}
TEST_LUA_PREFIXES = ("test_", "regression_", "mechanism_")
PROTECTED_RUNTIME_RELATIVE_PATHS = (
    "module/object/actor.lua",
    "module/fight/skill.lua",
    "module/fight/buff.lua",
    "module/fight/action.lua",
    "module/fight/damage.lua",
    "module/scene/battle_scene.lua",
)


def is_blocking_comment_audit_error(message: str) -> bool:
    """Only block on comment-audit findings that indicate executable risk."""

    blocking_tokens = (
        "??",
        "debug_log",
        "extern.overlying",
    )
    return any(token in message for token in blocking_tokens)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit generated local battle skill artifacts without calling a model.")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--battle-root", default="")
    parser.add_argument("--task-dir", default="")
    parser.add_argument("--payload", default="")
    return parser.parse_args()


def _format_paths(paths: list[Path]) -> str:
    return ", ".join(str(path) for path in paths)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_protected_runtime_files(battle_root: Path, task_dir: Path) -> list[str]:
    state_path = task_dir / "task_state.json"
    if not state_path.exists():
        return []
    try:
        state = load_json(state_path)
    except (OSError, json.JSONDecodeError):
        return []
    baseline = state.get("protected_runtime_baseline")
    if not isinstance(baseline, dict) or not baseline:
        return []

    protected_paths = state.get("protected_runtime_paths")
    if not isinstance(protected_paths, list) or not protected_paths:
        protected_paths = list(PROTECTED_RUNTIME_RELATIVE_PATHS)

    errors: list[str] = []
    for relative_path in protected_paths:
        relative_text = str(relative_path).replace("\\", "/").strip("/")
        if not relative_text:
            continue
        expected_hash = baseline.get(relative_text) or baseline.get(str(relative_path))
        if not expected_hash:
            continue
        path = battle_root / Path(relative_text)
        if not path.exists() or not path.is_file():
            errors.append(f"protected runtime file missing after task started: {relative_text}")
            continue
        try:
            current_hash = sha256_file(path)
        except OSError as exc:
            errors.append(f"protected runtime file cannot be read: {relative_text} ({exc})")
            continue
        if current_hash != expected_hash:
            errors.append(
                f"禁止修改底层战斗框架文件: {relative_text}。续写/修复技能只能修改任务目录产物或用户明确点名的技能脚本。"
            )
    return errors


def is_generated_skill_script(path: Path) -> bool:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return False
    return "author: codex" in head.lower() or "debug_log(" in head


def should_check_script_comments(task_dir: Path, path: Path) -> bool:
    return is_task_owned_lua_script(task_dir, path) or is_generated_skill_script(path)


def audit_payload_rows(payload: dict[str, Any], battle_root: Path, task_dir: Path) -> tuple[list[str], list[str], set[Path]]:
    errors: list[str] = []
    warnings: list[str] = []
    comment_checked_paths: set[Path] = set()

    rows = payload.get("rows")
    if not isinstance(rows, dict):
        errors.append("payload.rows 缺失或类型错误")
        return errors, warnings, comment_checked_paths

    skill_rows = rows.get("skill", [])
    stage_rows = rows.get("skill_stage", [])
    buff_rows = rows.get("buff", [])
    war_rows = rows.get("war_paper", [])

    print(f"[audit] payload rows: skill={len(skill_rows)} stage={len(stage_rows)} buff={len(buff_rows)} war_paper={len(war_rows)}")

    buff_ids = {row.get("id") for row in buff_rows if isinstance(row, dict) and row.get("id") is not None}
    for index, row in enumerate(stage_rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"skill_stage[{index}] 不是对象")
            continue
        script_name = str(row.get("script", "")).strip()
        if not script_name:
            errors.append(f"skill_stage[{index}] 缺少 script")
            continue

        matched = existing_action_paths(battle_root, task_dir, script_name)
        if not matched:
            errors.append(f"skill_stage[{index}] action script 不存在: action_{script_name}.lua")
        else:
            print(f"[audit] stage[{index}] -> action_{script_name}.lua :: {_format_paths(matched)}")
            for path in matched:
                if should_check_script_comments(task_dir, path):
                    comment_checked_paths.add(path)

        params = row.get("param")
        if script_name == "add_buff" and isinstance(params, list):
            flattened = []
            for item in params:
                if isinstance(item, list):
                    flattened.extend(item)
                else:
                    flattened.append(item)
            for buff_id in flattened:
                if isinstance(buff_id, int) and buff_id not in buff_ids:
                    warnings.append(f"skill_stage[{index}] 引用了未在 payload.buff 中声明的 buff_id={buff_id}")

    for index, row in enumerate(buff_rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"buff[{index}] 不是对象")
            continue
        script_name = str(row.get("script", "")).strip()
        if not script_name:
            errors.append(f"buff[{index}] 缺少 script")
            continue
        matched = existing_buff_paths(battle_root, task_dir, script_name)
        if not matched:
            errors.append(f"buff[{index}] buff script 不存在: buff_{script_name}.lua")
        else:
            print(f"[audit] buff[{index}] -> buff_{script_name}.lua :: {_format_paths(matched)}")
            for path in matched:
                if should_check_script_comments(task_dir, path):
                    comment_checked_paths.add(path)

    if comment_checked_paths:
        for path in sorted(comment_checked_paths):
            comment_errors = audit_lua_chinese_comments(path)
            if comment_errors:
                for item in comment_errors:
                    if is_blocking_comment_audit_error(item):
                        errors.append(item)
                    else:
                        warnings.append(item)
            else:
                print(f"[audit] chinese_comments: ok :: {path}")

    return errors, warnings, comment_checked_paths


def audit_payload_shape(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rows = payload.get("rows", {})
    if not isinstance(rows, dict):
        return errors

    skill_levels: dict[int, set[int]] = {}
    skill_max: dict[int, int] = {}
    for row in rows.get("skill", []):
        if not isinstance(row, dict):
            continue
        skill_id = int(row.get("id", -1))
        level = int(row.get("skill_lv", -1))
        row_key = row.get("key") or f"{skill_id}_{level}"
        if not str(row.get("desc") or "").strip():
            errors.append(f"skill[{row_key}] 缺少 desc，正式 skill 表描述不能为空")
        if not str(row.get("de_desc") or "").strip():
            errors.append(f"skill[{row_key}] 缺少 de_desc，正式 skill 表详细描述不能为空")
        skill_type_value = row.get("skill_type")
        if skill_type_value not in (None, ""):
            try:
                skill_type = int(skill_type_value)
            except (TypeError, ValueError):
                errors.append(f"skill[{row_key}] skill_type 非数字: {skill_type_value}")
            else:
                if skill_type not in VALID_SKILL_TYPES:
                    errors.append(
                        f"skill[{row_key}] skill_type={skill_type} 不在当前正式表允许值 {sorted(VALID_SKILL_TYPES)} 中，禁止写入"
                    )
        skill_levels.setdefault(skill_id, set()).add(level)
        skill_max[skill_id] = max(skill_max.get(skill_id, -1), int(row.get("max_lv", level)))
        expected_key = f"{skill_id}_{level}"
        if str(row.get("key", expected_key)) != expected_key:
            errors.append(f"skill key 不符合规则: id={skill_id} level={level} key={row.get('key')}")

    for skill_id, max_lv in skill_max.items():
        expected = set(range(0, max_lv + 1))
        actual = skill_levels.get(skill_id, set())
        if actual != expected:
            errors.append(f"skill 等级不连续: id={skill_id} expected=0..{max_lv} actual={sorted(actual)}")

    stage_levels: dict[tuple[int, int], set[int]] = {}
    for row in rows.get("skill_stage", []):
        if not isinstance(row, dict):
            continue
        skill_id = int(row.get("skill_id", -1))
        stage = int(row.get("stage", row.get("id", -1)))
        level = int(row.get("skill_level", -1))
        if stage <= 0:
            errors.append(f"skill_stage 阶段 id 非法: skill_id={skill_id} level={level} stage={stage}")
        stage_levels.setdefault((skill_id, stage), set()).add(level)
        expected_key = f"{skill_id}_{stage}_{level}"
        if str(row.get("key", expected_key)) != expected_key:
            errors.append(f"skill_stage key 不符合规则: expected={expected_key} actual={row.get('key')}")
    for (skill_id, stage), levels in stage_levels.items():
        max_lv = skill_max.get(skill_id, max(levels))
        expected = set(range(0, max_lv + 1))
        if levels != expected:
            errors.append(
                f"skill_stage 等级不连续: skill_id={skill_id} stage={stage} expected=0..{max_lv} actual={sorted(levels)}"
            )

    buff_levels: dict[int, set[int]] = {}
    buff_max: dict[int, int] = {}
    for row in rows.get("buff", []):
        if not isinstance(row, dict):
            continue
        buff_id = int(row.get("id", -1))
        level = int(row.get("level", -1))
        buff_levels.setdefault(buff_id, set()).add(level)
        buff_max[buff_id] = max(buff_max.get(buff_id, -1), int(row.get("max_lv", level)))
        expected_key = f"{buff_id}_{level}"
        if str(row.get("key", expected_key)) != expected_key:
            errors.append(f"buff key 不符合规则: id={buff_id} level={level} key={row.get('key')}")
    for buff_id, max_lv in buff_max.items():
        expected = set(range(0, max_lv + 1))
        actual = buff_levels.get(buff_id, set())
        if actual != expected:
            errors.append(f"buff 等级不连续: id={buff_id} expected=0..{max_lv} actual={sorted(actual)}")

    errors.extend(audit_war_report_config_contract(rows))
    return errors


def audit_war_report_config_contract(rows: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    explicit_war_ids: set[int] = set()
    for index, row in enumerate(rows.get("war_paper", []), start=1):
        if not isinstance(row, dict):
            continue
        row_key = row.get("name") or row.get("ID") or row.get("id") or index
        name = str(row.get("name") or "").strip()
        if not name:
            errors.append(f"war_paper[{index}] 缺少 name；name 必须是英文枚举名，中文只能写 desc1")
        elif not is_safe_war_paper_name(name):
            errors.append(
                f"war_paper[{index}] name={name} 非法；禁止中文或空格，必须是 data_war_paper.<name> 可用的英文/数字/下划线枚举名"
            )
        if not str(row.get("desc1") or "").strip():
            errors.append(f"war_paper[{index}] key={row_key} 缺少 desc1；战报正文必须写入 desc1，不能只依赖空白字段")
        for field in ("ID", "id", "record_id"):
            value = row.get(field)
            if value in (None, ""):
                continue
            try:
                explicit_war_ids.add(int(value))
            except (TypeError, ValueError):
                continue

    if not explicit_war_ids:
        return errors

    for row in rows.get("buff", []):
        if not isinstance(row, dict):
            continue
        buff_key = row.get("key") or f"{row.get('id', '?')}_{row.get('level', '?')}"
        for field in ("param", "param1", "param2", "param3", "param4", "param5", "param6", "param7", "param8"):
            values = flatten_values(row.get(field))
            matched = sorted({value for value in values if value in explicit_war_ids})
            if matched:
                errors.append(
                    f"buff[{buff_key}] {field} 禁止直接引用战报ID {matched}；请在生产 Lua 中使用战报枚举/常量名插入战报"
                )
    return errors


def flatten_values(value: Any) -> list[int]:
    if isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, float) and value.is_integer():
        return [int(value)]
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return [int(text)]
        return []
    if isinstance(value, dict):
        result: list[int] = []
        for item in value.values():
            result.extend(flatten_values(item))
        return result
    if isinstance(value, (list, tuple)):
        result: list[int] = []
        for item in value:
            result.extend(flatten_values(item))
        return result
    return []


def audit_production_script_contract(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        if is_non_production_lua(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in FORBIDDEN_RUNTIME_REFERENCES:
            if marker in text:
                errors.append(f"{path.name} 生产脚本禁止依赖临时实现: {marker}")
    return errors


def is_non_production_lua(path: Path) -> bool:
    if path.name in NON_PRODUCTION_LUA_NAMES:
        return True
    if path.parent.name == "tests":
        return True
    return path.name.startswith(TEST_LUA_PREFIXES)


def audit_command_skill_notes(payload: dict[str, Any], implementation_path: Path) -> list[str]:
    rows = payload.get("rows", {})
    skill_rows = rows.get("skill", []) if isinstance(rows, dict) else []
    is_command_skill = any(
        isinstance(row, dict)
        and any("指挥" in str(row.get(field, "")) for field in ("skill_type", "type", "category", "skill_category", "name", "desc"))
        for row in skill_rows
    )
    if not is_command_skill:
        return []
    if not implementation_path.exists():
        return ["指挥技能缺少 IMPLEMENTATION.md，无法确认失效/恢复场景已分析"]
    text = implementation_path.read_text(encoding="utf-8", errors="replace")
    if "失效" not in text or "恢复" not in text:
        return ["指挥技能的 IMPLEMENTATION.md 必须说明失效与恢复场景"]
    return []


def audit_war_report_coverage_notes(payload: dict[str, Any], implementation_path: Path, lua_paths: list[Path]) -> list[str]:
    rows = payload.get("rows", {}) if isinstance(payload, dict) else {}
    war_rows = rows.get("war_paper", []) if isinstance(rows, dict) else []
    lua_text_parts: list[str] = []
    for path in lua_paths:
        if not path.exists() or path.suffix.lower() != ".lua":
            continue
        try:
            lua_text_parts.append(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    lua_text = "\n".join(lua_text_parts)
    has_report_mechanic = bool(war_rows) or any(
        token in lua_text
        for token in (
            "make_effect_records",
            "make_confuse_records",
            "insert_effect_list",
            "insert_record_effect",
            "insert_record_effect_list_last",
        )
    )
    if not has_report_mechanic:
        return []
    if not implementation_path.exists():
        return ["存在战报机制但缺少 IMPLEMENTATION.md，无法确认战报覆盖矩阵"]
    text = implementation_path.read_text(encoding="utf-8", errors="ignore")
    required_keywords = ("战报覆盖矩阵", "触发", "层数", "状态", "num_list")
    missing = [keyword for keyword in required_keywords if keyword not in text]
    if missing:
        return [f"IMPLEMENTATION.md 缺少战报覆盖矩阵关键项: {', '.join(missing)}"]
    return []


def main() -> int:
    args = parse_args()
    ctx = resolve_task_context(
        workspace_root_value=args.workspace_root,
        battle_root_value=args.battle_root,
        task_dir_value=args.task_dir,
        payload_value=args.payload,
    )

    print("[audit] workspace_root:", ctx.workspace_root)
    print("[audit] battle_root:", ctx.battle_root)
    print("[audit] task_dir:", ctx.task_dir)
    print("[audit] payload:", ctx.payload_path or "<missing>")
    print("[audit] runtime_test:", ctx.runtime_test_path or "<missing>")
    print("[audit] knowledge_index:", ctx.knowledge_index_path or "<missing>")

    implementation = ctx.docs_path(IMPLEMENTATION_NAME)
    temp_config = ctx.config_path(TEMP_CONFIG_NAME)
    task_lua_scripts = collect_task_lua_scripts(ctx.task_dir)

    if implementation.exists():
        print("[audit] implementation: ok")
    else:
        print("[audit] implementation: missing")

    if temp_config.exists():
        print("[audit] temp_skill_config: ok")
    else:
        print("[audit] temp_skill_config: missing")

    print("[audit] task lua files:", len(task_lua_scripts))
    for path in task_lua_scripts:
        print("[audit] lua:", path.name)

    errors: list[str] = []
    warnings: list[str] = []
    errors.extend(audit_protected_runtime_files(ctx.battle_root, ctx.task_dir))

    if ctx.payload_path is None or not ctx.payload_path.exists():
        errors.append("缺少 temp_excel_payload.json")
    else:
        payload = normalize_excel_config_payload(ensure_payload_rows(load_json(ctx.payload_path)))
        if isinstance(payload.get("rows"), dict):
            payload = expand_payload_rows(payload)
        payload, repair_notes = auto_repair_payload_text_fields(payload, ctx.task_dir)
        for item in repair_notes:
            print(f"[audit-repair] {item}")
        ctx.payload_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        suspicious_fields = find_suspicious_question_mark_fields(payload)
        if suspicious_fields:
            errors.append("payload 中存在疑似乱码问号字段，请先修复 temp_excel_payload.json 后再继续。")
            for item in suspicious_fields:
                errors.append(f"疑似乱码: {item}")
        invalid_config_literals = find_invalid_excel_config_literals(payload)
        if invalid_config_literals:
            errors.append(
                "payload contains JSON/Python literal syntax that cannot be written to formal Excel/Lua config. "
                "Use Excel config text instead; for example [\"ATK\",10000] must be ATK,10000."
            )
            for item in invalid_config_literals:
                errors.append(f"invalid excel config literal: {item}")
        payload_errors, payload_warnings, task_owned_paths = audit_payload_rows(payload, ctx.battle_root, ctx.task_dir)
        errors.extend(payload_errors)
        warnings.extend(payload_warnings)
        errors.extend(audit_payload_shape(payload))
        warnings.extend(audit_command_skill_notes(payload, implementation))
        report_paths = sorted(set(task_owned_paths).union(task_lua_scripts))
        warnings.extend(audit_war_report_coverage_notes(payload, implementation, report_paths))
        errors.extend(audit_production_script_contract(sorted(task_owned_paths)))

    new_mechanism_files = [
        path.name
        for path in task_lua_scripts
        if path.name not in {"test_skill_temp.lua", "test_runtime_validation.lua", "temp_skill_config.lua"}
        and (path.name.startswith("action_") or path.name.startswith("buff_"))
    ]
    if new_mechanism_files:
        print("[audit] new_mechanism_files:", ", ".join(new_mechanism_files))
    else:
        print("[audit] new_mechanism_files: none")
    errors.extend(audit_production_script_contract(task_lua_scripts))

    if warnings:
        for item in warnings:
            print("[audit-warning]", item)

    if errors:
        for item in errors:
            print("[audit-error]", item)
        return 1

    print("[audit] local artifact audit passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
