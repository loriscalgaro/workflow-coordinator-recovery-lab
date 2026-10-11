"""Detect nonconforming main pushes after merge. Does not authorize merges."""
import json
import subprocess
from state_validator import validate_transition

STATE = "state/workflows/demo.json"


def git(*args):
    return subprocess.check_output(["git", *args]).decode().strip()


def main():
    sha = git("rev-parse", "HEAD")
    try:
        parent = git("rev-parse", "HEAD^")
    except subprocess.CalledProcessError:
        print("Genesis commit:", sha)
        return
    paths = git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()
    if paths != [STATE]:
        raise SystemExit("CANONICAL_TAMPER: only state file may change after genesis, got " + str(paths))
    old = json.loads(git("show", parent + ":" + STATE))
    new = json.loads(git("show", "HEAD:" + STATE))
    op = validate_transition(old, new, parent)
    print("ACCEPTED CANONICAL COMMIT:", sha, "operation:", op)


if __name__ == "__main__":
    main()
