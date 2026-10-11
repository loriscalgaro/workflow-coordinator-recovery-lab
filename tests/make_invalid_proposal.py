"""Create intentionally INVALID proposals for the demo. Never use with real data."""
import argparse
import json
import subprocess
from pathlib import Path

STATE = "state/workflows/demo.json"


def git(*args):
    return subprocess.check_output(["git", *args]).decode().strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, choices=["replay", "stale", "skip-revision"])
    parser.add_argument("--operation", default="op-test-999", help="Use a previously accepted operation for replay")
    args = parser.parse_args()
    root = Path(git("rev-parse", "--show-toplevel"))
    before = json.loads(git("show", "origin/main:" + STATE))
    out = dict(before)
    out["revision"] = before["revision"] + 1
    out["previous_commit"] = git("rev-parse", "origin/main")
    out["applied_operations"] = before["applied_operations"] + [args.operation]
    out["last_operation"] = args.operation
    out["note"] = "INVALID TEST: " + args.case
    if args.case == "stale":
        out["previous_commit"] = "0" * 40
    elif args.case == "skip-revision":
        out["revision"] += 1
    (root / STATE).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("Intentionally invalid test proposal created. Never merge:", args.case)


if __name__ == "__main__":
    main()
