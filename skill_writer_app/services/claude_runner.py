from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Callable, List, Optional

from skill_writer_app.services.claude_locator import resolve_claude_executable
from skill_writer_app.services.process_command import normalize_windows_script_command, windows_subprocess_kwargs
from skill_writer_app.services.text_decode import decode_process_output


class ClaudeRunner:
    def __init__(self) -> None:
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.last_error_message: str = ""
        self.last_resolved_executable: str = ""

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
        self.last_resolved_executable = resolve_claude_executable(preferred_path)
        return self.last_resolved_executable

    def _short_json(self, value: object, limit: int = 260) -> str:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except TypeError:
            text = str(value)
        text = " ".join(text.split())
        return text if len(text) <= limit else text[:limit] + "..."

    def build_command(
        self,
        workspace_root: str,
        executable_path: str = "",
        model: str = "",
        extra_args: str = "",
        resume_session_id: str = "",
        resume_last: bool = False,
    ) -> List[str]:
        claude_executable = self.resolve_executable(executable_path)
        command: List[str] = [
            claude_executable,
            "-p",
            "--verbose",
            "--output-format",
            "stream-json",
            "--dangerously-skip-permissions",
        ]
        if model.strip():
            command.extend(["--model", model.strip()])
        if resume_session_id.strip():
            command.extend(["--resume", resume_session_id.strip()])
        elif resume_last:
            command.append("--continue")
        if extra_args.strip():
            command.extend(shlex.split(extra_args.strip(), posix=False))
        return command

    def run_claude(
        self,
        prompt: str,
        workspace_root: str,
        output_file: str,
        log_queue: Queue[str],
        on_complete: Callable[[int], None],
        executable_path: str = "",
        model: str = "",
        extra_args: str = "",
        resume_session_id: str = "",
        resume_last: bool = False,
        on_session_detected: Callable[[str, str], None] | None = None,
    ) -> None:
        if self.is_running():
            raise RuntimeError("当前已有 Claude 任务正在运行")

        self.last_error_message = ""
        command = self.build_command(
            workspace_root=workspace_root,
            executable_path=executable_path,
            model=model,
            extra_args=extra_args,
            resume_session_id=resume_session_id,
            resume_last=resume_last,
        )

        def worker() -> None:
            return_code = -1
            latest_session_id = ""
            final_result = ""
            try:
                Path(output_file).parent.mkdir(parents=True, exist_ok=True)
                log_queue.put("[claude-cli] " + self.last_resolved_executable)
                run_command = normalize_windows_script_command(command)
                log_queue.put("[claude-cmd] " + subprocess.list2cmdline(run_command))
                self.process = subprocess.Popen(
                    run_command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=0,
                    cwd=workspace_root,
                    env=self._subprocess_env(),
                    **self._windows_subprocess_kwargs(),
                )

                assert self.process.stdin is not None
                prompt_input = prompt if prompt.endswith("\n") else prompt + "\n"
                try:
                    self.process.stdin.write(prompt_input.encode("utf-8"))
                    self.process.stdin.flush()
                    self.process.stdin.close()
                except BrokenPipeError as exc:
                    raise RuntimeError(
                        "Claude CLI 提前退出，未接收任务内容；通常是 Claude 参数、认证或本机 CLI 环境异常。"
                    ) from exc

                assert self.process.stdout is not None
                stream_queue: Queue[Optional[bytes]] = Queue()

                def read_stdout() -> None:
                    assert self.process is not None and self.process.stdout is not None
                    for stdout_line in self.process.stdout:
                        stream_queue.put(stdout_line)
                    stream_queue.put(None)

                threading.Thread(target=read_stdout, daemon=True).start()
                last_output_at = time.monotonic()
                while True:
                    try:
                        raw_line = stream_queue.get(timeout=30)
                    except Empty:
                        if self.process is not None and self.process.poll() is None:
                            idle_seconds = int(time.monotonic() - last_output_at)
                            log_queue.put(f"[claude-heartbeat] Claude 仍在运行，已 {idle_seconds} 秒无新输出。")
                            continue
                        break
                    if raw_line is None:
                        break

                    last_output_at = time.monotonic()
                    output_line = decode_process_output(raw_line).rstrip("\r\n")
                    try:
                        payload = json.loads(output_line)
                    except json.JSONDecodeError:
                        if output_line:
                            log_queue.put(output_line)
                        continue

                    session_id = str(payload.get("session_id", "") or "")
                    if session_id and session_id != latest_session_id:
                        latest_session_id = session_id
                        if on_session_detected:
                            on_session_detected(session_id, "")

                    payload_type = payload.get("type")
                    if payload_type == "system" and payload.get("subtype") == "init":
                        cwd = str(payload.get("cwd", "") or "")
                        active_model = str(payload.get("model", "") or "")
                        log_queue.put(f"[claude-init] cwd={cwd} model={active_model}")
                    elif payload_type == "assistant":
                        content = payload.get("message", {}).get("content", [])
                        for block in content if isinstance(content, list) else []:
                            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                                log_queue.put(str(block["text"]))
                            elif isinstance(block, dict) and block.get("type") == "tool_use":
                                tool_name = str(block.get("name", "") or "")
                                tool_input = self._short_json(block.get("input", {}))
                                log_queue.put(f"[claude-tool] {tool_name} {tool_input}")
                    elif payload_type == "user":
                        content = payload.get("message", {}).get("content", [])
                        for block in content if isinstance(content, list) else []:
                            if not isinstance(block, dict) or block.get("type") != "tool_result":
                                continue
                            if block.get("is_error"):
                                log_queue.put(f"[claude-tool-error] {self._short_json(block.get('content', ''))}")
                    elif payload_type == "result":
                        final_result = str(payload.get("result", "") or "")
                        if payload.get("is_error"):
                            log_queue.put(f"[claude-result-error] {final_result or payload.get('subtype', '')}")
                        if final_result:
                            log_queue.put(final_result)

                return_code = self.process.wait()
                Path(output_file).write_text(final_result, encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                self.last_error_message = str(exc)
                log_queue.put(f"[claude-error] {exc}")
            finally:
                self.process = None
                on_complete(return_code)

        threading.Thread(target=worker, daemon=True).start()
