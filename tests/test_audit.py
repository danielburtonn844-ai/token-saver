import json
import os
import tempfile
import unittest

from token_saver.audit import audit_text, iter_files, render, render_totals, report_to_json


class TestAudit(unittest.TestCase):
    def test_empty(self):
        r = audit_text("x", "")
        self.assertEqual(r.lines, 0)
        self.assertEqual(r.tokens, 0)
        self.assertEqual(r.est_waste_tokens, 0)

    def test_dup_lines(self):
        text = "\n".join(["same"] * 50 + [f"uniq {i}" for i in range(50)])
        r = audit_text("x", text)
        self.assertEqual(r.dup_lines, 49)
        self.assertGreater(r.est_waste_tokens, 0)

    def test_no_dup(self):
        text = "\n".join(f"line {i}" for i in range(100))
        r = audit_text("x", text)
        self.assertEqual(r.dup_lines, 0)

    def test_progress_and_long(self):
        text = "[####   ] 50%\n" * 10 + "x" * 900 + "\n"
        r = audit_text("x", text)
        self.assertEqual(r.progress_lines, 10)
        self.assertEqual(r.long_lines, 1)

    def test_json_schema(self):
        payload = json.loads(report_to_json([audit_text("a", "hello\n" * 10)]))
        self.assertEqual(payload["totals"]["files"], 1)
        self.assertIn("cjk_weight", payload["estimator"])
        self.assertEqual(payload["files"][0]["name"], "a")

    def test_render(self):
        out = render(audit_text("a", "x\n" * 10))
        self.assertIn("估算", out)
        total = render_totals([audit_text("a", "x\n" * 10)])
        self.assertIn("合计", total)


class TestIterFiles(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "sub"))
        os.makedirs(os.path.join(self.root, ".git"))
        os.makedirs(os.path.join(self.root, "node_modules"))
        with open(os.path.join(self.root, "a.py"), "w") as fh:
            fh.write("print(1)\n")
        with open(os.path.join(self.root, "sub", "b.js"), "w") as fh:
            fh.write("console.log(1)\n")
        with open(os.path.join(self.root, "c.bin"), "wb") as fh:
            fh.write(b"\x00\x01\x02" * 100)
        with open(os.path.join(self.root, ".git", "d.py"), "w") as fh:
            fh.write("x\n")
        with open(os.path.join(self.root, "node_modules", "e.js"), "w") as fh:
            fh.write("x\n")

    def names(self, **kw):
        return sorted(os.path.basename(p) for p in iter_files(self.root, **kw))

    def test_default(self):
        self.assertEqual(self.names(), ["a.py", "b.js"])

    def test_skip_dirs(self):
        got = self.names()
        self.assertNotIn("d.py", got)
        self.assertNotIn("e.js", got)

    def test_ext_filter(self):
        self.assertEqual(self.names(exts=["py"]), ["a.py"])

    def test_exclude(self):
        self.assertEqual(self.names(exclude=["*.js"]), ["a.py"])

    def test_max_files(self):
        self.assertEqual(len(self.names(max_files=1)), 1)


if __name__ == "__main__":
    unittest.main()
