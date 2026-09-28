"""Tests for indent_java (format.py) and the browser API (web.py)."""

import json
import textwrap
import unittest

from danta.codegen.format import indent_java

SIMPLE_SPEC = textwrap.dedent("""\
    Spec: danta/0.1

    # System: ping-service
    A minimal service.

    ## Flow: ping
    Intent: Health check.
    Trigger: POST /ping with msg str
    Mode: sync
    Steps:
    1. [Done] Respond with echo = msg.
""")


class IndentJava(unittest.TestCase):
    def _check(self, src, want):
        self.assertEqual(indent_java(textwrap.dedent(src)), textwrap.dedent(want))

    def test_flat_class(self):
        self._check(
            """\
            public class A {
            int x;
            }
            """,
            """\
            public class A {
              int x;
            }
            """,
        )

    def test_nested_methods(self):
        self._check(
            """\
            class A {
            void f() {
            return;
            }
            }
            """,
            """\
            class A {
              void f() {
                return;
              }
            }
            """,
        )

    def test_closing_brace_dedents_its_own_line(self):
        result = indent_java('class A {\nint x;\n}\n')
        lines = result.splitlines()
        self.assertEqual(lines[2], '}')            # closing brace at depth 0

    def test_empty_lines_preserved(self):
        src = 'class A {\n\nint x;\n}\n'
        result = indent_java(src)
        self.assertIn('\n\n', result)

    def test_string_literal_braces_ignored(self):
        src = 'class A {\nString s = "{}";\n}\n'
        result = indent_java(src)
        lines = result.splitlines()
        self.assertTrue(lines[1].startswith('  '))  # inside class, depth 1

    def test_line_comment_braces_ignored(self):
        # The { inside the comment must not increase depth; `int x;` stays at depth 1.
        src = 'class A {\n// {\nint x;\n}\n'
        result = indent_java(src)
        lines = result.splitlines()
        self.assertEqual(lines[1].strip(), '// {')  # comment content is unchanged
        self.assertTrue(lines[2].startswith('  '))  # x at depth 1, not 2

    def test_block_comment(self):
        src = 'class A {\n/* {\nstill comment\n*/\nint x;\n}\n'
        result = indent_java(src)
        lines = result.splitlines()
        self.assertTrue(lines[-2].startswith('  '))  # x at depth 1

    def test_empty_input(self):
        self.assertEqual(indent_java(''), '')


class WebAPI(unittest.TestCase):
    def setUp(self):
        import danta.web as web
        self.web = web

    def test_prompt_returns_nonempty_string(self):
        p = self.web.api_prompt()
        self.assertIsInstance(p, str)
        self.assertGreater(len(p), 100)

    def test_examples_is_valid_json_list(self):
        raw = self.web.api_examples()
        data = json.loads(raw)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_build_bad_spec_returns_errors(self):
        raw = self.web.api_build('not a spec')
        data = json.loads(raw)
        self.assertIn('errors', data)

    def test_build_valid_spec_returns_flows(self):
        raw = self.web.api_build(SIMPLE_SPEC)
        data = json.loads(raw)
        self.assertNotIn('fatal', data)

    def test_verify_returns_local_status(self):
        for lang in ('python', 'javascript', 'java'):
            with self.subTest(lang=lang):
                raw = self.web.api_verify(lang)
                data = json.loads(raw)
                self.assertEqual(data['status'], 'local')
                self.assertIn('command', data)
                self.assertTrue(data['command'])

    def test_project_valid_spec_returns_bytes(self):
        data = self.web.api_project(SIMPLE_SPEC, 'python')
        self.assertIsNotNone(data)
        self.assertIsInstance(data, (bytes, bytearray))
        self.assertGreater(len(data), 0)

    def test_project_bad_spec_returns_none(self):
        data = self.web.api_project('not a spec', 'python')
        self.assertIsNone(data)


if __name__ == '__main__':
    unittest.main()
