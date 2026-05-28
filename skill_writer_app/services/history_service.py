from __future__ import annotations

import json
from pathlib import Path
from typing import List

from skill_writer_app.models import TaskHistoryEntry
from skill_writer_app.services.mojibake_repair import repair_tree
from skill_writer_app.services.text_decode import read_json_file


class HistoryService:
    def __init__(self, history_path: Path, max_entries: int = 500) -> None:
        self.history_path = history_path
        self.max_entries = max_entries

    def load(self) -> List[TaskHistoryEntry]:
        if not self.history_path.exists():
            return []
        try:
            data = read_json_file(self.history_path)
        except (OSError, json.JSONDecodeError):
            return []
        repaired = repair_tree(data)
        if repaired != data:
            self.history_path.write_text(
                json.dumps(repaired, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            data = repaired
        if not isinstance(data, list):
            return []
        return [TaskHistoryEntry.from_dict(item) for item in data if isinstance(item, dict)]

    def save(self, entries: List[TaskHistoryEntry]) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [entry.to_dict() for entry in entries[: self.max_entries]]
        self.history_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def append(self, entry: TaskHistoryEntry) -> List[TaskHistoryEntry]:
        entries = self.load()
        entries.insert(0, entry)
        entries = entries[: self.max_entries]
        self.save(entries)
        return entries
