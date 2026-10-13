"""
test_app.py
===========
Unit tests for the modular Flask backend in app.py.

Tests:
1. GET  /api/calendar     (complete calendar, crop filter, ID filter, grid, validation)
2. GET  /api/today-tasks  (crop day lookup, planting_date lookup, validation, 400/404 handling)
3. POST /api/task-cost    (quantities & cost calculation, non-JSON, missing fields, validation)
4. Modularity test        (mounting blueprint onto a separate Flask application)
5. Web UI route GET /     (HTML rendering)
"""

import json
import unittest
from datetime import date, timedelta

from flask import Flask

import app
from app import calendar_api, create_app


class TestAppBackend(unittest.TestCase):
    """Test suite for app.py API endpoints and modularity."""

    @classmethod
    def setUpClass(cls):
        """Create a test client from the application factory."""
        cls.flask_app = create_app({"TESTING": True})
        cls.client = cls.flask_app.test_client()

    # ─── 1. GET /api/calendar ─────────────────────────────────────────────────

    def test_get_calendar_complete(self):
        """GET /api/calendar without args returns the full crop calendar."""
        res = self.client.get("/api/calendar")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.is_json)
        data = res.get_json()

        self.assertIn("crops", data)
        self.assertIn("seasons", data)
        self.assertIn("months", data)
        self.assertGreaterEqual(len(data["crops"]), 3)

    def test_get_calendar_by_crop_name(self):
        """GET /api/calendar?crop=Wheat returns complete calendar for Wheat."""
        res = self.client.get("/api/calendar?crop=Wheat")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertEqual(data["name"], "Wheat")
        self.assertEqual(data["season"], "Rabi")
        self.assertIn("stages", data)
        self.assertEqual(len(data["stages"]), 11)

    def test_get_calendar_by_crop_id(self):
        """GET /api/calendar?crop_id=1 returns complete calendar for Wheat."""
        res = self.client.get("/api/calendar?crop_id=1")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["name"], "Wheat")

    def test_get_calendar_unknown_crop(self):
        """GET /api/calendar with unknown crop returns 404 JSON error."""
        res = self.client.get("/api/calendar?crop=Dragonfruit")
        self.assertEqual(res.status_code, 404)
        self.assertTrue(res.is_json)
        data = res.get_json()
        self.assertIn("error", data)
        self.assertIn("Dragonfruit", data["error"])

    def test_get_calendar_invalid_crop_id(self):
        """GET /api/calendar with non-integer crop_id returns 400 JSON error."""
        res = self.client.get("/api/calendar?crop_id=not_an_id")
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

    def test_get_calendar_grid(self):
        """GET /api/calendar?grid=true returns the 12-month calendar grid."""
        res = self.client.get("/api/calendar?grid=true")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 12)

    # ─── 2. GET /api/today-tasks ──────────────────────────────────────────────

    def test_get_today_tasks_valid_day(self):
        """GET /api/today-tasks?crop=Wheat&day=21 returns CRI tasks."""
        res = self.client.get("/api/today-tasks?crop=Wheat&day=21")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.is_json)
        data = res.get_json()

        self.assertEqual(data["crop"], "Wheat")
        self.assertEqual(data["crop_day"], 21)
        self.assertGreaterEqual(data["tasks_count"], 2)

        task_names = [t["task_name"] for t in data["tasks"]]
        self.assertTrue(any("Crown Root" in n for n in task_names))
        self.assertTrue(any("Top-Dressing" in n for n in task_names))

    def test_get_today_tasks_sowing_day(self):
        """GET /api/today-tasks?crop=Wheat&day=0 returns Sowing Day tasks."""
        res = self.client.get("/api/today-tasks?crop=Wheat&day=0")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        task_names = [t["task_name"] for t in data["tasks"]]
        self.assertTrue(any("Sowing" in n for n in task_names))

    def test_get_today_tasks_by_crop_id(self):
        """GET /api/today-tasks accepts crop_id instead of name."""
        res = self.client.get("/api/today-tasks?crop_id=1&day=21")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["crop"], "Wheat")

    def test_get_today_tasks_by_planting_date(self):
        """GET /api/today-tasks computes crop_day from planting_date."""
        # Assume planted 21 days ago
        twenty_one_days_ago = (date.today() - timedelta(days=21)).isoformat()
        res = self.client.get(f"/api/today-tasks?crop=Wheat&planting_date={twenty_one_days_ago}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["crop_day"], 21)
        self.assertGreaterEqual(data["tasks_count"], 2)

    def test_get_today_tasks_missing_crop(self):
        """Missing crop parameter returns 400 Bad Request."""
        res = self.client.get("/api/today-tasks?day=21")
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

    def test_get_today_tasks_unknown_crop(self):
        """Unknown crop parameter returns 404 Not Found with suggestion."""
        res = self.client.get("/api/today-tasks?crop=UnknownCrop&day=21")
        self.assertEqual(res.status_code, 404)
        data = res.get_json()
        self.assertIn("error", data)
        self.assertIn("UnknownCrop", data["error"])

    def test_get_today_tasks_missing_day_and_date(self):
        """Missing both day and planting_date returns 400 Bad Request."""
        res = self.client.get("/api/today-tasks?crop=Wheat")
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

    def test_get_today_tasks_invalid_day(self):
        """Non-integer day parameter returns 400 Bad Request."""
        res = self.client.get("/api/today-tasks?crop=Wheat&day=twenty_one")
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

    def test_get_today_tasks_invalid_date(self):
        """Non-ISO planting_date returns 400 Bad Request."""
        res = self.client.get("/api/today-tasks?crop=Wheat&planting_date=not-a-date")
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

    # ─── 3. POST /api/task-cost ───────────────────────────────────────────────

    def test_post_task_cost_wheat_top_dressing(self):
        """POST /api/task-cost calculates quantities and cost for top-dressing."""
        payload = {
            "crop": "Wheat",
            "task": "First Top-Dressing of Nitrogen",
            "acres": 2.5
        }
        res = self.client.post("/api/task-cost", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.is_json)
        data = res.get_json()

        self.assertEqual(data["crop_name"], "Wheat")
        self.assertIn("Top-Dressing", data["task_name"])
        self.assertEqual(data["acres"], 2.5)
        self.assertGreater(data["total_task_cost"], 0)

        # Check disjoint cost breakdown sum equals total
        cb = data["cost_breakdown"]
        self.assertAlmostEqual(data["total_task_cost"], sum(cb.values()), places=2)

        # Check material quantities (Urea)
        self.assertGreater(len(data["quantities"]), 0)
        urea = data["quantities"][0]
        self.assertEqual(urea["unit"], "kg")
        self.assertEqual(urea["total_quantity"], 55.0 * 2.5)  # 137.5 kg
        self.assertEqual(urea["bags_required"], 4)

        # Check labour
        self.assertIsNotNone(data["labour"])
        self.assertEqual(data["labour"]["wage_rate"], 375.0)

    def test_post_task_cost_deep_ploughing(self):
        """POST /api/task-cost calculates tractor machinery and labour for tillage."""
        payload = {
            "crop": "Wheat",
            "task": "Deep Ploughing",
            "acres": 2.0
        }
        res = self.client.post("/api/task-cost", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        # Machinery cost: ₹1,800 * 2 = ₹3,600
        self.assertEqual(data["cost_breakdown"]["machinery"], 3600.0)
        # Labour cost: 1 day * 2 acres * ₹375 = ₹750
        self.assertEqual(data["cost_breakdown"]["labour"], 750.0)
        self.assertEqual(data["total_task_cost"], 4350.0)

    def test_post_task_cost_with_crop_id(self):
        """POST /api/task-cost accepts crop_id."""
        payload = {
            "crop_id": 1,
            "task": "Deep Ploughing",
            "acres": 1.0
        }
        res = self.client.post("/api/task-cost", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["crop_name"], "Wheat")

    def test_post_task_cost_non_json_body(self):
        """Non-JSON request body returns 400 Bad Request."""
        res = self.client.post("/api/task-cost", data="not json", content_type="text/plain")
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

    def test_post_task_cost_missing_crop(self):
        """Missing crop field returns 400 Bad Request."""
        payload = {"task": "Deep Ploughing", "acres": 2.0}
        res = self.client.post("/api/task-cost", json=payload)
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

    def test_post_task_cost_missing_task(self):
        """Missing task field returns 400 Bad Request."""
        payload = {"crop": "Wheat", "acres": 2.0}
        res = self.client.post("/api/task-cost", json=payload)
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

    def test_post_task_cost_missing_or_invalid_acres(self):
        """Missing, zero, or negative acres returns 400 Bad Request."""
        # Missing
        res1 = self.client.post("/api/task-cost", json={"crop": "Wheat", "task": "Deep Ploughing"})
        self.assertEqual(res1.status_code, 400)

        # Zero
        res2 = self.client.post("/api/task-cost", json={"crop": "Wheat", "task": "Deep Ploughing", "acres": 0})
        self.assertEqual(res2.status_code, 400)

        # Negative
        res3 = self.client.post("/api/task-cost", json={"crop": "Wheat", "task": "Deep Ploughing", "acres": -2.5})
        self.assertEqual(res3.status_code, 400)

        # String
        res4 = self.client.post("/api/task-cost", json={"crop": "Wheat", "task": "Deep Ploughing", "acres": "two"})
        self.assertEqual(res4.status_code, 400)

    def test_post_task_cost_unknown_crop(self):
        """Unknown crop returns 404 Not Found."""
        payload = {"crop": "Avocado", "task": "Deep Ploughing", "acres": 2.0}
        res = self.client.post("/api/task-cost", json=payload)
        self.assertEqual(res.status_code, 404)
        data = res.get_json()
        self.assertIn("error", data)

    def test_post_task_cost_unknown_task(self):
        """Unknown task for known crop returns 404 Not Found."""
        payload = {"crop": "Wheat", "task": "Spacecraft Launching Operation", "acres": 2.0}
        res = self.client.post("/api/task-cost", json=payload)
        self.assertEqual(res.status_code, 404)
        data = res.get_json()
        self.assertIn("error", data)

    # ─── 4. Modularity: Mounting onto Another Flask App ───────────────────────

    def test_blueprint_integration_into_another_app(self):
        """
        Validates modularity requirement:
        calendar_api Blueprint can be imported and mounted into another Flask application.
        """
        # Create a completely separate, independent host Flask application
        host_app = Flask("external_app")

        # Mount the farming calendar Blueprint
        host_app.register_blueprint(calendar_api)

        # Test calling the endpoints through the host application
        host_client = host_app.test_client()

        # 1. Test GET /api/calendar
        r1 = host_client.get("/api/calendar")
        self.assertEqual(r1.status_code, 200)
        self.assertIn("crops", r1.get_json())

        # 2. Test GET /api/today-tasks
        r2 = host_client.get("/api/today-tasks?crop=Wheat&day=21")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.get_json()["crop"], "Wheat")

        # 3. Test POST /api/task-cost
        r3 = host_client.post("/api/task-cost", json={
            "crop": "Wheat",
            "task": "Deep Ploughing",
            "acres": 1.0
        })
        self.assertEqual(r3.status_code, 200)
        # Machinery (₹1,800) + 1 day labour (₹375) = ₹2,175.0
        self.assertEqual(r3.get_json()["total_task_cost"], 2175.0)

    # ─── 5. Web UI Route ──────────────────────────────────────────────────────

    def test_web_ui_index_route(self):
        """GET / renders HTML page."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.content_type)
        html = res.get_data(as_text=True)
        self.assertIn("Farming Calendar", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
