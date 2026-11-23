import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASH = shutil.which("bash")
IS_POSIX = BASH is not None and os.name != "nt"


def dec(data):
    """容错解码，避免 CI 上的编码问题掩盖真正的失败原因。"""
    return data.decode("utf-8", errors="replace")


def slurp(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def sh(script, *args, cwd=ROOT, env=None):
    """用 bash 跑 shell 脚本。"""
    return subprocess.run([BASH, script, *args], cwd=cwd, env=env,
                          capture_output=True, timeout=180)


def py(script, *args, cwd=ROOT, env=None):
    """用当前解释器跑 Python 脚本。"""
    return subprocess.run([sys.executable, script, *args], cwd=cwd, env=env,
                          capture_output=True, timeout=180)


@unittest.skipUnless(IS_POSIX, "需要 bash")
class TestApplyCore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.entry = os.path.join(self.tmp, "AGENTS.md")
        self.core = os.path.join(self.tmp, "core.md")
        with open(self.core, "w", encoding="utf-8") as fh:
            fh.write("# 内核 v1\n规则一\n")
        with open(self.entry, "w", encoding="utf-8") as fh:
            fh.write("# 用户原有内容\n\n正文\n")

    def apply(self, *args):
        return py(os.path.join(ROOT, "scripts", "apply_core.py"), *args)

    def test_add_and_status(self):
        r = self.apply("add", self.entry, self.core)
        self.assertEqual(r.returncode, 0, dec(r.stderr))
        content = slurp(self.entry)
        self.assertEqual(content.count("<!-- token-saver:core:begin -->"), 1)
        self.assertIn("用户原有内容", content)
        self.assertEqual(self.apply("status", self.entry).returncode, 0)

    def test_idempotent(self):
        self.apply("add", self.entry, self.core)
        self.apply("add", self.entry, self.core)
        content = slurp(self.entry)
        self.assertEqual(content.count("<!-- token-saver:core:begin -->"), 1)

    def test_upgrade_replaces_block(self):
        self.apply("add", self.entry, self.core)
        with open(self.core, "w", encoding="utf-8") as fh:
            fh.write("# 内核 v2\n规则二\n")
        self.apply("add", self.entry, self.core)
        content = slurp(self.entry)
        self.assertIn("规则二", content)
        self.assertNotIn("规则一", content)

    def test_remove_cleansup(self):
        self.apply("add", self.entry, self.core)
        self.assertEqual(self.apply("remove", self.entry).returncode, 0)
        content = slurp(self.entry)
        self.assertNotIn("token-saver:core", content)
        self.assertIn("用户原有内容", content)
        self.assertNotEqual(self.apply("status", self.entry).returncode, 0)

    def test_remove_missing_block(self):
        self.assertEqual(self.apply("remove", self.entry).returncode, 1)

    def test_permissions_preserved(self):
        os.chmod(self.entry, 0o600)
        self.apply("add", self.entry, self.core)
        self.assertEqual(os.stat(self.entry).st_mode & 0o777, 0o600)

    def test_dry_run_no_change(self):
        before = slurp(self.entry)
        self.apply("add", self.entry, self.core, "--dry-run")
        self.assertEqual(slurp(self.entry), before)


@unittest.skipUnless(IS_POSIX, "需要 bash")
class TestInstallFlow(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.env = dict(os.environ)
        self.env["HOME"] = self.home
        self.env.pop("PYTHONIOENCODING", None)

    def install(self, *args):
        return sh(os.path.join(ROOT, "scripts", "install.sh"), "--target", "claude", *args,
                  env=self.env)

    def entry(self):
        return os.path.join(self.home, ".claude", "CLAUDE.md")

    def skill(self):
        return os.path.join(self.home, ".claude", "skills", "token-saver")

    def test_dry_run_creates_nothing(self):
        r = self.install("--dry-run")
        self.assertEqual(r.returncode, 0, dec(r.stderr))
        self.assertFalse(os.path.exists(self.skill()))

    def test_install_and_status(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, dec(r.stderr))
        self.assertTrue(os.path.isfile(os.path.join(self.skill(), "SKILL.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.skill(), "token_saver", "cli.py")))
        content = slurp(self.entry())
        self.assertEqual(content.count("<!-- token-saver:core:begin -->"), 1)
        self.assertEqual(self.install("--status").returncode, 0)

    def test_reinstall_keeps_one_block(self):
        self.install()
        r = self.install()
        self.assertEqual(r.returncode, 0, dec(r.stderr))
        content = slurp(self.entry())
        self.assertEqual(content.count("<!-- token-saver:core:begin -->"), 1)
        backups = [d for d in os.listdir(os.path.dirname(self.skill())) if ".bak." in d]
        self.assertTrue(backups)

    def test_uninstall(self):
        self.install()
        r = self.install("--uninstall")
        self.assertEqual(
            r.returncode, 0,
            "stderr=%r hex=%s" % (dec(r.stderr), r.stderr.hex()[:400]),
        )
        self.assertNotIn("token-saver:core", slurp(self.entry()))
        self.assertFalse(os.path.exists(self.skill()))
        self.assertNotEqual(self.install("--status").returncode, 0)

    def test_core_only(self):
        r = self.install("--core-only")
        self.assertEqual(r.returncode, 0, dec(r.stderr))
        self.assertFalse(os.path.exists(self.skill()))
        self.assertIn("token-saver:core", slurp(self.entry()))

    def test_skill_only(self):
        r = self.install("--skill-only")
        self.assertEqual(r.returncode, 0, dec(r.stderr))
        self.assertTrue(os.path.isdir(self.skill()))
        self.assertFalse(os.path.exists(self.entry()))

    def test_unknown_target(self):
        r = sh(os.path.join(ROOT, "scripts", "install.sh"), "--target", "mars", env=self.env)
        self.assertNotEqual(r.returncode, 0)

    def test_installed_skill_runs(self):
        self.install()
        tk = os.path.join(self.skill(), "scripts", "compress_toolout.py")
        r = subprocess.run([sys.executable, tk, "--version"], capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertIn("2.1.0", r.stdout.decode())


if __name__ == "__main__":
    unittest.main()
