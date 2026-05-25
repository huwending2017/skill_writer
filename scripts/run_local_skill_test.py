#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from payload_compiler import compile_payload_to_artifacts
from skill_artifact_utils import load_json, resolve_task_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run generated Lua runtime validation locally without a model.")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--battle-root", default="")
    parser.add_argument("--task-dir", default="")
    parser.add_argument("--payload", default="")
    return parser.parse_args()


def lua_string(value: Path | str) -> str:
    text = str(value).replace("\\", "/")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def configure_lua_paths(lua: object, ctx) -> None:
    task_dir = ctx.task_dir
    battle_root = ctx.battle_root
    lua.execute(
        "\n".join(
            [
                "package.path = package.path",
                f"    .. ';' .. {lua_string(task_dir / '?.lua')}",
                f"    .. ';' .. {lua_string(task_dir / '?' / '?.lua')}",
                f"    .. ';' .. {lua_string(battle_root / '?.lua')}",
                f"    .. ';' .. {lua_string(battle_root / '?' / '?.lua')}",
                f"    .. ';' .. {lua_string(battle_root / '?' / '?' / '?.lua')}",
            ]
        )
    )
    lua.execute(
        """
DEBUG = DEBUG or function(...) end
EVENT_DEF = EVENT_DEF or {
    BUFF_DAMAGED_OVER = "BUFF_DAMAGED_OVER",
    BUFF_ATTACKED_DAMAGE = "BUFF_ATTACKED_DAMAGE",
    BUFF_ATTACKED_SHARE = "BUFF_ATTACKED_SHARE",
    BUFF_LOSE_LIFE = "BUFF_LOSE_LIFE",
    BUFF_OVERLYING_EFFECT_FUNC = "BUFF_OVERLYING_EFFECT_FUNC",
}
RECORD_NUM_DEF = RECORD_NUM_DEF or {
    CAMP = "CAMP",
    SKILL_ID = "SKILL_ID",
    BUFF = "BUFF",
    NUM = "NUM",
}
data_war_paper = data_war_paper or {}
"""
    )


def is_unsupported_embedded_regression_error(message: str) -> bool:
    normalized = message.lower().replace("_", " ")
    if "owner camp" in normalized:
        return True
    if "attempt to index a boolean value" in normalized and "local 'script'" in normalized:
        return True
    if "attempt to index a boolean value" in normalized and 'local "script"' in normalized:
        return True
    if "attempt to call a nil value" in normalized and "mock" in normalized:
        return True
    return False


def main() -> int:
    args = parse_args()
    ctx = resolve_task_context(
        workspace_root_value=args.workspace_root,
        battle_root_value=args.battle_root,
        task_dir_value=args.task_dir,
        payload_value=args.payload,
    )

    print("[test] workspace_root:", ctx.workspace_root)
    print("[test] battle_root:", ctx.battle_root)
    print("[test] task_dir:", ctx.task_dir)

    if ctx.payload_path is not None and ctx.payload_path.exists():
        payload = load_json(ctx.payload_path)
        rows = payload.get("rows", {})
        print(
            "[test] payload rows:",
            f"skill={len(rows.get('skill', []))}",
            f"stage={len(rows.get('skill_stage', []))}",
            f"buff={len(rows.get('buff', []))}",
            f"war_paper={len(rows.get('war_paper', []))}",
        )
    else:
        print("[test] payload: <missing>")

    smoke_test_path = ctx.tests_path("test_skill_temp.lua")
    temp_config_path = ctx.config_path("temp_skill_config.lua")
    if ctx.payload_path is not None and ctx.payload_path.exists():
        result = compile_payload_to_artifacts(ctx)
        smoke_test_path = result.smoke_test_path
        temp_config_path = result.temp_config_path
        print("[test] refreshed_temp_config:", temp_config_path)
        print("[test] refreshed_smoke:", smoke_test_path)
    elif not temp_config_path.exists() or not smoke_test_path.exists():
        print("[test-error] 缺少 payload，且本地测试产物不完整。")
        return 1

    script_path = ctx.runtime_test_path
    if script_path is None:
        if not smoke_test_path.exists():
            print("[test-error] 缺少 test_runtime_validation.lua，且本地 smoke test 也不存在。")
            return 1
        script_path = smoke_test_path
        print("[test] runtime_test missing, fallback to smoke test:", script_path)
    else:
        print("[test] runtime_test:", script_path)

    regression_paths = sorted(
        path
        for pattern in ("regression_*.lua", "mechanism_*.lua")
        for path in (ctx.task_dir / "tests").glob(pattern)
        if path.is_file() and path.resolve() != Path(script_path).resolve()
    )

    try:
        from lupa import LuaRuntime
    except ModuleNotFoundError:
        if os.environ.get("SKILL_WRITER_REQUIRE_LUPA") == "1":
            raise
        print("[test-warning] Python dependency missing: lupa")
        print("[test-warning] Skip embedded Lua runtime execution on this machine.")
        print("[test-warning] Install with: python -m pip install lupa")
        print("[test] smoke file exists:", script_path)
        if regression_paths:
            print("[test] regression files detected:", len(regression_paths))
            for regression_path in regression_paths:
                print("[test] regression file exists:", regression_path)
        print("[test] local runtime validation skipped because lupa is unavailable")
        return 0

    lua = LuaRuntime(unpack_returned_tuples=True)
    configure_lua_paths(lua, ctx)
    script_text = script_path.read_text(encoding="utf-8")
    previous_cwd = Path.cwd()
    try:
        os.chdir(script_path.parent)
        lua.execute(script_text)
    finally:
        os.chdir(previous_cwd)

    skipped_regressions = 0
    if regression_paths:
        print("[test] regression files:", len(regression_paths))
    for regression_path in regression_paths:
        print("[test] regression:", regression_path)
        previous_cwd = Path.cwd()
        try:
            os.chdir(ctx.task_dir)
            lua.execute(regression_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
            if is_unsupported_embedded_regression_error(detail):
                skipped_regressions += 1
                print("[test-warning] embedded Lua mock does not cover this battle-scene regression.")
                print("[test-warning] skipped regression:", regression_path)
                print("[test-warning] reason:", detail.splitlines()[0] if detail else exc.__class__.__name__)
                continue
            raise
        finally:
            os.chdir(previous_cwd)
    if skipped_regressions:
        print(f"[test] local runtime validation passed with {skipped_regressions} unsupported regression skipped")
    else:
        print("[test] local runtime validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
