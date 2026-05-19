#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve or install Codex CLI for Skill Writer build/runtime.")
    parser.add_argument("--preferred-path", default="")
    parser.add_argument("--install-if-missing", action="store_true")
    return parser.parse_args()


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))

    from skill_writer_app.services.codex_locator import ensure_codex_cli

    args = parse_args()
    resolved = ensure_codex_cli(
        preferred_path=args.preferred_path,
        install_if_missing=args.install_if_missing,
    )
    print(resolved)
    return 0


if __name__ == "__main__":
    sys.exit(main())
