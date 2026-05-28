from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from skill_artifact_utils import load_json

USER_VISIBLE_FIELDS = (
    "name",
    "desc",
    "de_desc",
    "buff_desc",
    "desc1",
    "effect_desc",
    "beizhu2",
    "param1",
    "param2",
    "param3",
    "param4",
    "param5",
    "param6",
    "param7",
    "param8",
)

SKILL_BLOCK_RE = re.compile("\u6280\u80fd\\d+\\s*:.*?(?=\\n\\s*\u6280\u80fd\\d+\\s*:|\\Z)", re.S)
ATTACK_TYPE_LABELS = {
    "ATK": "\u6b66\u5668\u653b\u51fb",
    "INTELLECT": "\u667a\u8c0b\u653b\u51fb",
    "COMMAND": "\u7edf\u7387\u653b\u51fb",
    "SPEED": "\u901f\u5ea6\u653b\u51fb",
}
ATTR_LABELS = {
    "HARM_PHY_P": "\u9020\u6210\u6b66\u5668\u4f24\u5bb3\u63d0\u9ad8{value}",
    "HARM_INTELLECT_P": "\u9020\u6210\u667a\u8c0b\u4f24\u5bb3\u63d0\u9ad8{value}",
    "DOUBLE_HIT": "\u8fde\u51fb\u63d0\u9ad8{value}",
    "INTELLECT": "\u667a\u529b\u63d0\u9ad8{value}",
    "CRIT_PHY": "\u6b66\u5668\u4f1a\u5fc3\u63d0\u9ad8{value}",
    "CRIT_INTELLECT": "\u667a\u8c0b\u4f1a\u5fc3\u63d0\u9ad8{value}",
    "CRIT_HARM_PHY": "\u6b66\u5668\u4f1a\u5fc3\u4f24\u5bb3\u63d0\u9ad8{value}",
    "CRIT_HARM_INTELLECT": "\u667a\u8c0b\u4f1a\u5fc3\u4f24\u5bb3\u63d0\u9ad8{value}",
    "INJURED_PHY_P": "\u53d7\u5230\u6b66\u5668\u4f24\u5bb3\u964d\u4f4e{value}",
    "INJURED_INTELLECT_P": "\u53d7\u5230\u667a\u8c0b\u4f24\u5bb3\u964d\u4f4e{value}",
}
PERCENT_ATTR_KEYS = {
    "HARM_PHY_P",
    "HARM_INTELLECT_P",
    "DOUBLE_HIT",
    "CRIT_PHY",
    "CRIT_INTELLECT",
    "CRIT_HARM_PHY",
    "CRIT_HARM_INTELLECT",
    "INJURED_PHY_P",
    "INJURED_INTELLECT_P",
}
TARGET_LABELS = {
    (1, 0): "\u654c\u65b9\u76ee\u6807",
    (1, 1): "\u654c\u65b91\u4eba",
    (1, 2): "\u654c\u65b92\u4eba",
    (2, 0): "\u6211\u65b9\u76ee\u6807",
    (2, 1): "\u6211\u65b91\u4eba",
    (2, 6): "\u81ea\u8eab",
}


def auto_repair_payload_text_fields(payload: dict[str, Any], task_dir: Path) -> tuple[dict[str, Any], list[str]]:
    rows = payload.get("rows")
    if not isinstance(rows, dict):
        return payload, []

    notes: list[str] = []
    skill_meta = _load_skill_meta(task_dir)
    skill_names = {skill_id: item["name"] for skill_id, item in skill_meta.items() if item.get("name")}

    for row in rows.get("skill", []):
        if not isinstance(row, dict):
            continue
        skill_id = _safe_int(row.get("id"))
        meta = skill_meta.get(skill_id, {})
        if meta.get("name") and _is_suspicious(row.get("name")):
            row["name"] = meta["name"]
            notes.append(f"skill[{row.get('key') or skill_id}] name repaired")
        if meta.get("desc") and _is_suspicious(row.get("desc")):
            row["desc"] = meta["desc"]
            notes.append(f"skill[{row.get('key') or skill_id}] desc repaired")
        if meta.get("desc") and _is_suspicious(row.get("de_desc")):
            row["de_desc"] = meta["desc"]
            notes.append(f"skill[{row.get('key') or skill_id}] de_desc repaired")
        if skill_id is not None and isinstance(row.get("name"), str) and row.get("name"):
            skill_names[skill_id] = row["name"]

    buff_names: dict[int, str] = {}
    buff_script_skill_names: dict[str, str] = {}
    for row in rows.get("buff", []):
        if not isinstance(row, dict):
            continue
        buff_id = _safe_int(row.get("id"))
        parent_skill_id = _parent_skill_id_from_buff_id(buff_id)
        parent_skill_name = skill_names.get(parent_skill_id, _fallback_skill_name(parent_skill_id))
        if _is_suspicious(row.get("name")):
            row["name"] = _derive_buff_name(row, parent_skill_name)
            notes.append(f"buff[{row.get('key') or buff_id}] name repaired")
        if _is_suspicious(row.get("desc")):
            row["desc"] = _derive_buff_desc(row, parent_skill_name, skill_meta.get(parent_skill_id, {}).get("desc", ""))
            notes.append(f"buff[{row.get('key') or buff_id}] desc repaired")
        if buff_id is not None and isinstance(row.get("name"), str) and row.get("name"):
            buff_names[buff_id] = row["name"]
        script_name = str(row.get("script") or "").strip()
        if script_name and parent_skill_name:
            buff_script_skill_names[script_name] = parent_skill_name

    for row in rows.get("skill_stage", []):
        if not isinstance(row, dict):
            continue
        if _is_suspicious(row.get("desc")):
            row["desc"] = _derive_stage_desc(row, buff_names, skill_names)
            notes.append(f"stage[{row.get('key') or row.get('skill_id')}] desc repaired")

    for row in rows.get("war_paper", []):
        if not isinstance(row, dict):
            continue
        skill_name = _derive_war_skill_name(row, buff_script_skill_names)
        if _is_suspicious(row.get("desc1")):
            row["desc1"] = _derive_war_desc(row, skill_name)
            notes.append(f"war[{row.get('name') or row.get('ID')}] desc1 repaired")
        for index in range(1, 9):
            field = f"param{index}"
            if _is_suspicious(row.get(field)):
                row[field] = f"\u53c2\u6570{index}"
                notes.append(f"war[{row.get('name') or row.get('ID')}] {field} repaired")

    _fill_fallbacks(rows, skill_names, buff_names)
    return payload, _dedupe(notes)


def _load_skill_meta(task_dir: Path) -> dict[int, dict[str, str]]:
    for path in (task_dir / "task_state.json", task_dir / "task_memory.json"):
        try:
            data = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        text = str(data.get("skill_description") or data.get("requirement") or "").strip()
        meta = _parse_skill_meta(text)
        if meta:
            return meta
    for path in (
        task_dir / "task_handoff.md",
        task_dir / "logs" / "last_codex_prompt.txt",
        task_dir / "logs" / "last_model_message.txt",
    ):
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        meta = _parse_skill_meta(text)
        if meta:
            return meta
    return {}


def _parse_skill_meta(text: str) -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}
    if not text:
        return result
    for block in SKILL_BLOCK_RE.findall(text):
        skill_id = _capture(block, "\u6280\u80fdID\\s*[:\uff1a]\\s*(\\d+)")
        name = _capture(block, "\u6280\u80fd\u540d\\s*[:\uff1a]\\s*(.+)")
        desc = _capture(block, "\u6280\u80fd\u63cf\u8ff0\\s*[:\uff1a]\\s*(.+)")
        sid = _safe_int(skill_id)
        if sid is None:
            continue
        result[sid] = {"name": _clean_line(name), "desc": _clean_line(desc)}
    return result


def _derive_stage_desc(row: dict[str, Any], buff_names: dict[int, str], skill_names: dict[int, str]) -> str:
    script = str(row.get("script") or "").strip()
    if script == "attack":
        attack_type, percent = _parse_attack_param(str(row.get("param") or ""))
        return f"\u5bf9{_target_label(row)}\u53d1\u52a81\u6b21{attack_type}(\u4f24\u5bb3\u7387{percent})"
    if script == "add_buff":
        buff_id = _safe_int(str(row.get("param") or "").split(",")[0])
        buff_name = buff_names.get(buff_id, f"Buff{buff_id}" if buff_id is not None else "Buff")
        return f"\u4f7f{_target_label(row)}\u83b7\u5f97\u300c{buff_name}\u300d"
    if script == "add_buff_target_attr":
        parts = [part.strip() for part in str(row.get("param") or "").split(",") if part.strip()]
        buff_id = _safe_int(parts[1]) if len(parts) >= 2 else None
        buff_name = buff_names.get(buff_id, f"Buff{buff_id}" if buff_id is not None else "Buff")
        skill_name = skill_names.get(_safe_int(row.get("skill_id")), "\u6280\u80fd\u6548\u679c")
        return f"\u4e3a\u76ee\u6807\u9644\u52a0\u300c{buff_name}\u300d({skill_name}\u9636\u6bb5\u6548\u679c)"
    skill_name = skill_names.get(_safe_int(row.get("skill_id")), "\u6280\u80fd\u6548\u679c")
    return f"{skill_name}\u9636\u6bb5{row.get('stage')}\u6548\u679c"


def _derive_buff_name(row: dict[str, Any], parent_skill_name: str) -> str:
    if str(row.get("script") or "").strip() == "add_attr":
        if int(row.get("add_max") or 0) > 1:
            return f"{parent_skill_name}\u589e\u76ca"
        return f"{parent_skill_name}\u72b6\u6001"
    return f"{parent_skill_name}Buff"


def _derive_buff_desc(row: dict[str, Any], parent_skill_name: str, skill_desc: str) -> str:
    script = str(row.get("script") or "").strip()
    if script == "man_jiang_hong":
        return skill_desc or _describe_man_jiang_hong(str(row.get("param") or ""), int(row.get("time") or 0))
    if script == "add_attr":
        return _describe_add_attr_buff(row, parent_skill_name)
    return skill_desc or f"{parent_skill_name}\u6548\u679cBuff"


def _describe_add_attr_buff(row: dict[str, Any], parent_skill_name: str) -> str:
    parts = []
    for item in str(row.get("param") or "").split("|"):
        if "," not in item:
            continue
        code, raw_value = [bit.strip() for bit in item.split(",", 1)]
        value = _safe_int(raw_value)
        if value is None:
            continue
        template = ATTR_LABELS.get(code)
        if template:
            parts.append(template.format(value=_format_attr_value(code, value)))
        else:
            parts.append(f"{code}={value}")
    if not parts:
        parts.append(f"{parent_skill_name}\u6548\u679c")
    text = "\uff0c".join(parts)
    duration = int(row.get("time") or 0)
    if duration > 0:
        text += f"\uff0c\u6301\u7eed{duration}\u56de\u5408"
    add_max = int(row.get("add_max") or 0)
    if add_max > 1:
        text += f"\uff0c\u6700\u591a\u53e0\u52a0{add_max}\u5c42"
    return text


def _describe_man_jiang_hong(param: str, duration: int) -> str:
    pieces = [part.strip() for part in str(param).split("|")]
    attack_type = "\u6b66\u5668\u653b\u51fb"
    base_percent = "0%"
    target_count = 0
    round_limit = 0
    step_percent = "0%"
    cap_percent = "0%"
    if pieces and "," in pieces[0]:
        code, raw_value = [bit.strip() for bit in pieces[0].split(",", 1)]
        attack_type = ATTACK_TYPE_LABELS.get(code, f"{code}\u653b\u51fb")
        base_percent = _format_percent(_safe_int(raw_value) or 0)
    if len(pieces) >= 2:
        target_bits = [bit.strip() for bit in pieces[1].split(",") if bit.strip()]
        if len(target_bits) >= 2:
            target_count = _safe_int(target_bits[1]) or 0
    if len(pieces) >= 3:
        rule_bits = [bit.strip() for bit in pieces[2].split(",") if bit.strip()]
        if len(rule_bits) >= 3:
            round_limit = _safe_int(rule_bits[0]) or 0
            step_percent = _format_percent(_safe_int(rule_bits[1]) or 0)
            cap_percent = _format_percent(_safe_int(rule_bits[2]) or 0)
    target_text = f"\u654c\u65b9{target_count}\u540d\u89d2\u8272" if target_count > 0 else "\u654c\u65b9\u76ee\u6807"
    text = f"\u53d7\u5230\u4f24\u5bb3\u540e\uff0c\u968f\u673a\u5bf9{target_text}\u9020\u62101\u6b21{attack_type}(\u4f24\u5bb3\u7387{base_percent})"
    if round_limit > 0:
        text += f"\uff0c\u6bcf\u56de\u5408\u9650{round_limit}\u6b21"
    if step_percent != "0%" and cap_percent != "0%":
        text += f"\uff1b\u6bcf\u7d2f\u8ba1\u89e6\u53d13\u6b21\uff0c\u4f24\u5bb3\u7387\u63d0\u9ad8{step_percent}\uff0c\u6700\u591a\u8fbe\u5230{cap_percent}"
    if duration > 0:
        text += f"\uff0c\u6301\u7eed{duration}\u56de\u5408"
    return text


def _derive_war_skill_name(row: dict[str, Any], buff_script_skill_names: dict[str, str]) -> str:
    name = str(row.get("name") or "").strip()
    prefix = name.rsplit("_", 1)[0] if "_" in name else name
    return buff_script_skill_names.get(prefix, "\u6280\u80fd\u6548\u679c")


def _derive_war_desc(row: dict[str, Any], skill_name: str) -> str:
    name = str(row.get("name") or "")
    if name.endswith("_trigger"):
        return f"{skill_name}\u89e6\u53d1\uff1a\u5bf9%s\u4e2a\u76ee\u6807\u9020\u6210%s\u4f24\u5bb3\uff0c\u5f53\u524d\u56de\u5408\u6b21\u6570%s/%s\u6b21"
    if name.endswith("_power_up"):
        return f"{skill_name}\u5f3a\u5316\uff1a\u7d2f\u8ba1\u89e6\u53d1%s\u6b21\u540e\uff0c\u4f24\u5bb3\u7387\u63d0\u5347\u81f3%s"
    if name.endswith("_no_target"):
        return f"{skill_name}\u89e6\u53d1\u5931\u8d25\uff1a\u6ca1\u6709\u53ef\u751f\u6548\u7684\u76ee\u6807"
    return f"{skill_name}\u89e6\u53d1\u6218\u62a5"


def _fill_fallbacks(rows: dict[str, Any], skill_names: dict[int, str], buff_names: dict[int, str]) -> None:
    for row in rows.get("skill", []):
        if not isinstance(row, dict):
            continue
        skill_id = _safe_int(row.get("id"))
        skill_name = skill_names.get(skill_id, _fallback_skill_name(skill_id))
        if _is_suspicious(row.get("name")):
            row["name"] = skill_name
        if _is_suspicious(row.get("desc")):
            row["desc"] = f"{skill_name}\u6548\u679c\u8bf4\u660e"
        if _is_suspicious(row.get("de_desc")):
            row["de_desc"] = row.get("desc") or f"{skill_name}\u6548\u679c\u8bf4\u660e"

    for row in rows.get("skill_stage", []):
        if not isinstance(row, dict):
            continue
        if _is_suspicious(row.get("desc")):
            row["desc"] = _derive_stage_desc(row, buff_names, skill_names)

    for row in rows.get("buff", []):
        if not isinstance(row, dict):
            continue
        buff_id = _safe_int(row.get("id"))
        parent_skill_name = skill_names.get(_parent_skill_id_from_buff_id(buff_id), _fallback_skill_name(_parent_skill_id_from_buff_id(buff_id)))
        if _is_suspicious(row.get("name")):
            row["name"] = _derive_buff_name(row, parent_skill_name)
        if _is_suspicious(row.get("desc")):
            row["desc"] = _derive_buff_desc(row, parent_skill_name, "")

    for row in rows.get("war_paper", []):
        if not isinstance(row, dict):
            continue
        if _is_suspicious(row.get("desc1")):
            row["desc1"] = _derive_war_desc(row, "\u6280\u80fd\u6548\u679c")
        for index in range(1, 9):
            field = f"param{index}"
            if _is_suspicious(row.get(field)):
                row[field] = f"\u53c2\u6570{index}"


def _parse_attack_param(param: str) -> tuple[str, str]:
    parts = [part.strip() for part in str(param).split(",") if part.strip()]
    code = parts[0] if parts else "ATK"
    value = _safe_int(parts[1]) if len(parts) >= 2 else 0
    return ATTACK_TYPE_LABELS.get(code, f"{code}\u653b\u51fb"), _format_percent(value or 0)


def _target_label(row: dict[str, Any]) -> str:
    camp = _safe_int(row.get("camp")) or 0
    target = _safe_int(row.get("target")) or 0
    label = TARGET_LABELS.get((camp, target))
    if label:
        return label
    if camp == 1:
        return "\u654c\u65b9\u76ee\u6807"
    if camp == 2:
        return "\u6211\u65b9\u76ee\u6807"
    return "\u76ee\u6807"


def _format_attr_value(code: str, value: int) -> str:
    if code in PERCENT_ATTR_KEYS or code.endswith("_P"):
        return _format_percent(value)
    return str(value)


def _format_percent(value: int) -> str:
    return f"{value / 10:g}%"


def _capture(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _fallback_skill_name(skill_id: int | None) -> str:
    if skill_id is None:
        return "\u6280\u80fd"
    return f"\u6280\u80fd{skill_id}"


def _parent_skill_id_from_buff_id(buff_id: int | None) -> int | None:
    if buff_id is None or buff_id < 100:
        return None
    return buff_id // 100


def _clean_line(value: str) -> str:
    return re.sub(r"\\s+", " ", str(value or "")).strip()


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_suspicious(value: Any) -> bool:
    return isinstance(value, str) and ("??" in value or value.count("?") >= 3)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
