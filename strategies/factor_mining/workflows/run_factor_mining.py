"""Run governed factor mining: init, screening, record, freeze, or sealed final."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from strategies.factor_mining.research import (
    result_to_json,
    run_factor_mining,
    write_example_brief,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", required=True, type=Path, help="ResearchBrief JSON path")
    parser.add_argument(
        "--phase", required=True, choices=("init", "screening", "record", "freeze", "final")
    )
    parser.add_argument("--object", type=Path, help="ReviewReport or PoolDecision JSON for record")
    parser.add_argument("--approve", default="", help="Comma-separated factor_id list for freeze")
    parser.add_argument("--write", action="store_true", help="Required by final")
    parser.add_argument("--overwrite", action="store_true", help="Let init replace --brief")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--data-root", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.phase == "init":
        brief = write_example_brief(args.brief, data_root=args.data_root, overwrite=args.overwrite)
        print(
            json.dumps(
                {
                    "phase": "init",
                    "brief": str(args.brief),
                    "brief_id": brief.brief_id,
                    "brief_hash": brief.content_hash,
                    "data_version": brief.data_version,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    approve = tuple(item.strip() for item in args.approve.split(",") if item.strip())
    result = run_factor_mining(
        brief=args.brief,
        phase=args.phase,
        data_root=args.data_root,
        output_dir=args.output_dir,
        approve=approve,
        record_object=json.loads(args.object.read_text(encoding="utf-8")) if args.object else None,
        write=args.write,
    )
    print(result_to_json(result))


if __name__ == "__main__":
    main()
