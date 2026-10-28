"""CI guard: verifies that duplicate files match their canonical copies."""

import hashlib
import sys
from pathlib import Path

CANONICAL_COPIES: dict[str, list[str]] = {
    "rate_limiters/algorithms/05_gcra/app/lua/gcra.lua": [
        "rate_limiters/policies/04_failure_modes/app/lua/gcra.lua",
        "rate_limiters/policies/05_shadow_mode/app/lua/gcra.lua",
    ],
}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    mismatches = []
    root = Path(__file__).resolve().parent.parent

    for canonical_rel, copies in CANONICAL_COPIES.items():
        canonical_path = root / canonical_rel
        if not canonical_path.exists():
            continue

        canonical_digest = file_hash(canonical_path)
        for copy_rel in copies:
            copy_path = root / copy_rel
            if not copy_path.exists():
                continue

            copy_digest = file_hash(copy_path)
            if canonical_digest != copy_digest:
                mismatches.append(f"{copy_rel} drifted from canonical {canonical_rel}")

    if mismatches:
        print("ERROR: Drift detected in duplicate files:", file=sys.stderr)
        for m in mismatches:
            print(f"  - {m}", file=sys.stderr)
        return 1

    print("Check duplicates: OK (no drift detected)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
