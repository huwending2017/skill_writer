#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys

from payload_compiler import compile_payload_to_artifacts
from skill_artifact_utils import resolve_task_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile temp skill Lua artifacts from temp_excel_payload.json.")
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
    result = compile_payload_to_artifacts(ctx)
    print("[compile] task_dir:", result.task_dir)
    print("[compile] payload:", result.payload_path)
    print("[compile] temp_config:", result.temp_config_path)
    print("[compile] smoke_test:", result.smoke_test_path)
    print(
        "[compile] rows:",
        f"skill={len(result.skill_keys)}",
        f"stage={len(result.stage_keys)}",
        f"buff={len(result.buff_keys)}",
        f"war_paper={len(result.war_keys)}",
    )
    print("[compile] local payload compilation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
