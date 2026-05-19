from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from queue import Queue
from typing import Callable, List, Sequence

from skill_writer_app.services.process_command import normalize_windows_script_command, windows_subprocess_kwargs
from skill_writer_app.services.text_decode import decode_process_output


class LocalScriptRunner:
    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None
        self.last_error_message: str = ""

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
        return windows_subprocess_kwargs()

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

        if not getattr(sys, "frozen", False):
            current = Path(sys.executable)
            if current.exists() and current.name.lower().startswith("python"):
                return str(current.resolve())

        for name in ("python", "python3"):
            resolved = shutil.which(name)
            if resolved:
                return resolved

        raise FileNotFoundError("Python executable not found. Please configure a local Python path.")

    def run_script(
        self,
        script_path: str,
        script_args: Sequence[str],
        python_executable: str,
        workdir: str,
        log_queue: Queue[str],
        on_complete: Callable[[int], None],
    ) -> None:
        if self.is_running():
            raise RuntimeError("当前已有本地脚本任务在执行")

        self.last_error_message = ""
        resolved_script = Path(script_path).expanduser().resolve()
        if not resolved_script.exists():
            raise FileNotFoundError(f"local script not found: {resolved_script}")

        resolved_python = self.resolve_python_executable(python_executable)
        command: List[str] = [resolved_python, str(resolved_script), *list(script_args)]

        def worker() -> None:
            return_code = -1
            try:
                log_queue.put("[local-python] " + resolved_python)
                log_queue.put("[local-script] " + str(resolved_script))
                run_command = normalize_windows_script_command(command)
                log_queue.put("[local-cmd] " + subprocess.list2cmdline(run_command))
                self.process = subprocess.Popen(
                    run_command,
                    cwd=workdir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=0,
                    env=self._subprocess_env(),
                    **self._windows_subprocess_kwargs(),
                )
                assert self.process.stdout is not None
                for line in self.process.stdout:
                    log_queue.put(decode_process_output(line).rstrip("\r\n"))
                return_code = self.process.wait()
            except Exception as exc:  # noqa: BLE001
                self.last_error_message = str(exc)
                log_queue.put(f"[local-script-error] {exc}")
            finally:
                self.process = None
                on_complete(return_code)

        threading.Thread(target=worker, daemon=True).start()
