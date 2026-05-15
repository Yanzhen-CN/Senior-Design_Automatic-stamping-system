from __future__ import annotations

import argparse
import json

from .pipeline import preview_target, serial_result_to_dict, stamp_target
from .targeting import TargetInput


def main() -> None:
    parser = argparse.ArgumentParser(description="Automatic stamping CLI")
    parser.add_argument("--source", choices=["pixel", "relative_paper", "paper_preset"], default="pixel")
    parser.add_argument("--x", type=float)
    parser.add_argument("--y", type=float)
    parser.add_argument("--preset")
    parser.add_argument("--stamp", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    target = TargetInput(source=args.source, x=args.x, y=args.y, preset=args.preset)
    if args.stamp:
        preview, serial = stamp_target(target, dry_run=not args.live)
        payload = {
            "preview": preview.to_dict(),
            "serial": serial_result_to_dict(serial),
        }
    else:
        payload = preview_target(target).to_dict()
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

