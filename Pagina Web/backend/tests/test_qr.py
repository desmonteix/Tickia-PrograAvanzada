"""Offline regressions: never load application settings or the real database."""
import importlib.util
from pathlib import Path
import unittest

import cv2
import numpy as np


spec = importlib.util.spec_from_file_location("isolated_qr", Path(__file__).parents[1] / "qr_utils.py")
qr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qr)


def image_bytes(payload=None):
    if payload is None:
        image = np.full((150, 150, 3), 255, np.uint8)
    else:
        image = cv2.QRCodeEncoder_create().encode(payload)
        image = cv2.copyMakeBorder(image, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
        image = cv2.resize(image, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
    return cv2.imencode(".png", image)[1].tobytes()


class QRTests(unittest.TestCase):
    def test_blank_image_is_rejected(self):
        result, error = qr.process_qr_image(image_bytes())
        self.assertIsNone(result)
        self.assertIsNotNone(error)

    def test_identical_qr_has_identical_hash(self):
        image = image_bytes("https://teleticket.com.pe/ticket/fixture")
        first, error = qr.process_qr_image(image)
        second, _ = qr.process_qr_image(image)
        self.assertIsNone(error)
        self.assertEqual(first["hash"], second["hash"])

    def test_lookalike_domain_is_rejected(self):
        result, error = qr.process_qr_image(image_bytes("https://evilteleticket.com.pe/ticket"))
        self.assertIsNone(result)
        self.assertIsNotNone(error)

    def test_malformed_image_is_rejected(self):
        result, error = qr.process_qr_image(b"invalid")
        self.assertIsNone(result)
        self.assertIsNotNone(error)


if __name__ == "__main__":
    unittest.main()
