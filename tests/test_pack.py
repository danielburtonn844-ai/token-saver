import json
import os
import tempfile
import unittest

from token_saver.pack import build_card, collect_files, to_json


class TestPack(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "src", "deep", "deeper"))
        files = {
            "README.md": "# 项目说明\n第二行\n",
            "src/app.py": "# 应用入口\nprint('hi')\n",
            "src/deep/x.js": "// 深层脚本\nlet a = 1;\n",
            "src/deep/deeper/y.txt": "plain text file here\n",
        }
        for rel, content in files.items():
            with open(os.path.join(self.root, rel), "w", encoding="utf-8") as fh:
                fh.write(content)
        with open(os.path.join(self.root, "logo.png"), "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        with open(os.path.join(self.root, "blob.dat"), "wb") as fh:
            fh.write(b"\x00\xff" * 500)

    def test_card_structure(self):
        card, entries = build_card(self.root)
        self.assertIn("索引卡", card)
        self.assertIn("| 文件 | 行数 | token | 摘要 |", card)
        self.assertTrue(entries)

    def test_binary_excluded(self):
        _, entries = build_card(self.root)
        paths = {e.path for e in entries}
        self.assertNotIn("logo.png", paths)
        self.assertNotIn("blob.dat", paths)

    def test_summary_from_comment(self):
        _, entries = build_card(self.root)
        by_path = {e.path: e for e in entries}
        self.assertIn("应用入口", by_path[os.path.join("src", "app.py")].summary)

    def test_binary_ext_and_magic(self):
        files = [os.path.basename(p) for p, _, _ in collect_files(self.root)]
        self.assertIn("app.py", files)
        self.assertNotIn("logo.png", files)
        self.assertNotIn("blob.dat", files)

    def test_depth_limit(self):
        files = [os.path.relpath(p, self.root) for p, _, _ in
                 collect_files(self.root, depth=2)]
        self.assertTrue(any(f.endswith("x.js") for f in files))
        self.assertFalse(any("deeper" in f for f in files))

    def test_include_exclude(self):
        inc = [os.path.basename(p) for p, _, _ in collect_files(self.root, include=["*.py"])]
        self.assertEqual(inc, ["app.py"])
        exc = [os.path.basename(p) for p, _, _ in collect_files(self.root, exclude=["*.py"])]
        self.assertNotIn("app.py", exc)

    def test_max_files(self):
        self.assertEqual(len(collect_files(self.root, max_files=2)), 2)

    def test_json_output(self):
        card, entries = build_card(self.root)
        payload = json.loads(to_json(self.root, entries))
        self.assertEqual(payload["totals"]["files"], len(entries))
        self.assertGreater(payload["files"][0]["lines"], 0)

    def test_card_token_note(self):
        card, _ = build_card(self.root)
        self.assertIn("本卡估算", card)


if __name__ == "__main__":
    unittest.main()
