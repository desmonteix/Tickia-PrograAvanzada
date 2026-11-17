"""Con la app local encendida: TICKIA_DATASET_URL=http://127.0.0.1:5174."""
import os
from pathlib import Path
import re
import unittest
import uuid
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect

URL = os.getenv("TICKIA_DATASET_URL", "")
ARTIFACTS = Path(__file__).resolve().parents[3] / "Proyecto_PrograAvanzada" / ".local"


@unittest.skipUnless(URL, "Configura TICKIA_DATASET_URL con la app académica encendida")
class DatasetBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()
        ARTIFACTS.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors, self.external = [], []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("request", lambda request: self.external.append(request.url)
                     if urlparse(request.url).hostname not in ("127.0.0.1", "localhost") else None)

    def test_real_catalog_search_pagination_filters_details_and_mobile(self):
        page = self.page
        page.goto(URL)
        expect(page.get_by_role("heading", name="Catálogo de productos")).to_be_visible()
        expect(page.locator(".ticket-card")).to_have_count(24)
        expect(page.get_by_role("status").filter(has_text="9,337").or_(
            page.get_by_role("status").filter(has_text="9337"))).to_be_visible()
        self.assertEqual(self.context.request.get(URL + "/api/runtime").json()["data_mode"], "dataset")
        page.screenshot(path=str(ARTIFACTS / "catalogo-desktop.png"), full_page=True)
        page.get_by_role("button", name="Siguiente", exact=True).click()
        expect(page.get_by_text(re.compile(r"Página 2 de"))).to_be_visible()
        page.get_by_role("searchbox").fill("lamparas")
        expect(page.locator(".ticket-card").first.get_by_role("heading")).to_contain_text(re.compile("lámparas", re.I))
        page.get_by_label("Ordenar por").select_option("price_asc")
        page.get_by_label("Solo con stock").check()
        expect(page.locator(".ticket-card").first).to_be_visible()
        page.locator(".ticket-card").first.get_by_role("button").click()
        modal = page.get_by_role("dialog")
        expect(modal.get_by_role("heading", name="Variantes y disponibilidad")).to_be_visible()
        expect(modal.get_by_text("no se realizan cobros", exact=False)).to_be_visible()
        page.keyboard.press("Escape")
        expect(modal).not_to_be_visible()
        page.get_by_role("searchbox").fill("zzzz_no_existe_12345")
        expect(page.get_by_role("heading", name="No encontramos productos")).to_be_visible()
        page.get_by_role("searchbox").fill("")
        page.get_by_label("Categoría", exact=True).select_option("37")
        expect(page.locator(".ticket-card").first).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(ARTIFACTS / "catalogo-mobile.png"), full_page=True)
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
        self.assertEqual(self.errors, [])
        self.assertEqual(self.external, [])

    def test_local_signup_and_session(self):
        page = self.page
        email = "academic-" + uuid.uuid4().hex + "@example.com"
        page.goto(URL)
        expect(page.locator(".ticket-card")).to_have_count(24)
        page.get_by_role("button", name="Ingresar", exact=True).click()
        page.get_by_role("button", name="¿No tienes cuenta? Regístrate").click()
        page.get_by_label("Correo electrónico", exact=True).fill(email)
        page.get_by_label("Teléfono", exact=True).fill("999999999")
        page.get_by_label("Contraseña", exact=True).fill("LocalDataset123!")
        page.get_by_role("button", name="Registrarse", exact=True).click()
        expect(page.get_by_role("button", name="Salir", exact=True)).to_be_visible()
        page.reload()
        expect(page.get_by_role("button", name="Salir", exact=True)).to_be_visible()
        page.get_by_role("button", name="Salir", exact=True).click()
        expect(page.get_by_role("button", name="Ingresar", exact=True)).to_be_visible()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.external, [])
