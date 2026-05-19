from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from skill_writer_app.services.process_command import resolve_windows_executable_shim, windows_executable_rank


CLAUDE_COMMAND_NAMES: Sequence[str] = ("claude.exe", "claude.cmd", "claude.bat", "claude")


def _windows_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def _normalize_candidate(candidate: str) -> str:
    return os.path.normcase(os.path.normpath(candidate))


def discover_claude_candidates(preferred_path: str = "") -> list[str]:
    candidates: list[str] = []
    if preferred_path.strip():
        candidates.append(preferred_path.strip())

    for name in CLAUDE_COMMAND_NAMES:
        resolved = shutil.which(name)
        if resolved:
            candidates.append(resolved)

    if os.name == "nt":
        try:
            where_result = subprocess.run(
                ["where.exe", "claude"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                **_windows_subprocess_kwargs(),
            )
            if where_result.stdout:
                candidates.extend(line.strip() for line in where_result.stdout.splitlines() if line.strip())
        except OSError:
            pass

    home = Path.home()
    for candidate in (
        home / "AppData" / "Roaming" / "npm" / "claude.cmd",
        home / "AppData" / "Roaming" / "npm" / "claude.ps1",
    ):
        if candidate.exists():
            candidates.append(str(candidate))

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = _normalize_candidate(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(candidate)
    return deduped


def resolve_claude_executable(preferred_path: str = "") -> str:
    for candidate in sorted(discover_claude_candidates(preferred_path), key=windows_executable_rank):
        resolved = resolve_windows_executable_shim(candidate)
        if Path(resolved).exists():
            return str(Path(resolved))

    raise FileNotFoundError(
        "未找到可用的 Claude Code CLI。请先安装 @anthropic-ai/claude-code，"
        "或在桌面工具里手动填写 Claude CLI 可执行文件路径。"
    )
