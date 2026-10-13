"""
test_budget_calculator.py
=========================
Comprehensive unit tests for budget_calculator.py validating all requirements:
1. Land area in acres scaling and validation
2. Material quantities calculation
3. Fertilizer quantities calculation
4. Seed quantities calculation
5. Labour costs calculation
6. Machinery costs calculation
7. Irrigation costs calculation
8. Harvesting costs calculation
9. Other applicable expenses calculation
10. Total estimated cultivation cost
11. Verified per-acre rates and reliable prices
12. Incomplete estimate handling when quantities/prices are missing (no invented values)
13. Strict double-counting prevention
14. Multi-crop comparison
"""

import unittest
import math

import budget_calculator as bc
from budget_calculator import (
    BudgetCalculationError,
    InvalidLandAreaError,
    calculate_budget,
    compare_crops,
    get_crop_agronomic_profile,
    get_reliable_price,
    get_verified_crop_names,
)


class TestBudgetCalculator(unittest.TestCase):
    """Test suite for agricultural budget and cultivation cost calculator."""

    # ─── 1. Land Area in Acres Scaling & Validation ───────────────────────────

    def test_valid_acres_scaling(self):
        """Quantities and costs must scale strictly linearly with acres."""
        res_1 = calculate_budget("Wheat", acres=1.0)
        res_2 = calculate_budget("Wheat", acres=2.0)
        res_5 = calculate_budget("Wheat", acres=5.0)

        # Cost scaling
        self.assertAlmostEqual(res_2["total_cultivation_cost"], res_1["total_cultivation_cost"] * 2, places=2)
        self.assertAlmostEqual(res_5["total_cultivation_cost"], res_1["total_cultivation_cost"] * 5, places=2)

        # Seed scaling
        self.assertAlmostEqual(res_2["seed_quantities"]["total_quantity"], res_1["seed_quantities"]["total_quantity"] * 2, places=2)

        # Yield scaling
        self.assertAlmostEqual(res_2["expected_yield_quintals"], res_1["expected_yield_quintals"] * 2, places=2)

    def test_invalid_acres_values(self):
        """Zero, negative, non-numeric, boolean, and null acres raise InvalidLandAreaError."""
        with self.assertRaises(InvalidLandAreaError):
            calculate_budget("Wheat", acres=0)

        with self.assertRaises(InvalidLandAreaError):
            calculate_budget("Wheat", acres=-2.5)

        with self.assertRaises(InvalidLandAreaError):
            calculate_budget("Wheat", acres=None)

        with self.assertRaises(InvalidLandAreaError):
            calculate_budget("Wheat", acres=True)  # Boolean rejected

        with self.assertRaises(InvalidLandAreaError):
            calculate_budget("Wheat", acres="invalid")

    # ─── 2. Material Quantities Calculation ───────────────────────────────────

    def test_material_quantities(self):
        """Calculates all physical inputs with verified per-acre rates."""
        res = calculate_budget("Wheat", acres=2.0)
        mats = res["material_quantities"]
        self.assertIsInstance(mats, list)
        self.assertGreater(len(mats), 3)

        mat_names = [m["item"] for m in mats]
        # Should include seed, urea, DAP, MOP, packaging bags
        self.assertTrue(any("Seed" in name for name in mat_names))
        self.assertTrue(any("Urea" in name for name in mat_names))
        self.assertTrue(any("DAP" in name for name in mat_names))
        self.assertTrue(any("HDPE" in name or "bags" in name.lower() for name in mat_names))

        # Check total quantity calculation for 2 acres
        for m in mats:
            self.assertEqual(m["total_quantity"], round(m["rate_per_acre"] * 2.0, 2))

    # ─── 3. Fertilizer Quantities Calculation ─────────────────────────────────

    def test_fertilizer_quantities(self):
        """Calculates specific fertilizer requirements, kg totals, and bag counts."""
        res = calculate_budget("Wheat", acres=3.0)
        ferts = res["fertilizer_quantities"]
        self.assertIsInstance(ferts, list)

        fert_by_item = {f["item"]: f for f in ferts}
        self.assertIn("Urea (46% N)", fert_by_item)
        self.assertIn("Di-Ammonium Phosphate (DAP 18:46:0)", fert_by_item)

        # Urea: 110 kg/acre * 3 = 330 kg
        urea = fert_by_item["Urea (46% N)"]
        self.assertEqual(urea["total_quantity"], 330.0)
        # 330 kg / 45 kg bag = 7.33 -> 8 bags
        self.assertEqual(urea["bags_required"], 8)
        # Cost: 330 kg * ₹5.38/kg = ₹1,775.40
        self.assertAlmostEqual(urea["total_cost"], 330.0 * 5.38, places=2)

        # DAP: 55 kg/acre * 3 = 165 kg -> 4 bags of 50 kg
        dap = fert_by_item["Di-Ammonium Phosphate (DAP 18:46:0)"]
        self.assertEqual(dap["total_quantity"], 165.0)
        self.assertEqual(dap["bags_required"], 4)

    # ─── 4. Seed Quantities Calculation ───────────────────────────────────────

    def test_seed_quantities(self):
        """Calculates certified seed quantities and packaging."""
        res = calculate_budget("Wheat", acres=2.5)
        seed = res["seed_quantities"]
        self.assertIsNotNone(seed)

        # Wheat rate: 45 kg/acre * 2.5 = 112.5 kg
        self.assertEqual(seed["rate_per_acre"], 45.0)
        self.assertEqual(seed["total_quantity"], 112.5)
        # Standard 40 kg bags -> ceil(112.5 / 40) = 3 bags
        self.assertEqual(seed["bags_required"], 3)
        # Price: ₹42/kg * 112.5 kg = ₹4,725.00
        self.assertAlmostEqual(seed["total_cost"], 4725.0, places=2)

    # ─── 5. Labour Costs Calculation ──────────────────────────────────────────

    def test_labour_costs(self):
        """Calculates person-days across operations and total labour expense."""
        res = calculate_budget("Rice", acres=2.0)
        labour = res["labour_breakdown"]
        self.assertIsInstance(labour, list)
        self.assertGreater(len(labour), 0)

        # Total person days for Rice = (2 + 8 + 5 + 3) = 18 days/acre * 2 = 36 person-days
        total_days = sum(l["total_person_days"] for l in labour)
        self.assertEqual(total_days, 36.0)

        # Wage rate = ₹375.00/day
        total_labour_cost = sum(l["cost"] for l in labour)
        self.assertAlmostEqual(total_labour_cost, 36.0 * 375.0, places=2)
        self.assertEqual(res["breakdown"]["labour"], total_labour_cost)

    # ─── 6. Machinery Costs Calculation ───────────────────────────────────────

    def test_machinery_costs(self):
        """Calculates tractor tillage and sowing implement hiring costs."""
        res = calculate_budget("Wheat", acres=4.0)
        mach = res["machinery_breakdown"]
        self.assertIsInstance(mach, list)
        self.assertGreater(len(mach), 0)

        # Land prep: ₹1,800/acre * 4 = ₹7,200; Seed drill: ₹650/acre * 4 = ₹2,600
        total_mach_cost = sum(m["total_cost"] for m in mach)
        self.assertAlmostEqual(total_mach_cost, (1800.0 + 650.0) * 4.0, places=2)
        self.assertEqual(res["breakdown"]["machinery"], total_mach_cost)

    # ─── 7. Irrigation Costs Calculation ──────────────────────────────────────

    def test_irrigation_costs(self):
        """Calculates event-based pumping electricity/fuel and water charges."""
        res = calculate_budget("Wheat", acres=2.0)
        irrig = res["irrigation_breakdown"]
        self.assertEqual(irrig["events_count"], 5)

        # 5 events * ₹350/event/acre * 2 acres = ₹3,500
        self.assertAlmostEqual(irrig["total_cost"], 5 * 350.0 * 2.0, places=2)
        self.assertEqual(res["breakdown"]["irrigation"], 3500.0)

    # ─── 8. Harvesting Costs Calculation ──────────────────────────────────────

    def test_harvesting_costs(self):
        """Calculates combine harvester contract or mechanical harvesting cost."""
        res = calculate_budget("Maize", acres=3.0)
        harv = res["harvesting_breakdown"]
        self.assertIn("operation", harv)

        # Maize mechanical harvesting: ₹1,800/acre * 3 = ₹5,400
        self.assertAlmostEqual(harv["total_cost"], 1800.0 * 3.0, places=2)
        self.assertEqual(res["breakdown"]["harvesting"], 5400.0)

    # ─── 9. Other Applicable Expenses Calculation ─────────────────────────────

    def test_other_applicable_expenses(self):
        """Calculates seed treatment, weedicides, bags, and transport fees."""
        res = calculate_budget("Wheat", acres=1.0)
        other = res["other_expenses_breakdown"]
        self.assertIsInstance(other, list)
        self.assertGreater(len(other), 0)

        # Check that packaging bags and transport are present
        items = [o["item"] for o in other]
        self.assertTrue(any("Seed treatment" in i or "seed" in i.lower() for i in items))
        self.assertTrue(any("bags" in i.lower() for i in items))
        self.assertTrue(any("transport" in i.lower() for i in items))

        total_other = sum(o["cost"] for o in other)
        self.assertAlmostEqual(res["breakdown"]["other"], total_other, places=2)

    # ─── 10. Strict Double-Counting Prevention ────────────────────────────────

    def test_prevent_double_counting_wheat(self):
        """
        Sum of breakdown categories must strictly equal total_cultivation_cost.
        No expense line item may be counted twice.
        """
        res = calculate_budget("Wheat", acres=3.5)
        b = res["breakdown"]

        # 7 distinct categories
        expected_categories = {"seed", "fertilizer", "machinery", "labour", "irrigation", "harvesting", "other"}
        self.assertEqual(set(b.keys()), expected_categories)

        # Sum of categories must equal total cultivation cost down to the cent
        sum_categories = round(sum(b.values()), 2)
        self.assertAlmostEqual(res["total_cultivation_cost"], sum_categories, places=2)
        self.assertAlmostEqual(res["input_cost"], sum_categories, places=2)

        # Sum of individual line items must also equal total cultivation cost
        sum_line_items = round(sum(item["cost"] for item in res["line_items"] if item["cost"] is not None), 2)
        self.assertAlmostEqual(res["total_cultivation_cost"], sum_line_items, places=2)

    def test_prevent_double_counting_all_crops(self):
        """Assert double-counting prevention across all verified crops."""
        for crop_name in get_verified_crop_names():
            res = calculate_budget(crop_name, acres=2.5)
            b_sum = round(sum(res["breakdown"].values()), 2)
            self.assertAlmostEqual(res["total_cultivation_cost"], b_sum, places=2)

    # ─── 11. Reliable Prices Used ─────────────────────────────────────────────

    def test_reliable_prices_lookup(self):
        """Verifies official statutory MRPs and benchmark prices."""
        urea = get_reliable_price("urea_per_kg")
        self.assertIsNotNone(urea)
        self.assertEqual(urea["price"], 5.38)
        self.assertIn("Ministry of Chemicals", urea["source"])

        dap = get_reliable_price("dap_per_kg")
        self.assertIsNotNone(dap)
        self.assertEqual(dap["price"], 27.00)

        labour = get_reliable_price("agricultural_labour_per_day")
        self.assertIsNotNone(labour)
        self.assertEqual(labour["price"], 375.00)

    # ─── 12. Missing Data Marked Incomplete (No Invented Values) ─────────────

    def test_incomplete_estimate_on_unverified_crop(self):
        """
        An unverified crop with missing agronomic rates must be flagged as
        INCOMPLETE, tracking missing_items instead of inventing numbers.
        """
        unverified_crop = {
            "name": "Dragonfruit",
            "yield_per_acre": 8.0,
            "price_per_quintal": 10000.0,
            # cost_per_acre is missing!
        }
        res = calculate_budget(unverified_crop, acres=1.0)

        self.assertFalse(res["is_complete"])
        self.assertEqual(res["completeness_status"], "INCOMPLETE")
        self.assertGreater(len(res["missing_items"]), 0)
        self.assertIn("INCOMPLETE", res["completeness_notes"])

    def test_incomplete_estimate_when_price_is_missing(self):
        """
        When a required input has no verified price in the database,
        it must not invent a price; it must flag missing_items and mark is_complete=False.
        """
        # Override urea price to None / simulate missing price
        res = calculate_budget("Wheat", acres=1.0, custom_prices={"urea_per_kg": None})

        # Since urea price was set to None, it cannot be priced reliably
        self.assertFalse(res["is_complete"])
        self.assertEqual(res["completeness_status"], "INCOMPLETE")
        missing_names = [m["item"] for m in res["missing_items"]]
        self.assertTrue(any("Urea" in name for name in missing_names))

    # ─── 13. Revenue, Net Profit, and ROI Calculation ─────────────────────────

    def test_revenue_and_profit_calculation(self):
        """Validates expected yield, gross revenue, net profit, and ROI."""
        res = calculate_budget("Wheat", acres=2.0)

        # Wheat yield: 20 qtl/acre * 2 = 40 qtl
        self.assertEqual(res["expected_yield_quintals"], 40.0)

        # Govt MSP: ₹2,275/qtl * 40 = ₹91,000.00
        expected_revenue = 40.0 * 2275.0
        self.assertEqual(res["gross_revenue"], expected_revenue)

        # Net Profit = Revenue - Total Cost
        expected_profit = round(expected_revenue - res["total_cultivation_cost"], 2)
        self.assertEqual(res["net_profit"], expected_profit)

        # ROI % = (Net Profit / Total Cost) * 100
        expected_roi = round((expected_profit / res["total_cultivation_cost"]) * 100, 2)
        self.assertEqual(res["roi_percent"], expected_roi)

    # ─── 14. Multi-Crop Comparison ────────────────────────────────────────────

    def test_compare_crops_sorting(self):
        """compare_crops returns all crops sorted by net_profit descending."""
        crop_list = ["Wheat", "Rice", "Maize"]
        comparison = compare_crops(crop_list, acres=2.0)

        self.assertEqual(len(comparison), 3)

        # Check descending order by net profit
        profits = [c["net_profit"] for c in comparison]
        self.assertEqual(profits, sorted(profits, reverse=True))

        # Check required fields exist on each result
        for c in comparison:
            self.assertIn("crop_name", c)
            self.assertIn("input_cost", c)
            self.assertIn("net_profit", c)
            self.assertIn("roi_percent", c)
            self.assertIn("breakdown", c)

    # ─── 15. Backward Compatibility with Flask app.py ─────────────────────────

    def test_backward_compatibility_with_app_py(self):
        """Ensures all dictionary keys expected by app.py and calendar.js exist."""
        crop_dict = {
            "id": 1,
            "name": "Wheat",
            "season": "Rabi",
            "yield_per_acre": 20,
            "price_per_quintal": 2015,
            "cost_per_acre": 8000,
        }
        res = calculate_budget(crop_dict, acres=1.5)

        required_keys = [
            "crop_name", "season", "acres", "input_cost",
            "expected_yield_quintals", "gross_revenue",
            "net_profit", "roi_percent", "breakdown"
        ]
        for key in required_keys:
            self.assertIn(key, res, f"Key '{key}' missing from budget result.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
