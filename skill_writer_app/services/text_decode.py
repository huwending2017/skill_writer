from __future__ import annotations

import locale


def decode_process_output(data: bytes) -> str:
    if not data:
        return ""

    encodings = ["utf-8-sig", "utf-8", "gb18030"]
    preferred = locale.getpreferredencoding(False)
    if preferred and preferred.lower() not in {item.lower() for item in encodings}:
        encodings.append(preferred)
    if "mbcs" not in {item.lower() for item in encodings}:
        encodings.append("mbcs")

    best_text = ""
    best_score = -1
    for encoding in encodings:
        try:
            text = data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
        text = repair_mojibake(text)
        score = _decode_score(text)
        if score > best_score:
            best_text = text
            best_score = score
        if "\ufffd" not in text and _looks_readable(text):
            return text

    if best_text:
        return best_text
    return data.decode("utf-8", errors="replace")


def repair_mojibake(text: str) -> str:
    candidates = [text]
    for source_encoding in ("gb18030", "gbk", "cp936"):
        try:
            candidates.append(text.encode(source_encoding).decode("utf-8"))
        except (LookupError, UnicodeEncodeError, UnicodeDecodeError):
            pass

    best = max(candidates, key=_decode_score)
    if _decode_score(best) > _decode_score(text) + 20:
        return best
    return text


def _decode_score(text: str) -> int:
    score = 0
    score -= text.count("\ufffd") * 200
    score -= text.count("�") * 200
    score -= sum(1 for char in text if "\ue000" <= char <= "\uf8ff") * 80
    score -= sum(text.count(marker) for marker in ("锛", "涓", "鍙", "瀛", "鎺", "瑙", "勫", "鐨", "鏂", "浣", "绋", "佹")) * 25
    score -= sum(1 for char in text if ord(char) < 32 and char not in "\r\n\t") * 20
    score += sum(1 for char in text if "\u4e00" <= char <= "\u9fff") * 3
    score += sum(1 for char in text if char.isascii() and (char.isalnum() or char in " _-:/\\.[](){}=+,'\"")) 
    if any(marker in text for marker in ("[task]", "[timing]", "payload:", "skill:", "buff:", "成功", "失败")):
        score += 50
    return score


def _looks_readable(text: str) -> bool:
    if not text:
        return True
    bad = text.count("\ufffd") + text.count("�")
    return bad == 0
