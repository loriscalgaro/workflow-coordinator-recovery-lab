"""Create one new state proposal from origin/main; does not commit or push."""
import argparse
import json
import subprocess
from pathlib import Path
from state_validator import validate_shape, validate_transition

FILE = "state/workflows/demo.json"


def git(*args):
    return subprocess.check_output(["git", *args]).decode().strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation", required=True, help="Unique id, e.g., op-a-001")
    parser.add_argument("--note", required=True, help="Public dummy test text")
    args = parser.parse_args()
    root = Path(git("rev-parse", "--show-toplevel"))
    path = root / FILE
    before = json.loads(git("show", "origin/main:" + FILE))
    current = json.loads(path.read_text(encoding="utf-8"))
    if current != before:
        raise SystemExit("The branch state does not match origin/main. Start from origin/main.")
    validate_shape(before)
    if args.operation in before["applied_operations"]:
        raise SystemExit("This operation ID was already committed. Replays are forbidden.")
    main_sha = git("rev-parse", "origin/main")
    candidate = dict(before)
    candidate["revision"] = before["revision"] + 1
    candidate["previous_commit"] = main_sha
    candidate["last_operation"] = args.operation
    candidate["applied_operations"] = before["applied_operations"] + [args.operation]
    candidate["note"] = args.note
    validate_transition(before, candidate, main_sha)
    path.write_text(json.dumps(candidate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Proposal created:", path, "revision", candidate["revision"], "base", main_sha)
    print("Commit and push your proposal branch; only GitHub can accept it into main.")


if __name__ == "__main__":
    main()
