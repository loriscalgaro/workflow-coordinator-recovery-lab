"""Trusted-base pull_request_target handler: inspect PR as DATA, post status to head.

No candidate code is checked out, imported, evaluated, or executed.
The only side effect is the GitHub commit status; repository state changes through PR merge.
"""
import base64
import json
import os
import re
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from state_validator import GateError, loads_strict, validate_transition

EXPECTED_FILE = "state/workflows/demo.json"
CONTEXT = "canonical-gate/verified"
API = "https://api.github.com"


def api(method, route, token, payload=None):
    encoded = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = Request(
        API + route,
        data=encoded,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": "Bearer " + token,
            "User-Agent": "workflow-coordinator-poc-gate",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=20) as response:
            return json.load(response)
    except HTTPError as exc:
        raise GateError(f"GitHub API {method} {route.split('?')[0]} HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise GateError("GitHub API unavailable") from exc


def get_content(repo, ref, token):
    route = "/repos/" + repo + "/contents/" + EXPECTED_FILE + "?ref=" + quote(ref, safe="")
    x = api("GET", route, token)
    if x.get("type") != "file" or x.get("encoding") != "base64":
        raise GateError("unexpected GitHub content representation")
    try:
        return loads_strict(base64.b64decode("".join(x["content"].split()), validate=True))
    except (ValueError, KeyError) as exc:
        raise GateError("invalid GitHub file representation") from exc


def validate_pr(repo, number, token, expected_head):
    pr = api("GET", "/repos/" + repo + "/pulls/" + str(number), token)
    head = pr["head"]
    if pr["state"] != "open" or pr["draft"]:
        raise GateError("pull request is not an open, ready proposal")
    if pr["base"]["ref"] != "main" or head["repo"]["full_name"].casefold() != repo.casefold():
        raise GateError("only same-repository PRs to main are supported")
    if head["sha"] != expected_head:
        raise GateError("outdated PR event, refusing a status for different head")
    changed = api("GET", "/repos/" + repo + "/pulls/" + str(number) + "/files?per_page=100&page=1", token)
    if len(changed) != 1 or changed[0].get("filename") != EXPECTED_FILE or changed[0].get("status") != "modified":
        raise GateError("proposal must modify only " + EXPECTED_FILE)
    # Fail closed for pagination surprises.
    extra = api("GET", "/repos/" + repo + "/pulls/" + str(number) + "/files?per_page=100&page=2", token)
    if extra:
        raise GateError("unexpected additional changed files")

    canonical_ref = api("GET", "/repos/" + repo + "/git/ref/heads/main", token)
    main_sha = canonical_ref["object"]["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", main_sha):
        raise GateError("invalid main reference")
    canonical = get_content(repo, main_sha, token)
    candidate = get_content(repo, expected_head, token)
    accepted_op = validate_transition(canonical, candidate, main_sha)
    # Re-read canonical ref to close a known within-check TOCTOU window.
    latest_sha = api("GET", "/repos/" + repo + "/git/ref/heads/main", token)["object"]["sha"]
    if latest_sha != main_sha:
        raise GateError("main moved during validation; rerun is required")
    print("VERIFIED candidate op", accepted_op, "against canonical SHA", main_sha)
    return main_sha


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    number = int(os.environ["PR_NUMBER"])
    head = os.environ["PR_HEAD_SHA"]
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        print("invalid head SHA", file=sys.stderr)
        return 2
    ok, message = False, ""
    try:
        canonical_sha = validate_pr(repo, number, token, head)
        ok = True
        message = "Valid transition against " + canonical_sha[:12]
    except (GateError, KeyError, TypeError, ValueError) as exc:
        message = str(exc)[:130]
        print("REJECTED:", message, file=sys.stderr)
    # Post a GitHub-native status to the PR head SHA. Branch rule must require
    # this context AND require branches to be up to date before merging.
    payload = {"state": "success" if ok else "failure", "context": CONTEXT, "description": message[:140]}
    try:
        api("POST", "/repos/" + repo + "/statuses/" + head, token, payload)
    except GateError as exc:
        print("STATUS_PUBLICATION_FAILURE:", exc, file=sys.stderr)
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
