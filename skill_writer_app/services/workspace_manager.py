from __future__ import annotations

from pathlib import Path
from typing import List, Optional


class WorkspaceManager:
    GLOBAL_DIR_NAME = "_global"
    OPERATIONAL_DIR_NAMES = {
        GLOBAL_DIR_NAME,
        "excel_backup",
        "excel_test_copy",
        "excel_reorder_test_copy",
        "excel_writeback_test",
        "__pycache__",
        ".pycache_tmp",
        "_battle_knowledge_cache",
    }
    PRIMARY_PAYLOAD_NAME = "temp_excel_payload.json"
    TASK_DIRS = ("config", "scripts", "tests", "docs", "repair", "logs")
    LEGACY_TASK_FILES = {
        "temp_excel_payload.json": "config",
        "temp_skill_config.lua": "config",
        "test_skill_temp.lua": "tests",
        "test_runtime_validation.lua": "tests",
        "IMPLEMENTATION.md": "docs",
        "_repair_chat.md": "repair",
    }
    LEGACY_TASK_DIRS = {
        "_repair_attachments": "repair/attachments",
        "_repair_clipboard": "repair/clipboard",
    }
    ARTIFACT_PATTERNS = (
        "temp_excel_payload.json",
        "*.lua",
        "*.json",
        "*.md",
        "*.txt",
        "*.xlsx",
        "*.log",
    )

    def temp_workspace_path(self, workspace_root: str) -> Optional[Path]:
        battle_root = self.resolve_battle_root(workspace_root)
        if not battle_root:
            return None
        return battle_root / "temp_skill_workspace"

    def resolve_battle_root(self, workspace_root: str) -> Optional[Path]:
        root = Path(workspace_root)
        if not root.exists():
            return None

        direct_candidates = [
            root / "xgame_server" / "service" / "battle",
            root / "service" / "battle",
            root,
        ]
        for candidate in direct_candidates:
            if (candidate / "module").exists() and (candidate / "service").exists():
                return candidate

        matches = list(root.rglob("xgame_server/service/battle"))
        if matches:
            return matches[0]
        nested_battle = list(root.rglob("service/battle"))
        if nested_battle:
            return nested_battle[0]
        return None

    def default_payload_path(self, workspace_root: str) -> str:
        temp_root = self.temp_workspace_path(workspace_root)
        if not temp_root:
            return ""
        return str(temp_root / "temp_excel_payload.json")

    def default_temp_copy_dir(self, workspace_root: str, folder_name: str) -> str:
        temp_root = self.temp_workspace_path(workspace_root)
        if not temp_root:
            return ""
        return str(self.global_workspace_dir(temp_root) / folder_name)

    def global_workspace_dir(self, temp_root: Path) -> Path:
        return temp_root / self.GLOBAL_DIR_NAME

    def global_artifact_path(self, workspace_root: str, folder_name: str) -> str:
        temp_root = self.temp_workspace_path(workspace_root)
        if not temp_root:
            return ""
        return str(self.global_workspace_dir(temp_root) / folder_name)

    def migrate_legacy_global_dirs(self, workspace_root: str) -> list[tuple[Path, Path]]:
        temp_root = self.temp_workspace_root(workspace_root)
        if not temp_root:
            return []

        global_root = self.global_workspace_dir(temp_root)
        global_root.mkdir(parents=True, exist_ok=True)

        moved: list[tuple[Path, Path]] = []
        for name in sorted(self.OPERATIONAL_DIR_NAMES - {self.GLOBAL_DIR_NAME, "__pycache__", ".pycache_tmp"}):
            source = temp_root / name
            target = global_root / name
            if not source.exists() or source == target:
                continue
            if target.exists():
                continue
            source.rename(target)
            moved.append((source, target))
        return moved

    def temp_workspace_root(self, workspace_root: str) -> Optional[Path]:
        temp_root = self.temp_workspace_path(workspace_root)
        if not temp_root:
            return None
        if temp_root.exists():
            return temp_root
        return None

    def belongs_to_temp_workspace(self, path_value: str | Path, workspace_root: str) -> bool:
        temp_root = self.temp_workspace_path(workspace_root)
        if not temp_root:
            return False
        candidate = Path(path_value).expanduser()
        try:
            candidate = candidate.resolve()
            temp_root = temp_root.resolve()
        except OSError:
            return False
        try:
            candidate.relative_to(temp_root)
            return True
        except ValueError:
            return False

    def find_payload_candidates(self, workspace_root: str) -> List[Path]:
        temp_root = self.temp_workspace_root(workspace_root)
        if not temp_root:
            return []

        seen = set()
        candidates: List[Path] = []
        for pattern in ("temp_excel_payload.json", "*payload*.json"):
            for path in temp_root.rglob(pattern):
                if not path.is_file():
                    continue
                try:
                    resolved = str(path.resolve())
                except OSError:
                    resolved = str(path)
                if resolved in seen:
                    continue
                seen.add(resolved)
                candidates.append(path)

        return sorted(candidates, key=self._payload_sort_key, reverse=True)

    def find_recent_task_dirs(self, workspace_root: str) -> List[Path]:
        temp_root = self.temp_workspace_root(workspace_root)
        if not temp_root:
            return []

        dirs = [
            path
            for path in temp_root.iterdir()
            if path.is_dir() and path.name.lower() not in self.OPERATIONAL_DIR_NAMES
        ]
        return sorted(dirs, key=self._task_dir_sort_key, reverse=True)

    def find_primary_payload_for_dir(self, task_dir: str | Path) -> Optional[Path]:
        root = Path(task_dir)
        if not root.exists() or not root.is_dir():
            return None

        primary = root / "config" / self.PRIMARY_PAYLOAD_NAME
        if primary.is_file():
            return primary

        primary = root / self.PRIMARY_PAYLOAD_NAME
        if primary.is_file():
            return primary

        payloads = [path for path in root.glob("*payload*.json") if path.is_file()]
        if not payloads:
            return None
        return sorted(payloads, key=self._payload_sort_key, reverse=True)[0]

    def find_task_artifacts(self, task_dir: str | Path, limit: int = 20) -> List[Path]:
        root = Path(task_dir)
        if not root.exists() or not root.is_dir():
            return []

        seen = set()
        candidates: List[Path] = []
        for pattern in self.ARTIFACT_PATTERNS:
            for path in root.rglob(pattern):
                if not path.is_file():
                    continue
                try:
                    resolved = str(path.resolve())
                except OSError:
                    resolved = str(path)
                if resolved in seen:
                    continue
                seen.add(resolved)
                candidates.append(path)

        sorted_candidates = sorted(candidates, key=self._safe_mtime, reverse=True)
        return sorted_candidates[:limit]

    def canonical_task_file(self, task_dir: str | Path, file_name: str) -> Path:
        root = Path(task_dir)
        folder = self.LEGACY_TASK_FILES.get(file_name, "")
        return root / folder / file_name if folder else root / file_name

    def ensure_task_layout(self, task_dir: str | Path, migrate_legacy: bool = True) -> list[tuple[Path, Path]]:
        root = Path(task_dir)
        if not root.exists() or not root.is_dir():
            return []
        for folder in self.TASK_DIRS:
            (root / folder).mkdir(parents=True, exist_ok=True)

        moved: list[tuple[Path, Path]] = []
        if not migrate_legacy:
            return moved
        for file_name, folder in self.LEGACY_TASK_FILES.items():
            source = root / file_name
            target = root / folder / file_name
            if source.exists() and not target.exists():
                source.rename(target)
                moved.append((source, target))
        for old_name, target_rel in self.LEGACY_TASK_DIRS.items():
            source = root / old_name
            target = root / target_rel
            if source.exists() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)
                moved.append((source, target))
        return moved

    def _safe_mtime(self, path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _task_dir_sort_key(self, path: Path) -> tuple[float, int, float, str]:
        payload = self.find_primary_payload_for_dir(path)
        payload_mtime = self._safe_mtime(payload) if payload else 0.0
        activity_mtime = max(payload_mtime, self._task_dir_activity_mtime(path), self._safe_mtime(path))
        return (activity_mtime, self._task_dir_score(path), payload_mtime, path.name.lower())

    def _payload_sort_key(self, path: Path) -> tuple[float, int, int, str]:
        parent_score = self._task_dir_score(path.parent)
        primary_bonus = 1 if path.name == self.PRIMARY_PAYLOAD_NAME else 0
        return (self._safe_mtime(path), primary_bonus, parent_score, path.name.lower())

    def _task_dir_activity_mtime(self, path: Path) -> float:
        latest = 0.0
        for name in (
            "config/temp_excel_payload.json",
            self.PRIMARY_PAYLOAD_NAME,
            "config/temp_skill_config.lua",
            "temp_skill_config.lua",
            "tests/test_skill_temp.lua",
            "test_skill_temp.lua",
            "docs/IMPLEMENTATION.md",
            "IMPLEMENTATION.md",
            "tests/test_runtime_validation.lua",
            "test_runtime_validation.lua",
        ):
            latest = max(latest, self._safe_mtime(path / name))
        return latest

    def _task_dir_score(self, path: Path) -> int:
        if not path.exists() or not path.is_dir():
            return -999

        score = 0
        name = path.name.lower()
        if name in self.OPERATIONAL_DIR_NAMES:
            score -= 200

        if (path / "config" / self.PRIMARY_PAYLOAD_NAME).is_file() or (path / self.PRIMARY_PAYLOAD_NAME).is_file():
            score += 140
        if (path / "config" / "temp_skill_config.lua").is_file() or (path / "temp_skill_config.lua").is_file():
            score += 90
        if (path / "docs" / "IMPLEMENTATION.md").is_file() or (path / "IMPLEMENTATION.md").is_file():
            score += 60
        if (path / "tests" / "test_skill_temp.lua").is_file() or (path / "test_skill_temp.lua").is_file():
            score += 50

        direct_lua = len([item for item in path.glob("*.lua") if item.is_file()])
        direct_json = len([item for item in path.glob("*.json") if item.is_file()])
        direct_md = len([item for item in path.glob("*.md") if item.is_file()])
        direct_xlsx = len([item for item in path.glob("*.xlsx") if item.is_file()])

        score += min(direct_lua, 5) * 12
        score += min(direct_json, 3) * 10
        score += min(direct_md, 3) * 6

        if direct_xlsx > 0 and direct_lua == 0 and direct_json == 0:
            score -= 60

        try:
            if not any(path.iterdir()):
                score -= 20
        except OSError:
            score -= 20

        return score
