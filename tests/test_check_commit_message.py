import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location(
    'ccm', pathlib.Path(__file__).resolve().parent.parent / 'scripts/check_commit_message.py')
ccm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ccm)
PAIRS = ccm.load_pairs()


def errs(msg):
    return ccm.check_message(msg, PAIRS)


class CommitMessageTests(unittest.TestCase):
    def test_valid(self):
        self.assertFalse(errs('📄 docs(networks): record the themed error pages\n\nWhy.'))
        self.assertFalse(errs('\U0001f6e0\ufe0f fix(higress): x'))
        self.assertFalse(errs('\u2b06\ufe0f dep(helm): bump x to 1'))
        self.assertFalse(errs('🔧 chore(helm/chart): vendor foo 1.2.3'))


    def test_requires_variation_selector(self):
        self.assertTrue(errs('\U0001f6e0 fix(higress): x'))
        self.assertTrue(errs('\u2b06 dep(helm): bump x to 1'))
        self.assertIn('U+FE0F', errs('\u2b06 dep(helm): bump x to 1')[0])

    def test_bad_emoji_and_type(self):
        self.assertTrue(errs('🔥 chore(ingress): remove it'))
        self.assertTrue(errs('🔧 oops(ingress): remove it'))


    def test_format(self):
        self.assertTrue(errs('📄 docs: no domain'))
        self.assertTrue(errs('📄 docs(Networks): upper domain'))
        self.assertTrue(errs('📄 docs(networks): Upper title'))
        self.assertTrue(errs('📄 docs(networks): ok\nno blank line'))


    def test_forbidden_lines(self):
        self.assertTrue(errs('📄 docs(a): b\n\nClaude-Session: https://claude.ai/code/session_1'))
        self.assertTrue(errs('📄 docs(a): b\n\nCo-authored-by: Claude <noreply@anthropic.com>'))
        self.assertFalse(errs('📄 docs(a): b\n\nCo-authored-by: Jane <jane@example.com>'))


    def test_skips_and_comments(self):
        self.assertFalse(errs('Merge pull request #1 from x/y'))
        self.assertFalse(errs('# comment\n📄 docs(a): b'))


if __name__ == '__main__':
    unittest.main()
