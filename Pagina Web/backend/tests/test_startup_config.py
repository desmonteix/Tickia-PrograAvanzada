"""Production startup rejects missing proxy credentials before database access."""
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("TICKIA_LOAD_ENV", "0")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "isolated-startup-test-not-a-production-key")
sys.path.insert(0, str(Path(__file__).parents[2]))
from backend import main


class ProductionStartupTests(unittest.TestCase):
    def test_invalid_proxy_secret_blocks_startup_without_leaking_it(self):
        for secret in ("", "short", "a" * 129, "a" * 32 + "+"):
            with self.subTest(length=len(secret)), patch.object(main, "is_production", True), \
                    patch.dict(os.environ, {"PROXY_SHARED_SECRET": secret}), \
                    patch.object(main, "inspect") as inspect_db:
                with self.assertRaisesRegex(RuntimeError, "PROXY_SHARED_SECRET") as raised:
                    main.validate_production()
                inspect_db.assert_not_called()
                if secret:
                    self.assertNotIn(secret, str(raised.exception))

    def test_valid_proxy_secret_proceeds_to_other_production_checks(self):
        with patch.object(main, "is_production", True), \
                patch.dict(os.environ, {"PROXY_SHARED_SECRET": "a" * 64}), \
                patch("backend.qr_utils._get_fernet", side_effect=RuntimeError("next production gate")):
            with self.assertRaisesRegex(RuntimeError, "next production gate"):
                main.validate_production()
