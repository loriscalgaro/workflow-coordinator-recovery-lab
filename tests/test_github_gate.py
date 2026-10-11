import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import github_gate
from state_validator import GateError
from test_validator import GENESIS, good

MAIN_SHA = 'a' * 40
HEAD_SHA = 'b' * 40
REPO = 'test-owner/test-repository'


def content(data):
    raw = json.dumps(data).encode('utf-8')
    b64 = base64.b64encode(raw).decode('ascii')
    return {'type': 'file', 'encoding': 'base64', 'content': b64[:5] + '\n' + b64[5:]}


def fake_api(method, route, token, payload=None):
    if '/pulls/7/files' in route:
        return [] if 'page=2' in route else [{'filename': github_gate.EXPECTED_FILE, 'status': 'modified'}]
    if '/pulls/7' in route:
        return {'state': 'open', 'draft': False, 'base': {'ref': 'main'},
                'head': {'sha': HEAD_SHA, 'repo': {'full_name': REPO}}}
    if '/git/ref/heads/main' in route:
        return {'object': {'sha': MAIN_SHA}}
    if '/contents/' in route:
        return content(good() if 'ref='+HEAD_SHA in route else GENESIS)
    raise AssertionError('Unexpected route: ' + route)


class TrustedAPITests(unittest.TestCase):
    def test_real_route_parsing_and_canonical_binding(self):
        with patch.object(github_gate, 'api', side_effect=fake_api):
            self.assertEqual(github_gate.validate_pr(REPO, 7, 'test-token', HEAD_SHA), MAIN_SHA)

    def test_missing_current_parent_is_rejected(self):
        def tampered(method, route, token, payload=None):
            data = fake_api(method, route, token, payload)
            if '/git/ref/heads/main' in route:
                return {'object': {'sha': 'c'*40}}
            return data
        with patch.object(github_gate, 'api', side_effect=tampered):
            with self.assertRaises(GateError):
                github_gate.validate_pr(REPO, 7, 'test-token', HEAD_SHA)

    def test_extra_pr_changes_fail_closed(self):
        def tampered(method, route, token, payload=None):
            if '/pulls/7/files' in route and 'page=2' not in route:
                return [{'filename': github_gate.EXPECTED_FILE, 'status': 'modified'},
                        {'filename': '.github/workflows/canonical-gate.yml', 'status': 'modified'}]
            return fake_api(method, route, token, payload)
        with patch.object(github_gate, 'api', side_effect=tampered):
            with self.assertRaises(GateError):
                github_gate.validate_pr(REPO, 7, 'test-token', HEAD_SHA)

    def test_fork_pr_blocked(self):
        def tampered(method, route, token, payload=None):
            if route.endswith('/pulls/7'):
                x = fake_api(method, route, token, payload)
                x['head']['repo']['full_name'] = 'fork-owner/fork'
                return x
            return fake_api(method, route, token, payload)
        with patch.object(github_gate, 'api', side_effect=tampered):
            with self.assertRaises(GateError):
                github_gate.validate_pr(REPO, 7, 'test-token', HEAD_SHA)

    def test_main_moves_mid_validation(self):
        count = [0]
        def tampered(method, route, token, payload=None):
            if '/git/ref/heads/main' in route:
                count[0] += 1
                return {'object': {'sha': MAIN_SHA if count[0] == 1 else 'c' * 40}}
            return fake_api(method, route, token, payload)
        with patch.object(github_gate, 'api', side_effect=tampered):
            with self.assertRaises(GateError):
                github_gate.validate_pr(REPO, 7, 'test-token', HEAD_SHA)

if __name__ == '__main__':
    unittest.main()
