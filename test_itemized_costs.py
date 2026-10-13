"""
test_itemized_costs.py
======================
Comprehensive unit tests for itemized costs and complete lifecycle calendar:
1. Calculations for 1 acre and 2 acres.
2. Verification of each item's quantity and individual cost (item_cost = required_quantity * price_per_unit).
3. Verification of daily totals (daily_total = sum of known costs of all items used for that day's tasks).
4. Verification of the complete crop-cycle budget without double-counting.
5. Verification of strict double-counting prevention.
6. Verification of missing prices (null / incomplete status, no invented prices) and invalid acreage.
7. Verification of Flask API endpoints (GET /api/calendar, GET /api/today-tasks, POST /api/task-cost).
"""

import unittest
from flask import Flask

import app
import budget_calculator as bc
import farming_calendar as fc


class TestItemizedCosts(unittest.TestCase):
    """Test suite for itemized agricultural costs and calendar."""

    @classmethod
    def setUpClass(cls):
        cls.flask_app = app.create_app({"TESTING": True})
        cls.client = cls.flask_app.test_client()

    # ─── 1. Calculations for 1 Acre and 2 Acres ───────────────────────────────

    def test_item_scaling_1_and_2_acres(self):
        """Quantities and individual costs scale strictly linearly between 1 and 2 acres."""
        task_1 = bc.calculate_task_items_and_cost(
            {"task_name": "Deep Ploughing", "items": [
                {"name": "Tractor hire", "rate_per_acre": 1.0, "unit": "acre", "price_per_unit": 1200.0, "price_type": "ESTIMATED_CHC_TARIFF", "category": "machinery"},
                {"name": "Labour", "rate_per_acre": 0.5, "unit": "worker-day", "price_per_unit": 375.0, "price_type": "STATUTORY_MINIMUM_WAGE", "category": "labour"}
            ]},
            acres=1.0,
        )
        task_2 = bc.calculate_task_items_and_cost(
            {"task_name": "Deep Ploughing", "items": [
                {"name": "Tractor hire", "rate_per_acre": 1.0, "unit": "acre", "price_per_unit": 1200.0, "price_type": "ESTIMATED_CHC_TARIFF", "category": "machinery"},
                {"name": "Labour", "rate_per_acre": 0.5, "unit": "worker-day", "price_per_unit": 375.0, "price_type": "STATUTORY_MINIMUM_WAGE", "category": "labour"}
            ]},
            acres=2.0,
        )

        # Quantities scale by 2
        self.assertEqual(task_2["items"][0]["required_quantity"], task_1["items"][0]["required_quantity"] * 2)
        self.assertEqual(task_2["items"][1]["required_quantity"], task_1["items"][1]["required_quantity"] * 2)

        # Individual costs scale by 2
        self.assertEqual(task_2["items"][0]["item_cost"], task_1["items"][0]["item_cost"] * 2)
        self.assertEqual(task_2["items"][1]["item_cost"], task_1["items"][1]["item_cost"] * 2)

        # Task total scales by 2
        self.assertAlmostEqual(task_2["task_total"], task_1["task_total"] * 2, places=2)

    def test_lifecycle_budget_scaling_1_and_2_acres(self):
        """Complete crop-cycle budget scales exactly linearly between 1 and 2 acres."""
        b_1 = bc.calculate_budget("Wheat", acres=1.0)
        b_2 = bc.calculate_budget("Wheat", acres=2.0)

        self.assertAlmostEqual(b_2["total_cultivation_cost"], b_1["total_cultivation_cost"] * 2, places=2)
        for cat in b_1["breakdown"]:
            self.assertAlmostEqual(b_2["breakdown"][cat], b_1["breakdown"][cat] * 2, places=2)

    # ─── 2. Verification of Item Quantity and Individual Cost Formula ─────────

    def test_item_cost_formula(self):
        """Verifies item_cost = required_quantity * price_per_unit."""
        item = {
            "name": "Certified Wheat Seed",
            "rate_per_acre": 45.0,
            "unit": "kg",
            "price_per_unit": 42.0,
            "price_type": "OFFICIAL_NSC_TARIFF",
            "category": "seed",
        }
        res = bc.calculate_item_cost(item, acres=2.5)

        self.assertEqual(res["name"], "Certified Wheat Seed")
        self.assertEqual(res["required_quantity"], 45.0 * 2.5)  # 112.5 kg
        self.assertEqual(res["unit"], "kg")
        self.assertEqual(res["price_per_unit"], 42.0)
        self.assertEqual(res["item_cost"], 112.5 * 42.0)  # 4725.0
        self.assertEqual(res["price_type"], "OFFICIAL_NSC_TARIFF")
        self.assertTrue(res["is_priced"])

    def test_all_tasks_have_verified_formula(self):
        """Verifies formula across all tasks for all crops in crop_calendar.json."""
        for crop_name in ["Wheat", "Rice", "Maize"]:
            cal = fc.get_complete_calendar(crop_name, acres=1.5)
            for stage_key, stage_info in cal["stages"].items():
                for task in stage_info["tasks"]:
                    for itm in task.get("items", []):
                        if itm.get("price_per_unit") is not None:
                            expected_cost = round(itm["required_quantity"] * itm["price_per_unit"], 2)
                            self.assertAlmostEqual(
                                itm["item_cost"],
                                expected_cost,
                                places=2,
                                msg=f"Cost mismatch in {crop_name} -> {task['task_name']} -> {itm['name']}"
                            )

    # ─── 3. Verification of Daily Totals ─────────────────────────────────────

    def test_daily_totals_calculation_single_day(self):
        """Day 21 in Wheat has CRI Irrigation and Nitrogen Top-Dressing."""
        tasks = fc.get_tasks_for_day("Wheat", 21, acres=2.0)
        self.assertGreaterEqual(len(tasks), 2)

        # Expected daily total = sum of task totals
        sum_tasks = round(sum(t["task_total"] for t in tasks), 2)
        for t in tasks:
            self.assertEqual(t["daily_total"], sum_tasks)

        self.assertGreater(sum_tasks, 0.0)

    def test_daily_totals_zero_purchase_day(self):
        """Tasks with only decision / testing / monitoring have 0 daily total."""
        tasks = fc.get_tasks_for_day("Wheat", -42, acres=2.0)  # Soil Testing
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_name"], "Soil Testing")
        self.assertEqual(tasks[0]["daily_total"], 0.0)
        self.assertEqual(tasks[0]["items"], [])

    # ─── 4. Verification of Complete Crop-Cycle Budget ────────────────────────

    def test_complete_crop_cycle_budget_wheat(self):
        """Complete crop-cycle budget for Wheat matches verified package."""
        b = bc.calculate_lifecycle_budget_from_calendar("Wheat", acres=1.0)
        self.assertIsNotNone(b["lifecycle_budget"])
        self.assertEqual(b["crop_name"], "Wheat")
        self.assertEqual(b["acres"], 1.0)
        self.assertTrue(b["lifecycle_budget_is_complete"])
        self.assertEqual(b["lifecycle_budget_status"], "COMPLETE")

        # 7 distinct categories present
        expected_cats = {"seed", "fertilizer", "machinery", "labour", "irrigation", "harvesting", "other"}
        self.assertEqual(set(b["lifecycle_budget_breakdown"].keys()), expected_cats)

    def test_complete_crop_cycle_budget_all_crops(self):
        """Complete crop-cycle budget is valid for Wheat, Rice, and Maize."""
        for cname in ["Wheat", "Rice", "Maize"]:
            b = bc.calculate_lifecycle_budget_from_calendar(cname, acres=2.0)
            self.assertGreater(b["lifecycle_budget"], 10000.0)
            self.assertEqual(len(b["stages"]), 11)

    # ─── 5. Strict Double-Counting Prevention ────────────────────────────────

    def test_strict_double_counting_prevention(self):
        """Sum of categories strictly equals lifecycle_budget down to the cent."""
        for cname in ["Wheat", "Rice", "Maize"]:
            for acres in [1.0, 2.0, 3.5]:
                b = bc.calculate_budget(cname, acres=acres)
                cat_sum = round(sum(b["breakdown"].values()), 2)
                self.assertAlmostEqual(b["total_cultivation_cost"], cat_sum, places=2)

    # ─── 6. Missing Prices (Null) and Invalid Acreage ─────────────────────────

    def test_missing_price_marked_null(self):
        """Missing price returns None (null) and flags item as unpriced."""
        item = {
            "name": "Experimental Fertilizer",
            "rate_per_acre": 5.0,
            "unit": "kg",
            "price_per_unit": None,  # Price unavailable
            "price_type": "UNAVAILABLE",
            "category": "fertilizer",
        }
        res = bc.calculate_item_cost(item, acres=1.0)
        self.assertIsNone(res["price_per_unit"])
        self.assertIsNone(res["item_cost"])
        self.assertFalse(res["is_priced"])
        self.assertEqual(res["price_type"], "UNAVAILABLE")

    def test_task_with_missing_price_is_incomplete(self):
        """Task with unpriced items is marked INCOMPLETE."""
        task = {
            "task_name": "Special Spray",
            "items": [
                {"name": "Standard Chemical", "rate_per_acre": 1.0, "unit": "litre", "price_per_unit": 200.0, "category": "other"},
                {"name": "Rare Chemical", "rate_per_acre": 0.5, "unit": "litre", "price_per_unit": None, "category": "other"},
            ]
        }
        costed = bc.calculate_task_items_and_cost(task, acres=2.0)
        self.assertFalse(costed["task_is_complete"])
        self.assertIn("Rare Chemical", costed["missing_price_items"])
        self.assertEqual(costed["task_total"], 400.0)  # Only known cost included

    def test_invalid_acreage_rejected(self):
        """Non-positive or non-numeric acreage raises InvalidInputError."""
        with self.assertRaises(fc.InvalidInputError):
            fc.get_tasks_for_day("Wheat", 21, acres=0)

        with self.assertRaises(fc.InvalidInputError):
            fc.get_tasks_for_day("Wheat", 21, acres=-2)

        with self.assertRaises(fc.InvalidInputError):
            fc.get_tasks_for_day("Wheat", 21, acres="invalid")

        with self.assertRaises(fc.InvalidInputError):
            fc.get_tasks_for_day("Wheat", 21, acres=True)

    # ─── 7. Flask API Endpoints ───────────────────────────────────────────────

    def test_api_calendar_with_acres(self):
        """GET /api/calendar?crop=Wheat&acres=2.0 returns complete calendar with itemized costs."""
        res = self.client.get("/api/calendar?crop=Wheat&acres=2.0")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertEqual(data["name"], "Wheat")
        self.assertEqual(data["acres"], 2.0)
        self.assertIn("lifecycle_budget", data)
        self.assertGreater(data["lifecycle_budget"], 20000.0)
        self.assertIn("stages", data)

        # Inspect first stage's first task
        first_stage = list(data["stages"].values())[0]
        first_task = first_stage["tasks"][0]
        self.assertIn("items", first_task)
        self.assertIn("task_total_cost", first_task)
        self.assertIn("daily_total", first_task)
        self.assertIn("instructions", first_task)
        self.assertIn("purpose", first_task)
        self.assertIn("necessary_precautions", first_task)

    def test_api_calendar_invalid_acres(self):
        """GET /api/calendar?crop=Wheat&acres=-1 returns 400 JSON error."""
        res = self.client.get("/api/calendar?crop=Wheat&acres=-1")
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

    def test_api_today_tasks_with_acres(self):
        """GET /api/today-tasks?crop=Wheat&day=21&acres=2.0 returns tasks and daily_total."""
        res = self.client.get("/api/today-tasks?crop=Wheat&day=21&acres=2.0")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertEqual(data["crop"], "Wheat")
        self.assertEqual(data["acres"], 2.0)
        self.assertIn("daily_total", data)
        self.assertGreater(data["daily_total"], 0)

        task = data["tasks"][0]
        self.assertIn("items", task)
        self.assertIn("daily_total", task)
        self.assertIn("necessary_precautions", task)

    def test_api_today_tasks_invalid_acres(self):
        """GET /api/today-tasks?crop=Wheat&day=21&acres=0 returns 400 JSON error."""
        res = self.client.get("/api/today-tasks?crop=Wheat&day=21&acres=0")
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

    def test_api_task_cost_post(self):
        """POST /api/task-cost calculates itemized costs for a task."""
        payload = {
            "crop": "Wheat",
            "task": "Deep Ploughing",
            "acres": 2.0,
        }
        res = self.client.post("/api/task-cost", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertEqual(data["crop_name"], "Wheat")
        self.assertEqual(data["task_name"], "Deep Ploughing")
        self.assertEqual(data["acres"], 2.0)
        self.assertIn("items", data)
        self.assertIn("task_total_cost", data)
        self.assertIn("total_task_cost", data)
        self.assertIn("cost_breakdown", data)
        self.assertIn("necessary_precautions", data)
        self.assertIn("instructions", data)
        self.assertIn("purpose", data)

        # Check itemized items
        items = data["items"]
        self.assertGreaterEqual(len(items), 1)
        for itm in items:
            self.assertIn("name", itm)
            self.assertIn("required_quantity", itm)
            self.assertIn("unit", itm)
            self.assertIn("price_per_unit", itm)
            self.assertIn("item_cost", itm)
            self.assertIn("price_type", itm)
            self.assertIn("category", itm)

    def test_api_task_cost_invalid_acres(self):
        """POST /api/task-cost with negative acres returns 400."""
        payload = {
            "crop": "Wheat",
            "task": "Deep Ploughing",
            "acres": -3.0,
        }
        res = self.client.post("/api/task-cost", json=payload)
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
