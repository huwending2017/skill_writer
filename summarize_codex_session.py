from __future__ import annotations

import argparse
import json
from pathlib import Path

from skill_writer_app.services.session_handoff import SessionHandoffService


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Codex session jsonl files into JSON and Markdown.")
    parser.add_argument("--session-dir", required=True, help="Directory that contains rollout *.jsonl files.")
    parser.add_argument("--output-dir", required=True, help="Directory for generated handoff artifacts.")
    args = parser.parse_args()

    service = SessionHandoffService()
    summaries = service.summarize_directory(args.session_dir)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "session_summary.json"
    md_path = output_dir / "session_summary.md"

    json_path.write_text(
        json.dumps([item.to_dict() for item in summaries], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(service.render_markdown(summaries), encoding="utf-8")

    print(f"Generated {json_path}")
    print(f"Generated {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
