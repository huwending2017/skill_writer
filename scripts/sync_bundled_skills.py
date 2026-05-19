from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skill_writer_app.services.bundled_skill_service import BundledSkillService


def main() -> int:
    service = BundledSkillService(PROJECT_ROOT)
    results = service.sync_all()
    if not results:
        print("[skills] no bundled skills found")
        return 0

    for result in results:
        print(f"[skills] {result.action}: {result.name} -> {result.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
