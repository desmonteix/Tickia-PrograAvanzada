"""Exercise the actual nginx startup guard without a Docker daemon."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
SHELL = (r"C:\Program Files\Git\bin\sh.exe" if os.name == "nt" else shutil.which("sh"))
SECRET = "isolated-startup-test-" + "a" * 32


class ContainerConfigurationTests(unittest.TestCase):
    def validate(self, **changes):
        env = {**os.environ, "API_UPSTREAM": "http://tickia_backend:8000",
               "PROXY_SHARED_SECRET": SECRET}
        env.update(changes)
        return subprocess.run(
            [SHELL, "docker-entrypoint.d/19-validate-config.sh"], cwd=FRONTEND,
            env=env, capture_output=True, text=True, timeout=10,
        )

    def test_internal_host_and_https_origin_are_accepted(self):
        for upstream in ("http://tickia_backend:8000", "https://api.example.com", "http://127.0.0.1:8000"):
            with self.subTest(upstream=upstream):
                result = self.validate(API_UPSTREAM=upstream)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_upstream_has_an_actionable_error(self):
        result = self.validate(API_UPSTREAM="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("API_UPSTREAM", result.stderr)
        self.assertIn("Easypanel", result.stderr)

    def test_upstream_cannot_contain_path_credentials_or_nginx_syntax(self):
        for upstream in ("backend:8000", "http://backend:8000/", "http://backend:8000/api",
                         "http://user:password@backend", "http://backend?x=1", 'http://backend";#'):
            with self.subTest(upstream=upstream):
                result = self.validate(API_UPSTREAM=upstream)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("API_UPSTREAM", result.stderr)
                self.assertNotIn(upstream, result.stderr)

    def test_secret_is_required_and_never_echoed(self):
        for secret in ("", "short", "a" * 129, "a" * 32 + "\";", "a" * 32 + "\n"):
            with self.subTest(length=len(secret)):
                result = self.validate(PROXY_SHARED_SECRET=secret)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("PROXY_SHARED_SECRET", result.stderr)
                if secret:
                    self.assertNotIn(secret, result.stdout + result.stderr)

    def test_secret_boundaries_match_backend(self):
        for secret in ("a" * 32, "z_-9" * 32):
            result = self.validate(PROXY_SHARED_SECRET=secret)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
