import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class TestVersionConsistency(unittest.TestCase):
    def test_package_version(self):
        from token_saver import __version__
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_pyproject_matches(self):
        from token_saver import __version__
        m = re.search(r'^version = "([^"]+)"', read("pyproject.toml"), re.M)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), __version__)

    def test_skill_frontmatter_matches(self):
        from token_saver import __version__
        m = re.search(r"^version:\s*(\S+)", read("SKILL.md"), re.M)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), __version__)

    def test_changelog_has_version(self):
        from token_saver import __version__
        self.assertIn("## " + __version__, read("CHANGELOG.md"))


class TestScripts(unittest.TestCase):
    def test_all_compile(self):
        for name in os.listdir(os.path.join(ROOT, "scripts")):
            if name.endswith(".py"):
                path = os.path.join(ROOT, "scripts", name)
                with self.subTest(script=name):
                    r = subprocess.run([PY, "-m", "py_compile", path], capture_output=True)
                    self.assertEqual(r.returncode, 0, r.stderr.decode())

    def test_every_cli_has_version(self):
        from token_saver import __version__
        for name in ("compress_toolout.py", "tk_audit.py", "ctx_pack.py", "tk_doctor.py"):
            path = os.path.join(ROOT, "scripts", name)
            with self.subTest(script=name):
                r = subprocess.run([PY, path, "--version"], capture_output=True)
                self.assertEqual(r.returncode, 0)
                self.assertIn(__version__, r.stdout.decode())

    def test_no_third_party_imports(self):
        """核心包必须零依赖：不许出现 requests/rich 之类。"""
        bad = ["requests", "rich", "click", "numpy", "tiktoken"]
        for fn in os.listdir(os.path.join(ROOT, "token_saver")):
            if not fn.endswith(".py"):
                continue
            src = read(os.path.join("token_saver", fn))
            for mod in bad:
                self.assertNotRegex(src, rf"^\s*(?:import|from)\s+{mod}\b",
                                    msg=f"{fn} 引入了第三方依赖 {mod}")


class TestShellPortability(unittest.TestCase):
    """macOS 自带 bash 3.2 不认多字节字符，$VAR 后面紧跟中文会被当成变量名。"""

    def test_no_variable_touching_nonascii(self):
        pattern = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7F]")
        for rel in ("scripts/install.sh", "scripts/tk", "tests/smoke.sh"):
            src = read(rel)
            hits = pattern.findall(src)
            self.assertFalse(hits, "%s 里 $VAR 紧跟非 ASCII 字符：%s" % (rel, hits))


class TestDocs(unittest.TestCase):
    def test_readme_has_key_sections(self):
        text = read("README.md")
        for word in ("安装", "卸载", "token-saver", "MIT"):
            self.assertIn(word, text)

    def test_core_template_small(self):
        text = read(os.path.join("templates", "AGENTS.core.md"))
        from token_saver.text import est_tokens
        self.assertLess(est_tokens(text), 260, "常驻内核应控制在 260 token 内")

    def test_license_exists(self):
        self.assertIn("MIT", read("LICENSE"))


if __name__ == "__main__":
    unittest.main()
