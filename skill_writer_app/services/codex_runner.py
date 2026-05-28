from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Callable, List, Optional, Sequence

from skill_writer_app.services.codex_locator import resolve_codex_executable
from skill_writer_app.services.process_command import normalize_windows_script_command, windows_subprocess_kwargs
from skill_writer_app.services.text_decode import decode_process_output


class CodexRunner:
    CODE_EXCERPT_LINE_RE = re.compile(r"^\s*\d+[-:].+")
    DIFF_LINE_RE = re.compile(r"^(diff --git|index [0-9a-f]+\.\.[0-9a-f]+|@@|--- |\+\+\+ )")
    MARKDOWN_CODE_FENCE_RE = re.compile(r"^\s*```")
    KNOWLEDGE_HEADING_RE = re.compile(r"^\s*#{2,}\s+\d+(\.\d+)*\b")
    BACKTICK_ONLY_RE = re.compile(r"^\s*`[^`]+`\s*$")
    BULLET_CODE_SYMBOL_RE = re.compile(r"^\s*[-*]\s*`[^`]+`")
    BULLET_FUNCTION_RE = re.compile(r"^\s*[-*]\s*[\w:.]+\(.*\)")
    LUA_MODULE_LINE_RE = re.compile(r"^\s*module/[A-Za-z0-9_./-]+\.lua\b")
    INDENTED_CODE_LINE_RE = re.compile(r"^\s{2,}(local |function |if |for |while |return |require\b|self\.|script\.|end\b)")
    METHOD_REFERENCE_RE = re.compile(r"^\s*[\w:.]+\(.*\)\s*$")
    SEARCH_RESULT_LINE_RE = re.compile(
        r"^[A-Za-z]:\\.+\.(lua|py|json|md|txt|xlsx?|csv):\d+(?::\d+)?:",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.last_error_message: str = ""
        self.last_resolved_executable: str = ""
        self.started_monotonic: float = 0.0
        self.last_output_monotonic: float = 0.0

    def _windows_subprocess_kwargs(self) -> dict:
        return windows_subprocess_kwargs()

    def _subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("PYTHONPYCACHEPREFIX", None)
        return env

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

    def resolve_executable(self, preferred_path: str = "") -> str:
        self.last_resolved_executable = resolve_codex_executable(preferred_path)
        return self.last_resolved_executable

    def build_command(
        self,
        workspace_root: str,
        output_file: str,
        executable_path: str = "",
        model: str = "",
        extra_args: str = "",
        preset_args: Sequence[str] | None = None,
    ) -> List[str]:
        codex_executable = self.resolve_executable(executable_path)
        command: List[str] = [
            codex_executable,
            "exec",
            "-C",
            workspace_root,
        ]
        if model.strip():
            command.extend(["-m", model.strip()])
        if preset_args:
            command.extend(list(preset_args))
        if extra_args.strip():
            command.extend(shlex.split(extra_args.strip(), posix=False))
        command.extend(
            [
                "--dangerously-bypass-approvals-and-sandbox",
                "--output-last-message",
                output_file,
                "-",
            ]
        )
        return command

    def build_resume_command(
        self,
        output_file: str,
        session_id: str = "",
        executable_path: str = "",
        model: str = "",
        extra_args: str = "",
        preset_args: Sequence[str] | None = None,
    ) -> List[str]:
        codex_executable = self.resolve_executable(executable_path)
        command: List[str] = [
            codex_executable,
            "exec",
            "resume",
        ]
        if model.strip():
            command.extend(["-m", model.strip()])
        if preset_args:
            command.extend(list(preset_args))
        if extra_args.strip():
            command.extend(shlex.split(extra_args.strip(), posix=False))
        command.extend(
            [
                "--dangerously-bypass-approvals-and-sandbox",
                "--output-last-message",
                output_file,
            ]
        )
        if session_id.strip():
            command.append(session_id.strip())
        else:
            command.append("--last")
        command.append("-")
        return command

    def find_latest_session_for_workspace(self, workspace_root: str, since_timestamp: float = 0.0) -> tuple[str, str]:
        session_root = Path.home() / ".codex" / "sessions"
        if not session_root.exists():
            return "", ""
        try:
            workspace = str(Path(workspace_root).resolve()).lower()
        except OSError:
            workspace = str(Path(workspace_root)).lower()

        try:
            candidates = sorted(
                (path for path in session_root.rglob("*.jsonl") if path.is_file()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return "", ""

        for path in candidates[:80]:
            try:
                if since_timestamp and path.stat().st_mtime + 2 < since_timestamp:
                    continue
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    first_line = handle.readline()
                payload = json.loads(first_line)
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("type") != "session_meta":
                continue
            meta = payload.get("payload", {})
            if not isinstance(meta, dict):
                continue
            try:
                cwd = str(Path(str(meta.get("cwd", ""))).resolve()).lower()
            except OSError:
                cwd = str(Path(str(meta.get("cwd", "")))).lower()
            if cwd != workspace:
                continue
            originator = str(meta.get("originator", meta.get("source", "")))
            if originator.startswith("codex") or meta.get("source") == "exec":
                return str(meta.get("id", "")), str(path)
        return "", ""

    def _should_fold_stdout_line(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if self.CODE_EXCERPT_LINE_RE.match(line):
            return True
        if self.DIFF_LINE_RE.match(stripped):
            return True
        if self.SEARCH_RESULT_LINE_RE.match(stripped):
            return True
        return False

    def _should_fold_verbose_stdout_line(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if self._should_fold_stdout_line(line):
            return True
        if self.MARKDOWN_CODE_FENCE_RE.match(stripped):
            return True
        if self.KNOWLEDGE_HEADING_RE.match(stripped):
            return True
        if self.BACKTICK_ONLY_RE.match(stripped):
            return True
        if self.BULLET_CODE_SYMBOL_RE.match(stripped):
            return True
        if self.BULLET_FUNCTION_RE.match(stripped):
            return True
        if self.LUA_MODULE_LINE_RE.match(stripped):
            return True
        if self.INDENTED_CODE_LINE_RE.match(line):
            return True
        if self.METHOD_REFERENCE_RE.match(stripped):
            return True
        if "`" in stripped and (
            "module/" in stripped
            or ".lua" in stripped
            or "script." in stripped
            or "self." in stripped
            or ":" in stripped
        ):
            return True
        return False

    def _flush_folded_output(self, log_queue: Queue[str], folded_line_count: int, folded_context: str) -> int:
        if folded_line_count:
            label = folded_context or "代码/知识索引片段"
            log_queue.put(f"[codex-output] 已折叠 {folded_line_count} 行{label}")
        return 0

    def run_codex(
        self,
        prompt: str,
        workspace_root: str,
        output_file: str,
        log_queue: Queue[str],
        on_complete: Callable[[int], None],
        executable_path: str = "",
        model: str = "",
        extra_args: str = "",
        preset_args: Sequence[str] | None = None,
        resume_session_id: str = "",
        resume_last: bool = False,
        on_session_detected: Callable[[str, str], None] | None = None,
    ) -> None:
        if self.is_running():
            raise RuntimeError("当前已有 Codex 任务正在运行")

        self.last_error_message = ""
        self.started_monotonic = time.monotonic()
        self.last_output_monotonic = self.started_monotonic
        if resume_session_id or resume_last:
            command = self.build_resume_command(
                output_file=output_file,
                session_id=resume_session_id,
                executable_path=executable_path,
                model=model,
                extra_args=extra_args,
                preset_args=preset_args,
            )
        else:
            command = self.build_command(
                workspace_root=workspace_root,
                output_file=output_file,
                executable_path=executable_path,
                model=model,
                extra_args=extra_args,
                preset_args=preset_args,
            )

        def worker() -> None:
            return_code = -1
            folded_line_count = 0
            folded_context = ""
            started_scan_at = time.time() - 3
            detected_session_id = ""
            try:
                output_path = Path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                if output_path.exists():
                    try:
                        output_path.unlink()
                    except OSError:
                        output_path.write_text("", encoding="utf-8")
                prompt_file = output_path.with_name("last_codex_prompt.txt")
                prompt_file.write_text(prompt, encoding="utf-8")
                log_queue.put(f"[codex-prompt] chars={len(prompt)} saved={prompt_file}")
                log_queue.put("[codex-cli] " + self.last_resolved_executable)
                run_command = normalize_windows_script_command(command)
                log_queue.put("[codex-cmd] " + subprocess.list2cmdline(run_command))
                proc = subprocess.Popen(
                    run_command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=0,
                    env=self._subprocess_env(),
                    **self._windows_subprocess_kwargs(),
                )
                self.process = proc

                assert proc.stdin is not None
                proc.stdin.write(prompt.encode("utf-8"))
                proc.stdin.close()

                for _ in range(10):
                    detected_session_id, session_file = self.find_latest_session_for_workspace(
                        workspace_root,
                        started_scan_at,
                    )
                    if detected_session_id:
                        if on_session_detected:
                            on_session_detected(detected_session_id, session_file)
                        break
                    time.sleep(0.3)

                assert proc.stdout is not None
                stream_queue: Queue[Optional[bytes]] = Queue()

                def read_stdout() -> None:
                    assert proc.stdout is not None
                    for stdout_line in proc.stdout:
                        stream_queue.put(stdout_line)
                    stream_queue.put(None)

                threading.Thread(target=read_stdout, daemon=True).start()
                last_output_at = time.monotonic()
                self.last_output_monotonic = last_output_at
                while True:
                    try:
                        raw_line = stream_queue.get(timeout=30)
                    except Empty:
                        if proc.poll() is None:
                            idle_seconds = int(time.monotonic() - last_output_at)
                            log_queue.put(f"[codex-heartbeat] Codex 仍在运行，已 {idle_seconds} 秒无新输出。")
                            continue
                        break
                    if raw_line is None:
                        break

                    last_output_at = time.monotonic()
                    self.last_output_monotonic = last_output_at
                    output_line = decode_process_output(raw_line).rstrip("\r\n")
                    if not detected_session_id:
                        detected_session_id, session_file = self.find_latest_session_for_workspace(
                            workspace_root,
                            started_scan_at,
                        )
                        if detected_session_id and on_session_detected:
                            on_session_detected(detected_session_id, session_file)
                    if self._should_fold_verbose_stdout_line(output_line):
                        folded_line_count += 1
                        stripped = output_line.strip()
                        if self.KNOWLEDGE_HEADING_RE.match(stripped):
                            folded_context = "知识索引/代码片段"
                        elif self.SEARCH_RESULT_LINE_RE.match(stripped):
                            folded_context = "代码检索结果"
                        elif self.DIFF_LINE_RE.match(stripped):
                            folded_context = "差异片段"
                        elif not folded_context:
                            folded_context = "代码/知识索引片段"
                        continue
                    if folded_line_count:
                        folded_line_count = self._flush_folded_output(log_queue, folded_line_count, folded_context)
                        folded_context = ""
                    log_queue.put(output_line)

                if folded_line_count:
                    self._flush_folded_output(log_queue, folded_line_count, folded_context)

                return_code = proc.wait()
                if not detected_session_id:
                    detected_session_id, session_file = self.find_latest_session_for_workspace(
                        workspace_root,
                        started_scan_at,
                    )
                    if detected_session_id and on_session_detected:
                        on_session_detected(detected_session_id, session_file)
            except Exception as exc:  # noqa: BLE001
                self.last_error_message = str(exc)
                log_queue.put(f"[codex-error] {exc}")
            finally:
                self.process = None
                on_complete(return_code)

        threading.Thread(target=worker, daemon=True).start()
