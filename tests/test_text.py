import os
import tempfile
import unittest

from token_saver.text import (
    ANSI,
    CJK,
    clean_ansi,
    est_tokens,
    looks_binary,
    read_bytes,
    read_text,
    split_lines,
)


class TestEstimator(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(est_tokens(""), 0)

    def test_ascii_monotonic(self):
        self.assertLess(est_tokens("a" * 10), est_tokens("a" * 20))

    def test_cjk_heavier_than_latin(self):
        # 同样字符数，中文更贵
        self.assertGreater(est_tokens("中" * 20), est_tokens("a" * 20))

    def test_positive_for_single_char(self):
        self.assertGreaterEqual(est_tokens("x"), 1)

    def test_no_float_regression(self):
        self.assertIsInstance(est_tokens("混合 mixed 文本"), int)

    def test_cjk_regex_covers_fullwidth(self):
        self.assertTrue(CJK.search("，。！"))
        self.assertTrue(CJK.search("汉字"))
        self.assertFalse(CJK.search("plain ascii"))


class TestAnsi(unittest.TestCase):
    def test_csi_color(self):
        self.assertEqual(clean_ansi("\x1b[31mred\x1b[0m"), "red")

    def test_csi_private_mode(self):
        self.assertEqual(clean_ansi("\x1b[?25lhidden\x1b[?25h"), "hidden")

    def test_osc_title(self):
        self.assertEqual(clean_ansi("\x1b]0;title\x07text"), "text")

    def test_ansi_pattern_exists(self):
        self.assertTrue(ANSI.search("\x1b[1;32m"))


class TestBinary(unittest.TestCase):
    def test_text_not_binary(self):
        self.assertFalse(looks_binary("hello 世界\n".encode()))

    def test_nul_is_binary(self):
        self.assertTrue(looks_binary(b"abc\x00def"))

    def test_binary_noise(self):
        self.assertTrue(looks_binary(bytes(range(256))))

    def test_empty_not_binary(self):
        self.assertFalse(looks_binary(b""))


class TestRead(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, data):
        path = os.path.join(self.tmp, "x.bin")
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def test_bad_utf8_replaced(self):
        path = self._write(b"ok \xff\xfe end")
        text, cut = read_text(path)
        self.assertFalse(cut)
        self.assertIn("ok", text)
        self.assertIn("\ufffd", text)

    def test_bom_stripped(self):
        path = self._write(b"\xef\xbb\xbfhello")
        text, _ = read_text(path)
        self.assertEqual(text, "hello")

    def test_truncation_flag(self):
        path = self._write(b"a" * 100)
        data, cut = read_bytes(path, max_bytes=10)
        self.assertTrue(cut)
        self.assertEqual(len(data), 10)

    def test_crlf(self):
        path = self._write(b"a\r\nb\r\n")
        text, _ = read_text(path)
        self.assertEqual(split_lines(text), ["a", "b"])

    def test_missing_file_raises(self):
        with self.assertRaises(OSError):
            read_text(os.path.join(self.tmp, "nope"))


if __name__ == "__main__":
    unittest.main()
