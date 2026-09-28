"""Spec Studio's backend: prompt, fence stripping, and the build pipeline."""

import unittest

from danta.app.pipeline import build, strip_fences, verify_language
from danta.app.prompt import build_prompt, example_spec
from danta.spec import compile_spec


class Prompt(unittest.TestCase):
    def test_prompt_carries_the_language_and_ends_with_the_use_case(self):
        p = build_prompt()
        self.assertIn('## 8. Values', p)                        # the full language reference
        self.assertIn('Spec: danta/0.1', p)
        self.assertTrue(p.rstrip().endswith('USE CASE =========='))

    def test_prompt_example_obeys_its_own_rules(self):
        res = compile_spec(example_spec())
        self.assertTrue(res.ok, [str(e) for e in res.errors])
        self.assertEqual(res.intents, [])                      # rule 3: no prose values


class Pipeline(unittest.TestCase):
    def test_strip_fences(self):
        spec = 'Spec: danta/0.1\n# System: x\n'
        self.assertEqual(strip_fences(f'Sure! Here it is:\n```markdown\n{spec}```\nEnjoy.'), spec)
        self.assertEqual(strip_fences(f'Here you go.\n\n{spec}'), spec)
        self.assertEqual(strip_fences(spec), spec)

    def test_build_compiles_tests_and_verifies(self):
        r = build(f'```markdown\n{example_spec()}```')
        self.assertTrue(r['ok'])
        f = r['flows'][0]
        self.assertEqual(f['coverage'], 1.0)
        self.assertGreater(len(f['runs']), 2)
        self.assertTrue(all(s['line'] > 0 for s in f['steps']))
        self.assertEqual(set(r['project']), {'python', 'javascript', 'java'})
        self.assertIn('leave-desk/pyproject.toml', r['project']['python']['files'])
        self.assertIn('leave-desk/pom.xml', r['project']['java']['files'])
        self.assertIn('spring-boot-starter-web', r['project']['java']['files']['leave-desk/pom.xml'])
        self.assertEqual(verify_language(f'```markdown\n{example_spec()}```', 'python')['status'], 'verified')

    def test_every_example_builds(self):
        # every trigger source and step kind gets a flowchart label (topic triggers once crashed the Studio)
        import glob
        for path in sorted(glob.glob('danta/spec/examples/*.spec.md')):
            with self.subTest(path=path), open(path) as f:
                out = build(f.read().replace('the sum of the item amounts', '`sum(items.amount)`'))
                self.assertEqual(out['errors'], [])
                self.assertTrue(all(s['label'] for fl in out['flows'] for s in fl['steps']))

    def test_build_reports_errors_with_lines(self):
        r = build(example_spec().replace('Retry 2 times', 'Retry 8 times'))
        self.assertFalse(r['ok'])
        self.assertEqual([e['rule'] for e in r['errors']], ['retry-range'])
        self.assertIn('blocked', r['flows'][0])

    def test_build_holds_back_prose(self):
        with open('danta/spec/examples/order_checkout.spec.md') as f:
            r = build(f.read())
        self.assertTrue(r['ok'])
        self.assertEqual(len(r['intents']), 1)
        self.assertIn('logic model', r['flows'][0]['blocked'])
        self.assertEqual(r['project'], {})


if __name__ == '__main__':
    unittest.main()
