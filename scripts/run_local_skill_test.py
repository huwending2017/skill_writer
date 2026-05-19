#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from lupa import LuaRuntime

from payload_compiler import compile_payload_to_artifacts
from skill_artifact_utils import load_json, resolve_task_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run generated Lua runtime validation locally without a model.")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--battle-root", default="")
    parser.add_argument("--task-dir", default="")
    parser.add_argument("--payload", default="")
    return parser.parse_args()


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
    if not temp_config_path.exists() or not smoke_test_path.exists():
        result = compile_payload_to_artifacts(ctx)
        smoke_test_path = result.smoke_test_path
        temp_config_path = result.temp_config_path
        print("[test] auto_compiled:", temp_config_path)
        print("[test] auto_compiled_smoke:", smoke_test_path)

    script_path = ctx.runtime_test_path
    if script_path is None:
        if not smoke_test_path.exists():
            print("[test-error] 缺少 test_runtime_validation.lua，且本地 smoke test 也不存在。")
            return 1
        script_path = smoke_test_path
        print("[test] runtime_test missing, fallback to smoke test:", script_path)
    else:
        print("[test] runtime_test:", script_path)

    os.chdir(ctx.workspace_root)
    lua = LuaRuntime(unpack_returned_tuples=True)
    script_text = script_path.read_text(encoding="utf-8")
    lua.execute(script_text)

    regression_paths = sorted(
        path
        for pattern in ("regression_*.lua", "mechanism_*.lua")
        for path in (ctx.task_dir / "tests").glob(pattern)
        if path.is_file() and path.resolve() != Path(script_path).resolve()
    )
    if regression_paths:
        print("[test] regression files:", len(regression_paths))
    for regression_path in regression_paths:
        print("[test] regression:", regression_path)
        lua.execute(regression_path.read_text(encoding="utf-8"))
    print("[test] local runtime validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
