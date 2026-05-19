from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path
from queue import Queue
from typing import Callable, List

from skill_writer_app.services.text_decode import decode_process_output


class ExcelWritebackService:
    def __init__(self, script_path: str) -> None:
        self.script_path = script_path
        self.process: subprocess.Popen[bytes] | None = None
        self.last_error_message: str = ""
        self.last_summary_lines: list[str] = []
        self.last_verify_lines: list[str] = []

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop_running(self) -> bool:
        if not self.is_running():
            return False
        assert self.process is not None
        try:
            self.process.terminate()
            self.process.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                self.process.kill()
            except Exception:  # noqa: BLE001
                return False
        finally:
            self.process = None
        return True

    def _windows_subprocess_kwargs(self) -> dict:
        if os.name != "nt":
            return {}

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {
            "creationflags": subprocess.CREATE_NO_WINDOW,
            "startupinfo": startupinfo,
        }

    def _subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("PYTHONPYCACHEPREFIX", None)
        return env

    def resolve_python_executable(self, executable_path: str = "") -> str:
        candidate = executable_path.strip()
        if candidate:
            path = Path(candidate).expanduser()
            if path.exists():
                return str(path.resolve())
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
            raise FileNotFoundError(f"python executable not found: {candidate}")

        current = Path(sys.executable)
        if current.exists() and current.name.lower().startswith("python"):
            return str(current.resolve())

        for name in ("python", "python3"):
            resolved = shutil.which(name)
            if resolved:
                return resolved

        raise FileNotFoundError("Python executable not found. Please configure a local Python path.")

    def run_writeback(
        self,
        payload_path: str,
        skill_excel_path: str,
        war_excel_path: str,
        backup_dir: str,
        copy_dir: str,
        dedupe_existing: bool,
        dry_run: bool,
        write_copy: bool,
        python_executable: str,
        log_queue: Queue[str],
        on_complete: Callable[[int], None],
    ) -> None:
        self.last_error_message = ""
        self.last_summary_lines = []
        self.last_verify_lines = []
        output_tail: deque[str] = deque(maxlen=40)
        script_file = Path(self.script_path).expanduser()
        if not script_file.exists():
            raise FileNotFoundError(f"writeback script not found: {script_file}")
        resolved_python = self.resolve_python_executable(python_executable)
        command: List[str] = [
            resolved_python,
            str(script_file),
            "--payload",
            payload_path,
            "--skill-xlsx",
            skill_excel_path,
            "--war-xlsx",
            war_excel_path,
        ]

        if backup_dir and not write_copy:
            Path(backup_dir).mkdir(parents=True, exist_ok=True)
            command.extend(["--backup-dir", backup_dir])
        if copy_dir and write_copy:
            Path(copy_dir).mkdir(parents=True, exist_ok=True)
            command.extend(["--copy-to", copy_dir])
        if dedupe_existing:
            command.append("--dedupe-existing")
        if dry_run:
            command.append("--dry-run")

        def worker() -> None:
            return_code = -1
            try:
                log_queue.put("[writeback-python] " + resolved_python)
                log_queue.put("[writeback-cmd] " + subprocess.list2cmdline(command))
                self.process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=0,
                    env=self._subprocess_env(),
                    **self._windows_subprocess_kwargs(),
                )
                assert self.process.stdout is not None
                for line in self.process.stdout:
                    clean = decode_process_output(line).rstrip("\r\n")
                    if clean.startswith("[summary]"):
                        self.last_summary_lines.append(clean)
                    elif clean.startswith("[verify"):
                        self.last_verify_lines.append(clean)
                    output_tail.append(clean)
                    log_queue.put(clean)
                return_code = self.process.wait()
                if return_code != 0 and output_tail:
                    self.last_error_message = "\n".join(output_tail)
            except Exception as exc:  # noqa: BLE001
                self.last_error_message = str(exc)
                log_queue.put(f"[writeback-error] {exc}")
            finally:
                self.process = None
                on_complete(return_code)

        threading.Thread(target=worker, daemon=True).start()
