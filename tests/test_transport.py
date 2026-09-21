import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from shared import codex, gitlab
from registry import discover


class TransportTests(unittest.TestCase):
    def test_mr_review_full_access_skips_bubblewrap(self):
        spec = discover()['mr-review']
        self.assertEqual(spec.sandbox, 'danger-full-access')
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'review.json'
            output.write_text('{"decision": "abstain"}')
            with patch.object(codex.sys, 'platform', 'linux'), patch.object(codex.process, 'run') as run:
                review = codex.execute(repo=Path(directory), prompt='review',
                                       schema=Path('schema'), output=output, sandbox=spec.sandbox)
            run.assert_called_once()
            args = run.call_args.args[0]
            self.assertEqual(args[:2], ['codex', 'exec'])
            self.assertEqual(args[args.index('--sandbox') + 1], 'danger-full-access')
            self.assertIn('approval_policy="never"', args)
            self.assertEqual(review['decision'], 'abstain')

    def test_json_payloads_declare_content_type(self):
        for payload, method in (({'body': 'Review'}, None), ({}, None), ({'x': 1}, 'PUT')):
            with self.subTest(payload=payload, method=method):
                with patch.object(gitlab.process, 'run', return_value=subprocess.CompletedProcess([], 0, '{}')) as run:
                    gitlab.api('example.com', 'endpoint', payload, method=method)
                args = run.call_args.args[0]
                self.assertEqual(args[args.index('--header') + 1], 'Content-Type: application/json')
                self.assertEqual(args[args.index('--method') + 1], method or 'POST')
                self.assertEqual(json.loads(run.call_args.kwargs['input']), payload)

    def test_get_has_no_body(self):
        with patch.object(gitlab.process, 'run', return_value=subprocess.CompletedProcess([], 0, '[]')) as run:
            self.assertEqual(gitlab.api('example.com', 'endpoint'), [])
        self.assertNotIn('--input', run.call_args.args[0])
        self.assertIsNone(run.call_args.kwargs['input'])

    def test_blocked_sandbox_never_starts_model(self):
        for failure in (FileNotFoundError('bwrap'), subprocess.CalledProcessError(1, ['bwrap'], stderr='No permissions to create a new namespace')):
            with self.subTest(failure=failure), patch.object(codex.sys, 'platform', 'linux'):
                with patch.object(codex.process, 'run', side_effect=failure) as run:
                    with self.assertRaisesRegex(ValueError, 'before calling Codex'):
                        codex.execute(repo=Path('/tmp'), prompt='review', schema=Path('schema'), output=Path('missing'))
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0][0], 'bwrap')

    def test_successful_sandbox_probe(self):
        with patch.object(codex.sys, 'platform', 'linux'), patch.object(codex.process, 'run') as run:
            codex.check_linux_sandbox(Path('/tmp'))
        self.assertIn('--unshare-user', run.call_args.args[0])
        self.assertEqual(run.call_args.args[0][-1], '/bin/true')


if __name__ == '__main__':
    unittest.main()
