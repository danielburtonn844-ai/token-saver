import json
import os
import tempfile
import unittest

from token_saver.handover import TEMPLATE, check, create

GOOD = """# HANDOVER: demo

## 目标
把登录接口改成 JWT。

## 状态
- 已完成：签发与校验
- 进行中：刷新令牌
- 卡点：没有测试环境

## 关键决策
- 用 RS256 —— 因为要跨服务验签

## 已排除
- session 共享 —— 不行，因为 Redis 不稳定

## 文件指针
- 源码：`/srv/app/auth.py`

## 下一步
1. 补刷新令牌单测
2. 压测 200 QPS
"""


class TestHandover(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "HANDOVER.md")

    def write(self, text):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return self.path

    def test_create(self):
        self.assertEqual(create(self.path), 0)
        self.assertTrue(os.path.isfile(self.path))

    def test_create_refuses_existing(self):
        create(self.path)
        self.assertEqual(create(self.path), 1)

    def test_create_force(self):
        create(self.path)
        self.write("# 改过")
        self.assertEqual(create(self.path, force=True), 0)
        with open(self.path, encoding="utf-8") as fh:
            self.assertIn("HANDOVER", fh.read())

    def test_custom_template(self):
        self.assertEqual(create(self.path, template="# 自定义\n"), 0)
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "# 自定义\n")

    def test_empty_template_fails(self):
        create(self.path)
        report = check(self.path)
        self.assertFalse(report.ok)
        codes = {i.code for i in report.issues}
        self.assertIn("empty-sections", codes)

    def test_good_passes(self):
        report = check(self.write(GOOD))
        self.assertTrue(report.ok, [i.message for i in report.issues])
        self.assertLessEqual(report.tokens, 400)

    def test_missing_section(self):
        bad = GOOD.replace("## 关键决策", "## 随便写")
        report = check(self.write(bad))
        self.assertFalse(report.ok)
        self.assertIn("missing-sections", {i.code for i in report.issues})

    def test_duplicate_section(self):
        bad = GOOD + "\n## 目标\n重复一段。\n"
        report = check(self.write(bad))
        self.assertIn("duplicate-sections", {i.code for i in report.issues})

    def test_placeholder_warning(self):
        bad = GOOD.replace("把登录接口改成 JWT。", "<一句话说清这活要什么>")
        report = check(self.write(bad))
        self.assertIn("placeholders", {i.code for i in report.issues})

    def test_too_long_is_error(self):
        long_text = GOOD + "\n" + ("填充内容 " * 400) + "\n"
        report = check(self.write(long_text))
        self.assertIn("too-long", {i.code for i in report.issues})
        self.assertFalse(report.ok)

    def test_unknown_section_warns(self):
        text = GOOD + "\n## 备注\n随便。\n"
        report = check(self.write(text))
        self.assertIn("unknown-sections", {i.code for i in report.issues})
        self.assertTrue(report.ok)

    def test_json(self):
        report = check(self.write(GOOD))
        payload = json.loads(report.to_json())
        self.assertEqual(payload["path"], self.path)
        self.assertTrue(payload["ok"])
        self.assertIsInstance(payload["issues"], list)

    def test_template_has_all_sections(self):
        for section in ("目标", "状态", "关键决策", "文件指针", "下一步"):
            self.assertIn("## " + section, TEMPLATE)


if __name__ == "__main__":
    unittest.main()
