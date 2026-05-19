from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from skill_writer_app.services.process_command import normalize_windows_script_command, windows_subprocess_kwargs


@dataclass
class CheckItem:
    name: str
    ok: bool
    detail: str


class EnvironmentCheckService:
    def _is_current_app_executable(self, executable: str) -> bool:
        if not getattr(sys, "frozen", False):
            return False
        try:
            return Path(executable).resolve() == Path(sys.executable).resolve()
        except Exception:
            return False

    def check_command(self, label: str, command: str, version_args: list[str] | None = None) -> CheckItem:
        command = command.strip()
        resolved = ""
        if command:
            path = Path(command).expanduser()
            if path.exists():
                resolved = str(path.resolve())
            else:
                resolved = shutil.which(command) or ""
        if not resolved:
            resolved = shutil.which(command or label.lower()) or ""
        if not resolved:
            return CheckItem(label, False, "未找到可执行文件")
        if self._is_current_app_executable(resolved):
            return CheckItem(label, False, "已拦截：不能把 SkillWriterDesktop.exe 当作外部 CLI 执行")
        args = normalize_windows_script_command([resolved, *(version_args or ["--version"])])
        try:
            proc = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=8,
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
                **windows_subprocess_kwargs(),
            )
            output = proc.stdout.decode("utf-8", errors="replace").strip().splitlines()
            detail = output[0] if output else resolved
            return CheckItem(label, proc.returncode == 0, detail)
        except Exception as exc:  # noqa: BLE001
            return CheckItem(label, False, f"{resolved} | {exc}")

    def check_path(self, label: str, value: str, *, must_be_dir: bool = False, must_be_file: bool = False) -> CheckItem:
        if not value.strip():
            return CheckItem(label, False, "未配置")
        path = Path(value).expanduser()
        if must_be_dir and not path.is_dir():
            return CheckItem(label, False, f"目录不存在: {path}")
        if must_be_file and not path.is_file():
            return CheckItem(label, False, f"文件不存在: {path}")
        if not path.exists():
            return CheckItem(label, False, f"路径不存在: {path}")
        return CheckItem(label, True, str(path))

    def check_write_access(self, label: str, directory: str) -> CheckItem:
        path = Path(directory).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".skill_writer_write_probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return CheckItem(label, True, str(path))
        except Exception as exc:  # noqa: BLE001
            return CheckItem(label, False, str(exc))

    def check_python(self, executable: str) -> CheckItem:
        command = executable.strip()
        if not command:
            command = shutil.which("python") or shutil.which("py") or ""
        if not command:
            return CheckItem("Python", False, "未找到 python；请在工具里配置本机 Python 路径")
        return self.check_command("Python", command, ["--version"])

    def render(self, items: list[CheckItem]) -> str:
        lines = []
        for item in items:
            mark = "OK" if item.ok else "FAIL"
            lines.append(f"[{mark}] {item.name}: {item.detail}")
        failed = sum(1 for item in items if not item.ok)
        lines.insert(0, f"环境体检：{len(items) - failed}/{len(items)} 项通过")
        return "\n".join(lines)
