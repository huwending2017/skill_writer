from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, List


PATH_RE = re.compile(r"[A-Za-z]:\\[^\s`\"'\]\)]+")


@dataclass
class SessionSummary:
    session_file: str
    session_id: str
    timestamp: str
    cwd: str
    source: str
    model_provider: str
    user_message_count: int = 0
    assistant_message_count: int = 0
    last_user_message: str = ""
    last_assistant_message: str = ""
    mentioned_paths: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SessionHandoffService:
    def summarize_directory(self, session_dir: str | Path) -> list[SessionSummary]:
        root = Path(session_dir)
        if not root.exists():
            raise FileNotFoundError(f"Session directory does not exist: {root}")

        summaries: list[SessionSummary] = []
        for path in sorted(root.glob("*.jsonl")):
            summary = self.summarize_file(path)
            if summary:
                summaries.append(summary)
        return summaries

    def summarize_file(self, session_file: str | Path) -> SessionSummary | None:
        path = Path(session_file)
        if not path.exists():
            return None

        meta: dict[str, str] = {
            "session_id": "",
            "timestamp": "",
            "cwd": "",
            "source": "",
            "model_provider": "",
        }
        user_messages: list[str] = []
        assistant_messages: list[str] = []
        mentioned_paths: set[str] = set()

        for raw_line in self._iter_lines(path):
            payload = self._parse_json_line(raw_line)
            if not payload:
                continue

            record_type = payload.get("type")
            body = payload.get("payload", {})
            if record_type == "session_meta" and isinstance(body, dict):
                meta["session_id"] = self._string(body.get("id"))
                meta["timestamp"] = self._string(body.get("timestamp"))
                meta["cwd"] = self._string(body.get("cwd"))
                meta["source"] = self._string(body.get("source"))
                meta["model_provider"] = self._string(body.get("model_provider"))
                continue

            if record_type != "response_item" or not isinstance(body, dict):
                continue
            if body.get("type") != "message":
                continue

            role = self._string(body.get("role"))
            text = self._extract_message_text(body.get("content"))
            if not text:
                continue

            for match in PATH_RE.findall(text):
                mentioned_paths.add(match)

            if role == "user":
                user_messages.append(text)
            elif role == "assistant":
                assistant_messages.append(text)

        if not any(meta.values()) and not user_messages and not assistant_messages:
            return None

        return SessionSummary(
            session_file=str(path),
            session_id=meta["session_id"],
            timestamp=meta["timestamp"],
            cwd=meta["cwd"],
            source=meta["source"],
            model_provider=meta["model_provider"],
            user_message_count=len(user_messages),
            assistant_message_count=len(assistant_messages),
            last_user_message=user_messages[-1] if user_messages else "",
            last_assistant_message=assistant_messages[-1] if assistant_messages else "",
            mentioned_paths=sorted(mentioned_paths),
        )

    def render_markdown(self, summaries: Iterable[SessionSummary]) -> str:
        lines: list[str] = ["# Codex Session Handoff", ""]
        for item in summaries:
            lines.extend(
                [
                    f"## {Path(item.session_file).name}",
                    "",
                    f"- session_id: `{item.session_id or 'unknown'}`",
                    f"- timestamp: `{item.timestamp or 'unknown'}`",
                    f"- cwd: `{item.cwd or 'unknown'}`",
                    f"- source: `{item.source or 'unknown'}`",
                    f"- model_provider: `{item.model_provider or 'unknown'}`",
                    f"- user_messages: `{item.user_message_count}`",
                    f"- assistant_messages: `{item.assistant_message_count}`",
                    "",
                    "### Last User Message",
                    "",
                    self._as_blockquote(item.last_user_message or "(none)"),
                    "",
                    "### Last Assistant Message",
                    "",
                    self._as_blockquote(item.last_assistant_message or "(none)"),
                    "",
                ]
            )

            if item.mentioned_paths:
                lines.append("### Mentioned Paths")
                lines.append("")
                for path in item.mentioned_paths:
                    lines.append(f"- `{path}`")
                lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _iter_lines(self, path: Path) -> Iterable[str]:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                yield line.strip()

    def _parse_json_line(self, raw_line: str) -> dict[str, Any] | None:
        if not raw_line:
            return None
        try:
            data = json.loads(raw_line)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _extract_message_text(self, content: Any) -> str:
        if not isinstance(content, list):
            return ""

        chunks: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
                continue
            for key in ("input_text", "output_text"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    chunks.append(value.strip())
                    break

        return "\n\n".join(chunks).strip()

    def _as_blockquote(self, text: str) -> str:
        return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())

    def _string(self, value: Any) -> str:
        return value if isinstance(value, str) else ""
