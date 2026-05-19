from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


CORE_FILES = [
    "module/object/actor.lua",
    "module/fight/skill.lua",
    "module/fight/buff.lua",
    "module/fight/action.lua",
    "module/fight/damage.lua",
    "module/scene/battle_scene.lua",
    "module/battle_def.lua",
]

SCAN_TARGETS = {
    "actions": "module/actions_new",
    "buffs": "module/buffs_new",
}

FUNCTION_RE = re.compile(r"\bfunction\s+([A-Za-z0-9_:.]+)")
EVENT_RE = re.compile(r"EVENT_DEF\.([A-Z0-9_]+)")
EXTERN_RE = re.compile(r"script\.extern\.([A-Za-z0-9_]+)")
STATE_RE = re.compile(r"customized_buff_state\[(?:\"([^\"]+)\"|'([^']+)')\]")
LOCAL_STRING_RE = re.compile(r"local\s+([A-Za-z0-9_]+)\s*=\s*(?:\"([^\"]+)\"|'([^']+)')")
STATE_VAR_RE = re.compile(r"customized_buff_state\[([A-Za-z0-9_]+)\]")
CONFIG_INDEX_RE = re.compile(r"script\.config\[(\d+)\]")
STATE_ASSIGN_RE = re.compile(r"customized_buff_state\[(?:\"[^\"]+\"|'[^']+')\]\s*=")

CAPABILITY_RULES = [
    ("damage", "damage / harm", ["cal_damage", "damage", "harm", "real_harm", "atk_harm", "int_harm", "attack_"]),
    ("cure", "cure / heal", ["cure_target", "cure", "heal"]),
    ("add_buff", "add buff", ["add_buffs", "add_buff", "attach_buff", "buff_ids"]),
    ("remove_buff", "remove / clean buff", ["remove_buff", "del_buff", "delete_buff", "clean_buff", "dispel"]),
    ("control", "control state", ["confuse", "dizzy", "silent", "disarm", "fear", "panic", "control"]),
    ("attr_flat", "flat attribute change", ["add_attr", "steal_attr", "attr_def", "attr_val"]),
    ("attr_percent", "percent attribute change", ["add_attr_p", "attr_p", "attr_percent"]),
    ("launch_chance", "skill launch chance", ["launch_rate", "add_chance", "skill_rate", "can_launch"]),
    ("damage_modifier", "damage modifier", ["script.extern.damage", "harm_rate", "damage_rate"]),
    ("cure_modifier", "cure modifier", ["script.extern.cure_val", "cure_effect", "cure_rate"]),
    ("state_consumer", "customized state consumer", ["customized_buff_state["]),
    ("targeting", "target selection", ["buff_find_targets", "find_targets", "target_def", "target_list"]),
    ("random_target", "random target", ["random", "random_enemy", "random_team", "num_random"]),
    ("multi_hit", "multi hit / repeated effect", ["attack_times", "times_normal_attack", "multi_hit", "num_list"]),
    ("followup", "follow-up / extra cast", ["follow", "recast", "again", "extra_cast", "cast_again"]),
    ("round_listener", "round listener", ["BUFF_ORDER_START", "BUFF_ORDER_OVER"]),
    ("cast_before_listener", "before cast listener", ["BUFF_CAST_SKILL_BEFORE"]),
    ("cast_after_listener", "after cast listener", ["BUFF_CAST_SKILL_OVER", "BUFF_CAST_SKILL_OVER_AGAIN"]),
    ("damage_listener", "damage-chain listener", ["BUFF_ATTACK_DAMAGE", "BUFF_ATTACKED_DAMAGE"]),
    ("add_buff_listener", "add-buff lifecycle listener", ["BUFF_ADD_START", "BUFF_ADD_OVER", "BUFF_ADDED_OVER"]),
    ("immune", "immune / no-effect", ["immune", "immuge", "no_effect"]),
    ("stack", "stack / layer", ["overlying", "stack", "layer", "add_max"]),
    ("refresh_life", "refresh / duration", ["refresh", "change_life", "life_round", "cover"]),
    ("report", "war report", ["make_effect_records", "insert_effect_list", "make_confuse_records", "war_paper"]),
    ("statistic", "statistic", ["insert_statistic", "statistic"]),
    ("cooldown", "cooldown", ["cooldown", "skill_cd", "clean_first_skill_cd"]),
    ("movement", "movement / position", ["move", "position", "cell_mode"]),
    ("morale", "morale", ["morale"]),
    ("death_trigger", "death trigger", ["dead_rate", "EVENT_DEF.DEAD", "BATTLE_HERO_DEAD"]),
    ("scene_gate", "scene / environment gate", ["scene_type", "check_scene", "cell_mode"]),
    ("unit_gate", "unit / army gate", ["armytype", "general_type", "target_general", "equip", "sex"]),
]

ACTION_FAMILY_HINTS = [
    ("attack", ["action_attack", "damage"]),
    ("cure", ["action_cure", "cure"]),
    ("add_buff", ["action_add_buff", "add_buff"]),
    ("attr", ["action_add_attr", "action_steal_attr", "attr_flat", "attr_percent"]),
    ("state_switch", ["state_consumer", "state_provider"]),
    ("target_gate", ["scene_gate", "unit_gate", "targeting"]),
]

BUFF_FAMILY_HINTS = [
    ("state_provider", ["state_provider"]),
    ("launch_chance", ["launch_chance", "cast_before_listener"]),
    ("damage_modifier", ["damage_modifier", "damage_listener"]),
    ("cure_modifier", ["cure_modifier"]),
    ("round_resident", ["round_listener"]),
    ("add_buff_lifecycle", ["add_buff_listener"]),
    ("followup", ["followup", "cast_after_listener"]),
    ("control_or_debuff", ["control", "remove_buff", "immune"]),
]

TAG_RULES = {
    "damage": ["damage", "harm", "real_harm", "atk_harm", "int_harm"],
    "cure": ["cure", "heal"],
    "control": ["dizzy", "silent", "confuse", "fear", "panic", "control"],
    "add_buff": ["add_buff", "add_buffs", "attach_buff"],
    "remove_buff": ["remove_buff", "del_buff", "delete_buff"],
    "launch_rate": ["launch_rate", "add_chance", "active_skill_byo_launch_rate"],
    "harm_rate": ["harm_rate", "damage_rate"],
    "state_provider": ["customized_buff_state", "add_state"],
    "payload_modifier": ["script.extern", "extern."],
    "targeting": ["target", "target_list", "random_enemy", "random_team"],
    "report": ["make_effect_records", "insert_effect_list", "war_report", "word_record"],
    "statistic": ["insert_statistic", "statistic"],
    "immune": ["immune", "immuge"],
    "stack": ["overlying", "add_max", "stack", "layer"],
    "refresh": ["refresh", "cover", "change_life"],
    "followup": ["follow", "recast", "again", "extra_cast"],
}


@dataclass
class LuaFileSummary:
    category: str
    file_name: str
    relative_path: str
    mtime: float
    functions: list[str]
    events: list[str]
    extern_keys: list[str]
    state_keys: list[str]
    tags: list[str]
    capabilities: list[str]
    family_hints: list[str]
    config_slots: list[int]
    search_keywords: list[str]
    summary: str

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "file_name": self.file_name,
            "relative_path": self.relative_path,
            "mtime": self.mtime,
            "functions": self.functions,
            "events": self.events,
            "extern_keys": self.extern_keys,
            "state_keys": self.state_keys,
            "tags": self.tags,
            "capabilities": self.capabilities,
            "family_hints": self.family_hints,
            "config_slots": self.config_slots,
            "search_keywords": self.search_keywords,
            "summary": self.summary,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build battle action/buff knowledge index.")
    parser.add_argument("--battle-root", required=True, help="Path to xgame_server/service/battle")
    parser.add_argument("--output-json", default="", help="Optional output JSON path")
    parser.add_argument("--output-md", default="", help="Optional output Markdown path")
    return parser.parse_args()


def unique_sorted(values: Iterable[str]) -> list[str]:
    return sorted({value for value in values if value})


def read_text_with_fallback(path: Path) -> str:
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def extract_comment_summary(text: str) -> str:
    lines = text.splitlines()
    collected: list[str] = []
    started = False
    for line in lines[:80]:
        stripped = line.strip()
        if not started and not stripped:
            continue
        if stripped.startswith("--"):
            started = True
            collected.append(stripped.lstrip("- ").strip())
            if len(collected) >= 8:
                break
            continue
        if started:
            break
    if collected:
        return " / ".join(item for item in collected if item)

    fallback: list[str] = []
    for line in lines[:80]:
        stripped = line.strip()
        if stripped.startswith("--"):
            fallback.append(stripped.lstrip("- ").strip())
        if len(fallback) >= 4:
            break
    return " / ".join(item for item in fallback if item)


def infer_tags(file_name: str, text: str) -> list[str]:
    haystack = f"{file_name}\n{text}".lower()
    tags = []
    for tag, keywords in TAG_RULES.items():
        if any(keyword in haystack for keyword in keywords):
            tags.append(tag)
    return unique_sorted(tags)


def infer_capabilities(file_name: str, text: str) -> list[str]:
    haystack = f"{file_name}\n{text}".lower()
    capabilities = []
    for capability, _label, keywords in CAPABILITY_RULES:
        if any(keyword.lower() in haystack for keyword in keywords):
            capabilities.append(capability)
    if "add_state" in file_name.lower() or STATE_ASSIGN_RE.search(text):
        capabilities.append("state_provider")
    return unique_sorted(capabilities)


def infer_family_hints(category: str, file_name: str, capabilities: list[str]) -> list[str]:
    haystack = " ".join([file_name.lower(), *capabilities])
    rules = ACTION_FAMILY_HINTS if category == "actions" else BUFF_FAMILY_HINTS
    hints = []
    for family, keywords in rules:
        if any(keyword.lower() in haystack for keyword in keywords):
            hints.append(family)
    return unique_sorted(hints)


def extract_config_slots(text: str) -> list[int]:
    return sorted({int(item) for item in CONFIG_INDEX_RE.findall(text)})


def split_name_tokens(file_name: str) -> list[str]:
    stem = Path(file_name).stem
    return [part for part in re.split(r"[^A-Za-z0-9]+", stem) if part]


def build_search_keywords(
    file_name: str,
    tags: list[str],
    capabilities: list[str],
    events: list[str],
    extern_keys: list[str],
    state_keys: list[str],
    family_hints: list[str],
) -> list[str]:
    keywords = []
    keywords.extend(split_name_tokens(file_name))
    keywords.extend(tags)
    keywords.extend(capabilities)
    keywords.extend(events)
    keywords.extend(extern_keys)
    keywords.extend(state_keys)
    keywords.extend(family_hints)
    return unique_sorted(item.lower() for item in keywords)


def summarize_lua_file(path: Path, battle_root: Path, category: str) -> LuaFileSummary:
    text = read_text_with_fallback(path)
    state_keys = []
    for match in STATE_RE.findall(text):
        state_keys.append(match[0] or match[1])
    local_string_map = {
        name: (double_quoted or single_quoted)
        for name, double_quoted, single_quoted in LOCAL_STRING_RE.findall(text)
        if double_quoted or single_quoted
    }
    for var_name in STATE_VAR_RE.findall(text):
        mapped = local_string_map.get(var_name)
        if mapped:
            state_keys.append(mapped)
    tags = infer_tags(path.name, text)
    capabilities = infer_capabilities(path.name, text)
    events = unique_sorted(EVENT_RE.findall(text))
    extern_keys = unique_sorted(EXTERN_RE.findall(text))
    family_hints = infer_family_hints(category, path.name, capabilities)

    return LuaFileSummary(
        category=category,
        file_name=path.name,
        relative_path=str(path.relative_to(battle_root)).replace("\\", "/"),
        mtime=path.stat().st_mtime,
        functions=unique_sorted(FUNCTION_RE.findall(text)),
        events=events,
        extern_keys=extern_keys,
        state_keys=unique_sorted(state_keys),
        tags=tags,
        capabilities=capabilities,
        family_hints=family_hints,
        config_slots=extract_config_slots(text),
        search_keywords=build_search_keywords(
            path.name,
            tags,
            capabilities,
            events,
            extern_keys,
            unique_sorted(state_keys),
            family_hints,
        ),
        summary=extract_comment_summary(text),
    )


def build_lookup(items: list[dict], key: str) -> dict:
    lookup: dict[str, list[str]] = {}
    for item in items:
        for value in item.get(key, []):
            lookup.setdefault(value, []).append(item["file_name"])
    return {name: sorted(files) for name, files in sorted(lookup.items())}


def build_keyword_lookup(items: list[dict]) -> dict:
    lookup: dict[str, list[str]] = {}
    for item in items:
        for keyword in item.get("search_keywords", []):
            lookup.setdefault(keyword, []).append(item["file_name"])
    return {name: sorted(files) for name, files in sorted(lookup.items())}


def build_index(battle_root: Path) -> dict:
    files: list[LuaFileSummary] = []
    latest_source_mtime = 0.0

    for category, relative_dir in SCAN_TARGETS.items():
        target_dir = battle_root / relative_dir
        if not target_dir.exists():
            continue
        for path in sorted(target_dir.glob("*.lua")):
            summary = summarize_lua_file(path, battle_root, category)
            latest_source_mtime = max(latest_source_mtime, summary.mtime)
            files.append(summary)

    core_meta = []
    for relative_path in CORE_FILES:
        path = battle_root / relative_path
        if not path.exists():
            continue
        stat = path.stat()
        latest_source_mtime = max(latest_source_mtime, stat.st_mtime)
        core_meta.append(
            {
                "relative_path": relative_path.replace("\\", "/"),
                "mtime": stat.st_mtime,
            }
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    actions = [item.to_dict() for item in files if item.category == "actions"]
    buffs = [item.to_dict() for item in files if item.category == "buffs"]
    all_items = actions + buffs
    return {
        "schema_version": 2,
        "generated_at": generated_at,
        "battle_root": str(battle_root),
        "latest_source_mtime": latest_source_mtime,
        "core_files": core_meta,
        "counts": {
            "actions": len(actions),
            "buffs": len(buffs),
        },
        "actions": actions,
        "buffs": buffs,
        "lookups": {
            "by_capability": build_lookup(all_items, "capabilities"),
            "by_event": build_lookup(all_items, "events"),
            "by_state_key": build_lookup(all_items, "state_keys"),
            "by_extern_key": build_lookup(all_items, "extern_keys"),
            "by_family_hint": build_lookup(all_items, "family_hints"),
            "by_keyword": build_keyword_lookup(all_items),
        },
    }


def render_lookup_section(title: str, lookup: dict, limit_per_key: int = 40) -> list[str]:
    lines = [f"## {title}", ""]
    if not lookup:
        return lines + ["- none", ""]
    for key, files in lookup.items():
        shown = files[:limit_per_key]
        suffix = "" if len(files) <= limit_per_key else f" ... (+{len(files) - limit_per_key})"
        lines.append(f"- `{key}`: {', '.join(f'`{file}`' for file in shown)}{suffix}")
    lines.append("")
    return lines


def render_markdown(index: dict) -> str:
    lines = [
        "# Battle Knowledge Index",
        "",
        f"- generated_at: `{index['generated_at']}`",
        f"- battle_root: `{index['battle_root']}`",
        f"- actions: `{index['counts']['actions']}`",
        f"- buffs: `{index['counts']['buffs']}`",
        "",
        "## How To Use",
        "",
        "1. Convert the skill requirement into capabilities, event timing, state keys, or extern payloads.",
        "2. Check the lookup sections first and shortlist existing files.",
        "3. Read only the shortlisted Lua files before deciding whether a new script is required.",
        "4. Prefer config composition when an existing file already appears under the matching capability.",
        "",
    ]
    lines.extend(render_lookup_section("Capability Lookup", index["lookups"]["by_capability"]))
    lines.extend(render_lookup_section("Event Lookup", index["lookups"]["by_event"]))
    lines.extend(render_lookup_section("State Key Lookup", index["lookups"]["by_state_key"]))
    lines.extend(render_lookup_section("Extern Payload Lookup", index["lookups"]["by_extern_key"]))
    lines.extend(render_lookup_section("Family Hint Lookup", index["lookups"]["by_family_hint"]))
    lines.extend(
        [
        "## Actions",
        "",
        "| File | Family | Capabilities | Events | Extern | State | Config | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in index["actions"]:
        lines.append(
            "| {file} | {family} | {capabilities} | {events} | {extern} | {state} | {config} | {summary} |".format(
                file=item["file_name"],
                family=", ".join(item["family_hints"]),
                capabilities=", ".join(item["capabilities"]),
                events=", ".join(item["events"]),
                extern=", ".join(item["extern_keys"]),
                state=", ".join(item["state_keys"]),
                config=", ".join(str(slot) for slot in item["config_slots"]),
                summary=(item["summary"] or "").replace("|", "/"),
            )
        )

    lines.extend(
        [
            "",
            "## Buffs",
            "",
            "| File | Family | Capabilities | Events | Extern | State | Config | Summary |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in index["buffs"]:
        lines.append(
            "| {file} | {family} | {capabilities} | {events} | {extern} | {state} | {config} | {summary} |".format(
                file=item["file_name"],
                family=", ".join(item["family_hints"]),
                capabilities=", ".join(item["capabilities"]),
                events=", ".join(item["events"]),
                extern=", ".join(item["extern_keys"]),
                state=", ".join(item["state_keys"]),
                config=", ".join(str(slot) for slot in item["config_slots"]),
                summary=(item["summary"] or "").replace("|", "/"),
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    battle_root = Path(args.battle_root).resolve()
    if not battle_root.exists():
        raise FileNotFoundError(f"battle_root not found: {battle_root}")

    cache_root = battle_root / "temp_skill_workspace" / "_global" / "_battle_knowledge_cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    output_json = Path(args.output_json).resolve() if args.output_json else cache_root / "battle_knowledge_index.json"
    output_md = Path(args.output_md).resolve() if args.output_md else cache_root / "battle_knowledge_index.md"

    index = build_index(battle_root)
    output_json.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.write_text(render_markdown(index), encoding="utf-8")

    print(f"[index] json: {output_json}")
    print(f"[index] md: {output_md}")
    print(f"[index] actions: {index['counts']['actions']}")
    print(f"[index] buffs: {index['counts']['buffs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
