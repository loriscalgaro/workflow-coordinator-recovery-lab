"""Pure, dependency-free canonical transition checks. Never execute candidate content."""
import json
import re

FIELDS = {"schema", "workflow_id", "revision", "previous_commit", "last_operation", "applied_operations", "note"}
SHA = re.compile(r"^[0-9a-f]{40}$")
OP = re.compile(r"^[a-z][a-z0-9-]{2,39}$")
MAX_BYTES = 16_384
MAX_OPERATIONS = 100


class GateError(ValueError):
    pass


def loads_strict(raw):
    if len(raw) > MAX_BYTES:
        raise GateError("JSON exceeds 16 KiB")

    def no_duplicates(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise GateError("duplicate JSON property: " + key)
            out[key] = value
        return out

    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError("invalid JSON/UTF-8") from exc
    if not isinstance(result, dict):
        raise GateError("state must be an object")
    return result


def validate_shape(state):
    if set(state) != FIELDS:
        raise GateError("unexpected/missing state fields")
    if state["schema"] != "github-canonical-poc-v1" or state["workflow_id"] != "demo":
        raise GateError("wrong schema or workflow")
    if type(state["revision"]) is not int or not 0 <= state["revision"] <= MAX_OPERATIONS:
        raise GateError("invalid revision")
    operations = state["applied_operations"]
    if not isinstance(operations, list) or len(operations) != state["revision"]:
        raise GateError("invalid operations length")
    if not all(isinstance(op, str) and OP.fullmatch(op) for op in operations):
        raise GateError("invalid operation identifier")
    if len(operations) != len(set(operations)):
        raise GateError("replayed operation identifier")
    if not isinstance(state["note"], str) or not 1 <= len(state["note"]) <= 160:
        raise GateError("note must contain 1-160 characters")
    if state["revision"] == 0:
        if state["previous_commit"] is not None or state["last_operation"] is not None or operations:
            raise GateError("invalid genesis")
    else:
        if not isinstance(state["previous_commit"], str) or not SHA.fullmatch(state["previous_commit"]):
            raise GateError("invalid previous commit")
        if state["last_operation"] != operations[-1]:
            raise GateError("last operation does not match journal")


def validate_transition(before, after, main_sha):
    validate_shape(before)
    validate_shape(after)
    if not isinstance(main_sha, str) or not SHA.fullmatch(main_sha):
        raise GateError("invalid authoritative main SHA")
    if after["revision"] != before["revision"] + 1:
        raise GateError("revision must increment by exactly one")
    if after["previous_commit"] != main_sha:
        raise GateError("STALE_PREDECESSOR: proposal does not bind to current main SHA")
    earlier = before["applied_operations"]
    later = after["applied_operations"]
    if later[:-1] != earlier or len(later) != len(earlier) + 1:
        raise GateError("operation journal must append exactly one entry")
    if later[-1] in earlier:
        raise GateError("REPLAY: operation was already accepted")
    return later[-1]
