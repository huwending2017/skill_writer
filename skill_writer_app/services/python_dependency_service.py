from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from queue import Queue

from skill_writer_app.services.process_command import normalize_windows_script_command, windows_subprocess_kwargs
from skill_writer_app.services.text_decode import decode_process_output


@dataclass(frozen=True)
class PythonDependency:
    import_name: str
    install_spec: str
    required: bool = True


@dataclass
class DependencyInstallResult:
    ok: bool
    installed: list[str]
    missing: list[str]
    failed: list[str]
    optional_failed: list[str]

    def summary(self) -> str:
        parts: list[str] = []
        if self.installed:
            parts.append("installed=" + ",".join(self.installed))
        if self.failed:
            parts.append("failed=" + ",".join(self.failed))
        if self.optional_failed:
            parts.append("optional_failed=" + ",".join(self.optional_failed))
        if self.missing:
            parts.append("missing=" + ",".join(self.missing))
        return "; ".join(parts) if parts else "all satisfied"


RUNTIME_DEPENDENCIES: tuple[PythonDependency, ...] = (
    PythonDependency("openpyxl", "openpyxl>=3.1", required=True),
    PythonDependency("lupa", "lupa>=2.0", required=False),
)


def runtime_requirements_path(app_base_dir: Path) -> Path:
    candidates = [
        app_base_dir / "requirements-runtime.txt",
        app_base_dir / "_internal" / "requirements-runtime.txt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


class PythonDependencyService:
    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("PYTHONPYCACHEPREFIX", None)
        return env

    def has_module(self, python_executable: str, import_name: str) -> bool:
        command = [
            python_executable,
            "-c",
            f"import importlib.util, sys; sys.exit(0 if importlib.util.find_spec({import_name!r}) else 1)",
        ]
        proc = subprocess.run(
            normalize_windows_script_command(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=self._env(),
            **windows_subprocess_kwargs(),
        )
        return proc.returncode == 0

    def install_dependency(
        self,
        python_executable: str,
        dependency: PythonDependency,
        log_queue: Queue[str] | None = None,
    ) -> bool:
        if log_queue is not None:
            log_queue.put(f"[python-deps] installing {dependency.install_spec}")
        command = [python_executable, "-m", "pip", "install", "--upgrade", dependency.install_spec]
        proc = subprocess.Popen(
            normalize_windows_script_command(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            env=self._env(),
            **windows_subprocess_kwargs(),
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            if log_queue is not None:
                log_queue.put("[python-deps] " + decode_process_output(line).rstrip("\r\n"))
        return proc.wait() == 0

    def ensure_runtime_dependencies(
        self,
        python_executable: str,
        log_queue: Queue[str] | None = None,
        *,
        install_optional: bool = True,
        fail_on_required: bool = True,
    ) -> DependencyInstallResult:
        installed: list[str] = []
        missing: list[str] = []
        failed: list[str] = []
        optional_failed: list[str] = []

        for dependency in RUNTIME_DEPENDENCIES:
            if not dependency.required and not install_optional:
                continue
            if self.has_module(python_executable, dependency.import_name):
                continue
            missing.append(dependency.import_name)
            ok = self.install_dependency(python_executable, dependency, log_queue)
            if ok and self.has_module(python_executable, dependency.import_name):
                installed.append(dependency.import_name)
                continue
            if dependency.required:
                failed.append(dependency.import_name)
            else:
                optional_failed.append(dependency.import_name)

        return DependencyInstallResult(
            ok=(not failed or not fail_on_required),
            installed=installed,
            missing=missing,
            failed=failed,
            optional_failed=optional_failed,
        )
