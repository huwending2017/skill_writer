from __future__ import annotations

import re
from typing import Iterable


class LogSanitizer:
    SCRIPT_LINE_RE = re.compile(
        r"^\s*("
        r"[-=]{8,}|"
        r"--|"
        r"function\s+[\w.:]+|"
        r"local\s+[\w_]+|"
        r"if\s+.+\s+then|"
        r"elseif\s+.+\s+then|"
        r"else\s*$|"
        r"for\s+.+\s+do|"
        r"while\s+.+\s+do|"
        r"repeat\s*$|"
        r"until\s+.+|"
        r"return\b|"
        r"end\s*$|"
        r"require\s*\(|"
        r"module\s*\(|"
        r"DEBUG\s*\(|"
        r"[\w.]+:[\w_]+\s*\(|"
        r"[\w.]+\.[\w_]+\s*=|"
        r"[\w_]+\s*=\s*[\w.]+:[\w_]+\s*\("
        r")"
    )
    CODE_FENCE_RE = re.compile(r"^\s*```")
    MARKDOWN_HEADING_RE = re.compile(r"^\s*#{1,6}\s+")
    MARKDOWN_BULLET_RE = re.compile(r"^\s*[-*]\s+")
    MARKDOWN_NUMBERED_RE = re.compile(r"^\s*\d+\.\s+")
    SKILL_TAG_RE = re.compile(r"^\s*</?(skill|name|path)>", re.IGNORECASE)
    YAML_DIVIDER_RE = re.compile(r"^\s*---\s*$")
    PATH_LIST_RE = re.compile(
        r"^\s*(?:[A-Za-z]:\\|/|\\\\).+\.(lua|py|js|ts|json|md|txt|xlsx?|csv)(?::\d+(?::\d+)?)?\s*$",
        re.IGNORECASE,
    )
    MOJIBAKE_RE = re.compile(r"[锛涓鍙瀛鎺瑙鐨鏂浣绋]|[\ue000-\uf8ff]")
    SAFE_PREFIX_RE = re.compile(r"^\s*\[[A-Za-z0-9_-]+\]")

    def __init__(self) -> None:
        self.suppressed_script_lines = 0
        self.in_code_fence = False

    def sanitize_lines(self, lines: Iterable[str]) -> list[str]:
        output: list[str] = []
        for line in lines:
            if self._should_suppress(line):
                self.suppressed_script_lines += 1
                continue
            self._flush_summary(output)
            output.append(line)
        return output

    def flush(self) -> list[str]:
        output: list[str] = []
        self._flush_summary(output)
        return output

    def _flush_summary(self, output: list[str]) -> None:
        if self.suppressed_script_lines:
            output.append(f"[log-filter] 已折叠 {self.suppressed_script_lines} 行脚本/文件列表内容")
            self.suppressed_script_lines = 0

    def _should_suppress(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return self.in_code_fence or self.suppressed_script_lines > 0

        if self.CODE_FENCE_RE.match(stripped):
            self.in_code_fence = not self.in_code_fence
            return True
        if self.in_code_fence:
            return True

        if self.MOJIBAKE_RE.search(stripped):
            return True
        if self.SAFE_PREFIX_RE.match(stripped):
            return False
        if stripped.startswith(("payload:", "dry_run:", "dedupe_existing:", "engine:", "scan_mode:")):
            return False
        if stripped.startswith(("[timing]", "skill:", "skill_stage:", "buff:", "war_paper:")):
            return False
        if "结束，退出码" in stripped or "开始执行" in stripped:
            return False

        if self.PATH_LIST_RE.match(stripped):
            return True
        if self.SKILL_TAG_RE.match(stripped) or self.YAML_DIVIDER_RE.match(stripped):
            return True
        if self.MARKDOWN_HEADING_RE.match(stripped):
            return True
        if self.MARKDOWN_BULLET_RE.match(stripped):
            return True
        if self.MARKDOWN_NUMBERED_RE.match(stripped):
            return True
        if self.SCRIPT_LINE_RE.match(line):
            return True
        return False
