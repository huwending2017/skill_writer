from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Sequence


CODEX_COMMAND_NAMES: Sequence[str] = ("codex.exe", "codex.cmd", "codex.bat", "codex")


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


def discover_codex_candidates(preferred_path: str = "") -> list[str]:
    candidates: list[str] = []

    if preferred_path.strip():
        candidates.append(preferred_path.strip())

    for name in CODEX_COMMAND_NAMES:
        resolved = shutil.which(name)
        if resolved:
            candidates.append(resolved)

    if os.name == "nt":
        try:
            where_result = subprocess.run(
                ["where.exe", "codex"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                **_windows_subprocess_kwargs(),
            )
            if where_result.stdout:
                for line in where_result.stdout.splitlines():
                    if line.strip():
                        candidates.append(line.strip())
        except OSError:
            pass

    home = Path.home()
    known_patterns = [
        home / "AppData" / "Roaming" / "npm" / "codex.cmd",
        home / ".trae-cn" / "extensions",
        home / ".vscode" / "extensions",
        home / ".cursor" / "extensions",
        home / ".windsurf" / "extensions",
    ]
    for path in known_patterns:
        if path.is_file():
            candidates.append(str(path))
            continue
        if path.is_dir():
            for exe in sorted(path.glob("openai.chatgpt-*/bin/windows-x86_64/codex.exe"), reverse=True):
                candidates.append(str(exe))
            for exe in sorted(path.glob("**/bin/windows-x86_64/codex.exe"), reverse=True):
                candidates.append(str(exe))

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = _normalize_candidate(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(candidate)
    return deduped


def rank_codex_candidates(candidates: Sequence[str]) -> list[str]:
    return sorted(
        candidates,
        key=lambda item: (
            0 if item.lower().endswith(".exe") else 1,
            item.lower(),
        ),
    )


def resolve_codex_executable(preferred_path: str = "") -> str:
    ranked = rank_codex_candidates(discover_codex_candidates(preferred_path))
    for candidate in ranked:
        if Path(candidate).exists():
            return str(Path(candidate))

    attempted = "\n".join(ranked) if ranked else "无候选路径"
    raise FileNotFoundError(
        "未找到可用的 Codex CLI。请在桌面工具里手动填写 Codex 可执行文件路径。\n"
        f"已尝试的候选路径:\n{attempted}"
    )


def npm_available() -> bool:
    return shutil.which("npm") is not None


def install_codex_cli() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["npm", "install", "-g", "@openai/codex"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **_windows_subprocess_kwargs(),
    )


def ensure_codex_cli(preferred_path: str = "", install_if_missing: bool = False) -> str:
    try:
        return resolve_codex_executable(preferred_path)
    except FileNotFoundError:
        if not install_if_missing:
            raise

    if not npm_available():
        raise FileNotFoundError("Codex CLI not found and npm is unavailable.")

    result = install_codex_cli()
    if result.returncode != 0:
        detail = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
        raise RuntimeError(f"Failed to install @openai/codex.\n{detail.strip()}".rstrip())

    return resolve_codex_executable(preferred_path)
