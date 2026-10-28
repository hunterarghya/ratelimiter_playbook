"""Runs mypy across all subprojects independently.

Because each subproject uses 'app' as its top-level package name, running mypy
in a single invocation causes duplicate module name errors. This runner checks
each subproject independently and aggregates the exit codes.
"""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    targets: list[str] = []
    for parent in ["rate_limiters/algorithms", "rate_limiters/policies"]:
        parent_path = root / parent
        if parent_path.exists():
            for child in sorted(parent_path.iterdir()):
                if child.is_dir() and (child / "app").exists():
                    targets.append(str(child.relative_to(root)).replace("\\", "/"))

    targets.append("tools")
    exit_code = 0
    for target in targets:
        print(f"--> Typechecking {target}...")
        result = subprocess.run(["mypy", target], cwd=root)
        if result.returncode != 0:
            exit_code = result.returncode
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
