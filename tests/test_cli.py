import json
import os
import subprocess
import sys
import tempfile
import unittest

from token_saver import __version__

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
SCRIPTS = os.path.join(ROOT, "scripts")


def run(args, stdin=None, cwd=ROOT, env=None):
    return subprocess.run(
        [PY] + args, input=stdin, capture_output=True, cwd=cwd, env=env, timeout=120
    )


class TestCompressCLI(unittest.TestCase):
    def test_version(self):
        r = run([os.path.join(SCRIPTS, "compress_toolout.py"), "--version"])
        self.assertEqual(r.returncode, 0)
        self.assertIn(__version__, r.stdout.decode())

    def test_binary_stdin(self):
        r = run([os.path.join(SCRIPTS, "compress_toolout.py")], stdin=b"\x00\x01\x02" * 500)
        self.assertEqual(r.returncode, 3)
        self.assertIn("二进制", r.stderr.decode())

    def test_missing_file(self):
        r = run([os.path.join(SCRIPTS, "compress_toolout.py"), "--file", "/nope/none.log"])
        self.assertEqual(r.returncode, 3)

    def test_stdin_compression(self):
        data = ("\n".join(f"line {i}" for i in range(2000)) + "\n").encode()
        r = run([os.path.join(SCRIPTS, "compress_toolout.py"), "--budget", "200"], stdin=data)
        self.assertEqual(r.returncode, 0)
        self.assertIn("省略", r.stdout.decode())

    def test_json_stats(self):
        data = ("\n".join(f"line {i}" for i in range(500)) + "\n").encode()
        r = run([os.path.join(SCRIPTS, "compress_toolout.py"), "--json", "--budget", "100"],
                stdin=data)
        self.assertEqual(r.returncode, 0)
        stats = json.loads(r.stderr.decode().strip().splitlines()[-1])
        self.assertIn("saved_ratio", stats)
        self.assertLessEqual(stats["out_tokens"], stats["raw_tokens"])

    def test_out_file(self):
        tmp = tempfile.mkdtemp()
        out = os.path.join(tmp, "c.txt")
        data = b"a\n" * 100
        r = run([os.path.join(SCRIPTS, "compress_toolout.py"), "--out", out], stdin=data)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(os.path.getsize(out) > 0)

    def test_profile_auto(self):
        data = ('{"a": 1}\n' * 300).encode()
        r = run([os.path.join(SCRIPTS, "compress_toolout.py"), "--json"], stdin=data)
        stats = json.loads(r.stderr.decode().strip().splitlines()[-1])
        self.assertEqual(stats["profile"], "json")

    def test_bad_args(self):
        r = run([os.path.join(SCRIPTS, "compress_toolout.py"), "--budget", "-5"])
        self.assertEqual(r.returncode, 2)

    @unittest.skipIf(os.name == "nt", "bash 包装器只在类 Unix 上测")
    def test_tk_wrapper(self):
        r = subprocess.run(["bash", os.path.join(SCRIPTS, "tk"), "150"],
                           input=b"x\n" * 300, capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertIn("省", r.stderr.decode())


class TestAuditCLI(unittest.TestCase):
    def test_json(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "a.log")
        with open(path, "w") as fh:
            fh.write("x\n" * 100)
        r = run([os.path.join(SCRIPTS, "tk_audit.py"), "--json", path])
        self.assertEqual(r.returncode, 0)
        payload = json.loads(r.stdout.decode())
        self.assertEqual(payload["totals"]["files"], 1)

    def test_csv(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "a.log")
        with open(path, "w") as fh:
            fh.write("x\n" * 10)
        r = run([os.path.join(SCRIPTS, "tk_audit.py"), "--csv", path])
        self.assertEqual(r.returncode, 0)
        self.assertIn("est_waste_tokens", r.stdout.decode())

    def test_no_args_usage(self):
        r = run([os.path.join(SCRIPTS, "tk_audit.py")])
        self.assertEqual(r.returncode, 2)


class TestPackCLI(unittest.TestCase):
    def test_json(self):
        r = run([os.path.join(SCRIPTS, "ctx_pack.py"), ROOT, "--json", "--max-files", "5"])
        self.assertEqual(r.returncode, 0)
        payload = json.loads(r.stdout.decode())
        self.assertEqual(payload["totals"]["files"], 5)

    def test_markdown(self):
        r = run([os.path.join(SCRIPTS, "ctx_pack.py"), ROOT, "--max-files", "5"])
        self.assertIn("索引卡", r.stdout.decode())


class TestHandoverCLI(unittest.TestCase):
    def test_new_and_check(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "H.md")
        r = run([os.path.join(SCRIPTS, "handover.py"), "new", path])
        self.assertEqual(r.returncode, 0)
        r = run([os.path.join(SCRIPTS, "handover.py"), "check", path])
        self.assertEqual(r.returncode, 1)
        r = run([os.path.join(SCRIPTS, "handover.py"), "check", "--json", path])
        payload = json.loads(r.stdout.decode())
        self.assertFalse(payload["ok"])

    def test_missing_file(self):
        r = run([os.path.join(SCRIPTS, "handover.py"), "show", "/nope/H.md"])
        self.assertEqual(r.returncode, 3)

    def test_bad_command(self):
        r = run([os.path.join(SCRIPTS, "handover.py"), "wat", "x"])
        self.assertEqual(r.returncode, 2)


class TestDoctorCLI(unittest.TestCase):
    def test_json(self):
        r = run([os.path.join(SCRIPTS, "tk_doctor.py"), "--json"])
        payload = json.loads(r.stdout.decode())
        self.assertIn("checks", payload)
        self.assertEqual(payload["version"], __version__)

    def test_module_entry(self):
        r = run(["-m", "token_saver", "doctor", "--json"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("checks", json.loads(r.stdout.decode()))


if __name__ == "__main__":
    unittest.main()
