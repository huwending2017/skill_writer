from __future__ import annotations

import filecmp
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SkillSyncResult:
    name: str
    source: Path
    destination: Path
    action: str


class BundledSkillService:
    def __init__(self, app_base_dir: Path | None = None) -> None:
        self.app_base_dir = app_base_dir or self.resolve_app_base_dir()

    @staticmethod
    def resolve_app_base_dir() -> Path:
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            # Development builds run from <project>/dist/SkillWriterDesktop.
            # Keep user state in <project> so rebuilding dist does not erase
            # history/settings/active workflow state.
            if exe_dir.name == "SkillWriterDesktop" and exe_dir.parent.name == "dist":
                project_root = exe_dir.parent.parent
                if (project_root / "app.py").exists() and (project_root / "skill_writer_app").exists():
                    return project_root
            return exe_dir
        return Path(__file__).resolve().parents[2]

    @staticmethod
    def codex_home() -> Path:
        configured = os.environ.get("CODEX_HOME")
        if configured:
            return Path(configured).expanduser().resolve()
        return Path.home() / ".codex"

    def bundled_skills_dir(self) -> Path:
        candidates = [
            self.app_base_dir / "bundled_skills",
            self.app_base_dir / "_internal" / "bundled_skills",
        ]
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(Path(meipass) / "bundled_skills")

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def installed_skills_dir(self) -> Path:
        return self.codex_home() / "skills"

    def installed_skill_path(self, skill_name: str) -> Path:
        return self.installed_skills_dir() / skill_name

    def sync_all(self) -> list[SkillSyncResult]:
        source_root = self.bundled_skills_dir()
        if not source_root.exists():
            return []

        results: list[SkillSyncResult] = []
        self.installed_skills_dir().mkdir(parents=True, exist_ok=True)

        for source in sorted(source_root.iterdir()):
            if not source.is_dir() or not (source / "SKILL.md").exists():
                continue
            destination = self.installed_skill_path(source.name)
            action = self.sync_one(source, destination)
            results.append(SkillSyncResult(source.name, source, destination, action))

        return results

    def sync_one(self, source: Path, destination: Path) -> str:
        if destination.exists() and self.same_tree(source, destination):
            return "unchanged"

        temp_destination = destination.with_name(f"{destination.name}.tmp_sync")
        if temp_destination.exists():
            shutil.rmtree(temp_destination)

        shutil.copytree(
            source,
            temp_destination,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
        )

        if destination.exists():
            shutil.rmtree(destination)
            action = "updated"
        else:
            action = "installed"

        temp_destination.replace(destination)
        return action

    def same_tree(self, left: Path, right: Path) -> bool:
        if not right.exists():
            return False

        comparison = filecmp.dircmp(left, right, ignore=["__pycache__", ".DS_Store"])
        if comparison.left_only or comparison.right_only or comparison.funny_files:
            return False

        _, mismatch, errors = filecmp.cmpfiles(
            left,
            right,
            comparison.common_files,
            shallow=False,
        )
        if mismatch or errors:
            return False

        return all(self.same_tree(left / name, right / name) for name in comparison.common_dirs)
