"""El modo académico ignora servicios remotos y guarda archivos dentro de su raíz."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[2]))
from backend import local_config, storage_utils


class LocalDatasetConfigTests(unittest.TestCase):
    def test_local_database_and_keys_are_persistent_with_payments_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(local_config, "LOCAL_DIR", Path(directory)), patch.dict(os.environ, {
                "ENVIRONMENT": "development", "DATABASE_URL": "postgresql://unreachable.invalid/db",
                "PAYMENT_ENABLED": "true", "SETTLEMENT_ENABLED": "true",
            }):
                url = local_config.configure_local()
                first = (os.environ["SECRET_KEY"], os.environ["QR_ENCRYPTION_KEY"])
                self.assertTrue(url.startswith("sqlite:///"))
                self.assertNotIn("unreachable", url)
                self.assertEqual(os.environ["PAYMENT_ENABLED"], "false")
                self.assertEqual(os.environ["SETTLEMENT_ENABLED"], "false")
                self.assertEqual(local_config.configure_local(), url)
                self.assertEqual(first, (os.environ["SECRET_KEY"], os.environ["QR_ENCRYPTION_KEY"]))

    def test_local_mode_is_not_silently_used_for_production(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with self.assertRaisesRegex(RuntimeError, "local"):
                local_config.configure_local()

    def test_storage_roundtrip_never_contacts_supabase_and_rejects_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(storage_utils, "LOCAL_DIR", Path(directory)), \
                    patch.object(storage_utils, "LOCAL_MODE", True), \
                    patch.object(storage_utils, "_get_supabase_client", side_effect=AssertionError("No remote storage")):
                key = "tickets/example.enc"
                self.assertEqual(storage_utils.upload_encrypted_qr(key, b"encrypted"), key)
                self.assertEqual(storage_utils.download_encrypted_qr(key), b"encrypted")
                for path in ("../outside.enc", str(Path(directory).parent / "outside.enc"), ""):
                    with self.assertRaises(ValueError):
                        storage_utils.upload_encrypted_qr(path, b"blocked")
                storage_utils.delete_qr_file(key)
                storage_utils.delete_qr_file(key)
                self.assertFalse((Path(directory) / "storage" / key).exists())
