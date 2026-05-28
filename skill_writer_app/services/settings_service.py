from __future__ import annotations

import json
from pathlib import Path

from skill_writer_app.models import AppSettings
from skill_writer_app.services.mojibake_repair import repair_tree
from skill_writer_app.services.text_decode import read_json_file


class SettingsService:
    def __init__(self, settings_path: Path) -> None:
        self.settings_path = settings_path

    def load(self) -> AppSettings:
        if not self.settings_path.exists():
            return AppSettings()
        try:
            data = read_json_file(self.settings_path)
        except json.JSONDecodeError:
            return AppSettings()
        repaired = repair_tree(data)
        if repaired != data:
            self.settings_path.write_text(
                json.dumps(repaired, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return AppSettings.from_dict(repaired)

    def save(self, settings: AppSettings) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
