from __future__ import annotations

from typing import Any


MOJIBAKE_MARKERS = ("锛", "涓", "鍙", "瀛", "鎺", "瑙", "鐨", "鏂", "浣", "绋", "鎶", "鑳")


def repair_text(value: str) -> str:
    candidates = [value]
    for source_encoding in ("gb18030", "gbk", "cp936"):
        try:
            candidates.append(value.encode(source_encoding).decode("utf-8"))
        except (LookupError, UnicodeEncodeError, UnicodeDecodeError):
            continue
    return max(candidates, key=_score)


def repair_tree(value: Any) -> Any:
    if isinstance(value, str):
        return repair_text(value)
    if isinstance(value, list):
        return [repair_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: repair_tree(item) for key, item in value.items()}
    return value


def _score(value: str) -> int:
    score = 0
    score -= value.count("\ufffd") * 200
    score -= value.count("锟") * 120
    score -= sum(value.count(marker) for marker in MOJIBAKE_MARKERS) * 18
    score += sum(1 for char in value if "\u4e00" <= char <= "\u9fff") * 3
    score += sum(1 for char in value if char.isascii())
    return score
