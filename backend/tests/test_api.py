import os
import unittest
from pathlib import Path

# Ensure backend directory is in sys.path
import sys
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app


class TestCompanyBrainAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_endpoint(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_ping_endpoint(self):
        resp = self.client.get("/ping")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_config_endpoint(self):
        resp = self.client.get("/api/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("store_name", data)
        self.assertIn("demo_mode", data)
        self.assertIn("snapshot_mode", data)

    def test_stats_endpoint(self):
        resp = self.client.get("/api/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("products", data)
        self.assertIn("sales", data)

    def test_data_status_endpoint(self):
        resp = self.client.get("/api/data/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("products", data)
        self.assertIn("sales", data)

    def test_kpis_endpoint(self):
        resp = self.client.get("/api/kpis?days=90")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("revenue", data)
        self.assertIn("margin", data)

    def test_trend_endpoint(self):
        resp = self.client.get("/api/trend?granularity=day&days=30")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_top_products_endpoint(self):
        resp = self.client.get("/api/top-products?days=90&limit=5")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_categories_endpoint(self):
        resp = self.client.get("/api/categories?days=90")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_inventory_status_endpoint(self):
        resp = self.client.get("/api/inventory/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("summary", data)
        self.assertIn("products", data)

    def test_reorder_suggestions_endpoint(self):
        resp = self.client.get("/api/reorder/suggestions?lead_days=5&cover_days=14")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("lines", data)
        self.assertIn("total_cost", data)

    def test_refills_endpoint(self):
        resp = self.client.get("/api/refills?within_days=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("summary", data)
        self.assertIn("rows", data)

    def test_live_sales_validation(self):
        # Empty items should return 422
        resp = self.client.post("/api/sales/live", json={"customer_id": 1, "items": []})
        self.assertEqual(resp.status_code, 422)

    def test_chat_endpoint(self):
        resp = self.client.post("/api/chat", json={"message": "What is our revenue?"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("reply", data)
        self.assertIsInstance(data["reply"], str)

    def test_import_template_endpoint(self):
        resp = self.client.get("/api/import/template/products")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("product_id", resp.text)


if __name__ == "__main__":
    unittest.main()
