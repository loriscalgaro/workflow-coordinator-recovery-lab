import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from state_validator import GateError, loads_strict, validate_shape, validate_transition

BASE_SHA = "a" * 40
GENESIS = {"schema": "github-canonical-poc-v1", "workflow_id": "demo", "revision": 0,
           "previous_commit": None, "last_operation": None, "applied_operations": [], "note": "GENESIS"}


def good():
    next_state = copy.deepcopy(GENESIS)
    next_state.update(revision=1, previous_commit=BASE_SHA, last_operation="op-a-001",
                      applied_operations=["op-a-001"], note="First")
    return next_state


class ValidatorTests(unittest.TestCase):
    def rejected(self, before, after, sha=BASE_SHA):
        with self.assertRaises(GateError):
            validate_transition(before, after, sha)

    def test_genesis(self):
        validate_shape(GENESIS)

    def test_one_valid_transition(self):
        self.assertEqual(validate_transition(GENESIS, good(), BASE_SHA), "op-a-001")

    def test_stale_sha(self):
        self.rejected(GENESIS, good(), "b" * 40)

    def test_missing_journal(self):
        item = good(); item["applied_operations"] = []
        self.rejected(GENESIS, item)

    def test_duplicate_operation(self):
        old = good(); item = copy.deepcopy(old)
        item.update(revision=2, last_operation="op-a-001", applied_operations=["op-a-001", "op-a-001"])
        self.rejected(old, item)

    def test_changed_prior_operation(self):
        old = good(); item = copy.deepcopy(old)
        item.update(revision=2, last_operation="op-b-002", applied_operations=["op-x-001", "op-b-002"])
        self.rejected(old, item)

    def test_skip_revision(self):
        item = good(); item["revision"] = 2
        self.rejected(GENESIS, item)

    def test_extra_field(self):
        item = good(); item["admin"] = True
        self.rejected(GENESIS, item)

    def test_boolean_revision(self):
        item = good(); item["revision"] = True
        self.rejected(GENESIS, item)

    def test_invalid_op(self):
        item = good(); item["last_operation"] = "../../bad"; item["applied_operations"] = ["../../bad"]
        self.rejected(GENESIS, item)

    def test_duplicate_json_key(self):
        with self.assertRaises(GateError):
            loads_strict(b'{"revision":1,"revision":2}')

    def test_invalid_encoding(self):
        with self.assertRaises(GateError):
            loads_strict(b'\xff')

    def test_big_input(self):
        with self.assertRaises(GateError):
            loads_strict(b' ' * 20_000)


if __name__ == "__main__":
    unittest.main()
