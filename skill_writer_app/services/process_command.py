from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Sequence


def windows_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def normalize_windows_script_command(command: Sequence[str]) -> list[str]:
    args = list(command)
    if os.name != "nt" or not args:
        return args

    executable = resolve_windows_executable_shim(args[0])
    args[0] = executable
    suffix = Path(executable).suffix.lower()
    if suffix in {".cmd", ".bat"}:
        return ["cmd.exe", "/d", "/c", *args]
    if suffix == ".ps1":
        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            *args,
        ]
    return args


def resolve_windows_executable_shim(executable: str) -> str:
    if os.name != "nt":
        return executable
    path = Path(executable)
    if path.suffix:
        return executable
    candidates = []
    if path.parent and str(path.parent) not in {"", "."}:
        candidates.extend(path.with_suffix(suffix) for suffix in (".exe", ".cmd", ".bat", ".ps1"))
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        candidates.append(Path(str(path) + suffix))
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return executable


def windows_executable_rank(candidate: str) -> tuple[int, str]:
    suffix = Path(candidate).suffix.lower()
    priority = {
        ".exe": 0,
        ".cmd": 1,
        ".bat": 2,
        ".ps1": 3,
        "": 9,
    }.get(suffix, 8)
    return (priority, candidate.lower())
