import os
import tempfile
import time
import unittest

from token_saver.compress import PROFILES, compress, detect_profile, load_input
from token_saver.text import est_tokens


def make_log(n=4000, errors=25):
    lines = []
    for i in range(n):
        if i % 37 == 0:
            lines.append(f"2026-01-01 00:00:{i % 60:02d} ERROR db.go:{i} connection refused host=10.0.0.{(i % 250) + 1}")
        elif i % 11 == 0:
            lines.append(f"npm WARN deprecated pkg-{i}@1.0.0: use something else")
        else:
            lines.append(f"2026-01-01 00:00:{i % 60:02d} INFO req id={i} status=200 path=/v1/items/{i}")
    # 额外制造 error，保证数量可控
    for k in range(errors):
        lines.insert(k * 7 + 3, f"ERROR unique failure code=E{k} at worker/{k}.py:{100 + k}")
    return lines


class TestCompressBasics(unittest.TestCase):
    def test_empty(self):
        r = compress([])
        self.assertEqual(r.text, "")
        self.assertEqual(r.stats.raw_lines, 0)

    def test_output_smaller(self):
        r = compress(make_log(), budget=800)
        self.assertLess(r.stats.out_tokens, r.stats.raw_tokens)
        self.assertGreater(r.stats.ratio, 0.5)

    def test_deterministic(self):
        a = compress(make_log(1000), budget=400).text
        b = compress(make_log(1000), budget=400).text
        self.assertEqual(a, b)

    def test_keeps_head_and_tail(self):
        lines = [f"line {i}" for i in range(500)]
        r = compress(lines, budget=10, head=3, tail=2, keep_errors=False)
        self.assertIn("line 0", r.text)
        self.assertIn("line 499", r.text)

    def test_ellipsis_marker(self):
        lines = [f"line {i}" for i in range(300)]
        r = compress(lines, budget=20, head=2, tail=2)
        self.assertIn("省略", r.text)

    def test_error_signatures_kept(self):
        """同类错误折叠成一个样本 + 次数，但错误种类一种都不能少。"""
        from token_saver.compress import signature
        lines = make_log(2000, errors=30)
        r = compress(lines, budget=150, head=2, tail=2)
        want = {signature(ln) for ln in lines if "ERROR" in ln}
        got = {signature(ln) for ln in r.text.splitlines()}
        self.assertTrue(want.issubset(got), "有错误种类被整类丢弃")

    def test_unique_errors_kept_verbatim(self):
        lines = [f"ERROR totally different {w} happened" for w in
                 ("disk", "network", "auth", "database", "cache")]
        r = compress(lines + [f"INFO line {i}" for i in range(500)], budget=100, head=1, tail=1)
        for ln in lines:
            self.assertIn(ln, r.text)

    def test_error_fold_annotated(self):
        lines = [f"ERROR db.go:{i} connection refused" for i in range(50)]
        r = compress(lines, budget=200, head=0, tail=0)
        self.assertIn("同型", r.text)
        self.assertIn("connection refused", r.text)

    def test_errors_can_be_dropped(self):
        lines = make_log(2000, errors=100)
        r = compress(lines, budget=50, head=1, tail=1, keep_errors=False, strict=True)
        self.assertLess(r.stats.out_tokens, est_tokens("\n".join(lines)))


class TestFolding(unittest.TestCase):
    def test_repeat_folding(self):
        lines = ["same line"] * 60 + [f"tail {i}" for i in range(20)]
        r = compress(lines, budget=500, head=1, tail=5)
        self.assertIn("重复 ×60", r.text)

    def test_same_kind_folding(self):
        lines = [f"GET /api/user/{i} 200 {i}ms" for i in range(200)]
        r = compress(lines, budget=300, head=2, tail=2)
        self.assertIn("同型", r.text)

    def test_folding_stops_at_three(self):
        lines = ["dup"] * 2 + ["x", "y", "z"]
        r = compress(lines, budget=1000, head=0, tail=0)
        self.assertEqual(r.text.count("dup"), 2)

    def test_traversal_like(self):
        lines = [f"drwxr-xr-x 2 root root {i} Jan 1 00:00 dir{i}" for i in range(500)]
        r = compress(lines, budget=200, head=3, tail=3)
        self.assertIn("同型", r.text)


class TestLimits(unittest.TestCase):
    def test_long_line_truncated(self):
        lines = ["x" * 5000, "short"]
        r = compress(lines, max_line=200, budget=500)
        self.assertIn("截断", r.text)
        self.assertLess(len(r.text.splitlines()[0]), 400)

    def test_max_line_zero_disables(self):
        lines = ["y" * 5000]
        r = compress(lines, max_line=0, budget=5000, head=1, tail=0)
        self.assertNotIn("截断", r.text)

    def test_negative_budget_rejected(self):
        with self.assertRaises(ValueError):
            compress(["a"], budget=-1)

    def test_negative_head_rejected(self):
        with self.assertRaises(ValueError):
            compress(["a"], head=-1)

    def test_absurd_max_line_rejected(self):
        with self.assertRaises(ValueError):
            compress(["a"], max_line=999999)

    def test_budget_zero_keeps_head_tail(self):
        lines = [f"l{i}" for i in range(100)]
        r = compress(lines, budget=0, head=4, tail=2, keep_errors=False)
        self.assertIn("l0", r.text)
        self.assertIn("l99", r.text)

    def test_strict_budget_respected(self):
        r = compress(make_log(5000), budget=300, strict=True)
        self.assertLessEqual(r.stats.out_tokens, 300)

    def test_strict_small_budget(self):
        r = compress(make_log(2000), budget=120, strict=True)
        self.assertLessEqual(r.stats.out_tokens, 120)


class TestQuality(unittest.TestCase):
    def test_unicode_preserved(self):
        lines = ["构建失败：找不到模块", "错误：权限不足", "完成"]
        r = compress(lines, budget=100)
        self.assertIn("构建失败", r.text)
        self.assertIn("权限不足", r.text)
        self.assertNotIn("\ufffd", r.text)

    def test_paths_survive(self):
        lines = [f"INFO step {i} /srv/app/src/module_{i}.py" for i in range(200)]
        r = compress(lines, budget=300)
        self.assertIn(".py", r.text)

    def test_no_content_invented(self):
        lines = [f"line-{i}" for i in range(50)]
        r = compress(lines, budget=2000, head=50, tail=0)
        out = [ln for ln in r.text.splitlines() if not ln.startswith("…[")]
        self.assertTrue(set(out).issubset(set(lines)))

    def test_all_blank_input(self):
        r = compress([""] * 100, budget=100)
        self.assertLessEqual(r.stats.out_tokens, 200)


class TestProfiles(unittest.TestCase):
    def test_profiles_registered(self):
        for name in ("default", "build", "test", "json", "traversal"):
            self.assertIn(name, PROFILES)

    def test_detect_json(self):
        sample = '{\n  "a": 1,\n  "b": 2,\n  "c": [1,2,3]\n}\n' * 30
        self.assertEqual(detect_profile(sample), "json")

    def test_detect_progress(self):
        sample = "[####      ] 40%\n" * 50 + "done\n"
        self.assertEqual(detect_profile(sample), "build")

    def test_detect_test_output(self):
        sample = "PASS tests/a.py\nPASS tests/b.py\nFAIL tests/c.py\n" * 20
        self.assertEqual(detect_profile(sample), "test")

    def test_detect_empty(self):
        self.assertEqual(detect_profile(""), "default")


class TestInput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_binary_rejected(self):
        path = os.path.join(self.tmp, "a.bin")
        with open(path, "wb") as fh:
            fh.write(b"\x00\x01\x02\xff" * 100)
        with self.assertRaises(ValueError):
            load_input(path)

    def test_ansi_removed(self):
        path = os.path.join(self.tmp, "a.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\x1b[31mERROR\x1b[0m boom\n")
        text, n, cut = load_input(path)
        self.assertNotIn("\x1b", text)
        self.assertGreater(n, 0)
        self.assertFalse(cut)

    def test_large_input_truncated(self):
        path = os.path.join(self.tmp, "big.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("x" * 5000)
        text, n, cut = load_input(path, max_bytes=1000)
        self.assertTrue(cut)
        self.assertEqual(n, 1000)

    def test_speed_on_big_log(self):
        lines = make_log(60000, errors=200)
        start = time.time()
        r = compress(lines, budget=1200)
        elapsed = time.time() - start
        self.assertLess(elapsed, 10, "6 万行压缩超过 10 秒")
        self.assertGreater(r.stats.ratio, 0.9)


if __name__ == "__main__":
    unittest.main()
