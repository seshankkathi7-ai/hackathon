"""
test_farming_calendar.py
========================
Unit tests for farming_calendar.py validating all core requirements:
1. Reading crop_calendar.json
2. Querying tasks by crop name and crop day
3. Returning all tasks scheduled for that day
4. Returning the complete calendar
5. Handling unknown crops and invalid inputs
6. Generating proposed crop plans when planting date is unknown vs. known
7. Ensuring simplicity, reusability, and backward-compatibility
"""

import unittest
from datetime import date, datetime
from pathlib import Path

import farming_calendar as fc
from farming_calendar import (
    CropNotFoundError,
    FarmingCalendar,
    InvalidInputError,
)


class TestFarmingCalendar(unittest.TestCase):
    """Test suite for FarmingCalendar module and class."""

    @classmethod
    def setUpClass(cls):
        """Instantiate a dedicated calendar instance for testing."""
        cls.cal = FarmingCalendar()

    # ─── Requirement 1: Read crop_calendar.json ───────────────────────────────

    def test_load_data(self):
        """Calendar loads valid data containing crops, seasons, and months."""
        data = self.cal.load_data()
        self.assertIn("crops", data)
        self.assertIn("seasons", data)
        self.assertIn("months", data)
        self.assertGreaterEqual(len(data["crops"]), 3)

        crop_names = self.cal.get_available_crop_names()
        self.assertIn("Wheat", crop_names)
        self.assertIn("Rice", crop_names)
        self.assertIn("Maize", crop_names)

    def test_nonexistent_data_file(self):
        """Initializing with a nonexistent path raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            FarmingCalendar("nonexistent_calendar.json")

    # ─── Requirements 2 & 3: Accept crop name and day, return scheduled tasks ─

    def test_get_tasks_for_day_wheat_cri(self):
        """Day 21 in Wheat is the Crown Root Initiation & top-dressing window."""
        tasks = fc.get_tasks_for_day("Wheat", 21)
        self.assertIsInstance(tasks, list)
        self.assertGreaterEqual(len(tasks), 2)

        task_names = [t["task_name"] for t in tasks]
        self.assertTrue(any("Crown Root" in name for name in task_names))
        self.assertTrue(any("Top-Dressing" in name for name in task_names))

        # Check enriched fields
        sample = tasks[0]
        self.assertEqual(sample["crop_name"], "Wheat")
        self.assertIn("stage_name", sample)
        self.assertIn("instructions", sample)
        self.assertIn("materials", sample)
        self.assertIn("safety_precautions", sample)

    def test_get_tasks_for_day_sowing(self):
        """Day 0 corresponds to Sowing Day."""
        tasks = fc.get_tasks_for_day("Wheat", 0)
        task_names = [t["task_name"] for t in tasks]
        self.assertTrue(any("Sowing" in name for name in task_names))
        self.assertTrue(any("Basal Fertilizer" in name for name in task_names))

    def test_get_tasks_for_day_pre_sowing(self):
        """Negative crop days represent pre-sowing activities."""
        # Day -25 should hit Deep Ploughing (scheduled [-28, -21])
        tasks = fc.get_tasks_for_day("Wheat", -25)
        task_names = [t["task_name"] for t in tasks]
        self.assertTrue(any("Deep Ploughing" in name for name in task_names))

    def test_get_tasks_for_day_harvest(self):
        """Day 149 in Wheat is in the maturity & harvesting window."""
        tasks = fc.get_tasks_for_day("Wheat", 149)
        task_names = [t["task_name"] for t in tasks]
        self.assertTrue(any("Harvest" in name or "Maturity" in name for name in task_names))

    def test_get_tasks_for_day_empty(self):
        """A day with no active tasks returns an empty list without error."""
        tasks = fc.get_tasks_for_day("Wheat", 500)
        self.assertEqual(tasks, [])

    def test_get_tasks_for_day_case_insensitive(self):
        """Crop name matching is case-insensitive and trims whitespace."""
        tasks_lower = fc.get_tasks_for_day("wheat", 21)
        tasks_upper = fc.get_tasks_for_day("WHEAT", 21)
        tasks_padded = fc.get_tasks_for_day("  Wheat  ", 21)
        self.assertEqual(len(tasks_lower), len(tasks_upper))
        self.assertEqual(len(tasks_lower), len(tasks_padded))

    def test_get_tasks_for_day_numeric_types(self):
        """Accepts integer, whole float (21.0), or integer string ('21')."""
        t_int = fc.get_tasks_for_day("Wheat", 21)
        t_float = fc.get_tasks_for_day("Wheat", 21.0)
        t_str = fc.get_tasks_for_day("Wheat", "21")
        self.assertEqual(len(t_int), len(t_float))
        self.assertEqual(len(t_int), len(t_str))

    # ─── Requirement 4: Return the complete calendar when requested ───────────

    def test_get_complete_calendar_all(self):
        """get_complete_calendar() without arguments returns full calendar dict."""
        cal_data = fc.get_complete_calendar()
        self.assertIsInstance(cal_data, dict)
        self.assertIn("crops", cal_data)
        self.assertIn("seasons", cal_data)

    def test_get_complete_calendar_single_crop(self):
        """get_complete_calendar('Rice') returns the full calendar for Rice."""
        rice_cal = fc.get_complete_calendar("Rice")
        self.assertIsInstance(rice_cal, dict)
        self.assertEqual(rice_cal["name"], "Rice")
        self.assertEqual(rice_cal["season"], "Kharif")
        self.assertIn("stages", rice_cal)
        # All 11 stages exist
        self.assertEqual(len(rice_cal["stages"]), 11)

    def test_get_crop_schedule_chronological(self):
        """get_crop_schedule returns all tasks sorted by start_day."""
        schedule = fc.get_crop_schedule("Maize")
        self.assertIsInstance(schedule, list)
        self.assertGreaterEqual(len(schedule), 15)

        # Check ascending order by start_day
        start_days = [t["start_day"] for t in schedule]
        self.assertEqual(start_days, sorted(start_days))

    # ─── Requirement 5: Handle unknown crops and invalid inputs ───────────────

    def test_unknown_crop_error(self):
        """Querying an unknown crop raises CropNotFoundError with suggestions."""
        with self.assertRaises(CropNotFoundError) as ctx:
            fc.get_tasks_for_day("Dragonfruit", 10)
        err_msg = str(ctx.exception)
        self.assertIn("Dragonfruit", err_msg)
        self.assertIn("Wheat", err_msg)

    def test_invalid_crop_names(self):
        """None, empty string, or non-string crop names raise InvalidInputError."""
        with self.assertRaises(InvalidInputError):
            fc.get_tasks_for_day("", 10)

        with self.assertRaises(InvalidInputError):
            fc.get_tasks_for_day("   ", 10)

        with self.assertRaises(InvalidInputError):
            fc.get_tasks_for_day(None, 10)

        with self.assertRaises(InvalidInputError):
            fc.get_tasks_for_day(12345, 10)

    def test_invalid_crop_days(self):
        """None, boolean, non-integer floats, and non-numeric strings raise InvalidInputError."""
        with self.assertRaises(InvalidInputError):
            fc.get_tasks_for_day("Wheat", None)

        with self.assertRaises(InvalidInputError):
            fc.get_tasks_for_day("Wheat", True)  # bool rejected

        with self.assertRaises(InvalidInputError):
            fc.get_tasks_for_day("Wheat", 21.5)  # non-integer float

        with self.assertRaises(InvalidInputError):
            fc.get_tasks_for_day("Wheat", "day_twenty_one")  # non-numeric string

    # ─── Requirement 6: Proposed crop plans when planting date is unknown ──────

    def test_proposed_crop_plan_planting_date_unknown(self):
        """
        When planting_date is None, returns a proposed plan based on relative
        crop days, milestone roadmaps, and an illustrative seasonal scenario.
        """
        plan = fc.generate_crop_plan("Wheat")

        self.assertEqual(plan["crop_name"], "Wheat")
        self.assertFalse(plan["planting_date_known"])
        self.assertIsNone(plan["planting_date"])
        self.assertEqual(plan["plan_type"], "PROPOSED_RELATIVE_PLAN")
        self.assertIn("timeline_milestones", plan)
        self.assertIn("schedule", plan)
        self.assertIn("illustrative_scenario", plan)

        # Check schedule tasks have relative day labels and unassigned dates
        first_task = plan["schedule"][0]
        self.assertIn("day_label", first_task)
        self.assertEqual(first_task["scheduled_dates_formatted"], "TBD (relative to planting day)")
        self.assertIsNone(first_task["scheduled_start_date"])

        # Check illustrative scenario
        scenario = plan["illustrative_scenario"]
        self.assertIn("assumed_planting_date", scenario)
        self.assertIn("projected_harvest_date", scenario)

    def test_proposed_crop_plan_planting_date_known(self):
        """
        When planting_date IS known, exact calendar dates are calculated for every task.
        """
        planting = "2026-11-01"
        plan = fc.generate_crop_plan("Wheat", planting_date=planting)

        self.assertTrue(plan["planting_date_known"])
        self.assertEqual(plan["planting_date"], planting)
        self.assertEqual(plan["plan_type"], "SCHEDULED_CALENDAR")
        self.assertNotIn("illustrative_scenario", plan)

        # Find Day 21–25 task (First Top-Dressing of Nitrogen)
        cri_tasks = [t for t in plan["schedule"] if "First Top-Dressing" in t["task_name"]]
        self.assertTrue(len(cri_tasks) > 0)
        cri = cri_tasks[0]

        # Nov 1 + 21 days = Nov 22, 2026
        self.assertEqual(cri["scheduled_start_date"], "2026-11-22")
        # Nov 1 + 25 days = Nov 26, 2026
        self.assertEqual(cri["scheduled_end_date"], "2026-11-26")
        self.assertIn("22 Nov 2026", cri["scheduled_dates_formatted"])

    def test_proposed_crop_plan_datetime_date_object(self):
        """Accepts datetime.date and datetime.datetime objects as planting_date."""
        d_obj = date(2026, 6, 15)
        plan_date = fc.generate_crop_plan("Rice", planting_date=d_obj)
        self.assertEqual(plan_date["planting_date"], "2026-06-15")

        dt_obj = datetime(2026, 6, 15, 10, 30)
        plan_dt = fc.generate_crop_plan("Rice", planting_date=dt_obj)
        self.assertEqual(plan_dt["planting_date"], "2026-06-15")

    def test_proposed_crop_plan_invalid_date(self):
        """Malformatted date strings or invalid types raise InvalidInputError."""
        with self.assertRaises(InvalidInputError):
            fc.generate_crop_plan("Wheat", planting_date="01-11-2026")  # non-ISO

        with self.assertRaises(InvalidInputError):
            fc.generate_crop_plan("Wheat", planting_date="not-a-date")

        with self.assertRaises(InvalidInputError):
            fc.generate_crop_plan("Wheat", planting_date=12345)

    # ─── Backward Compatibility: Functions used by app.py ─────────────────────

    def test_app_py_compatibility(self):
        """Existing helpers for Flask UI continue to function seamlessly."""
        crops = fc.get_all_crops()
        self.assertIsInstance(crops, list)

        crop_1 = fc.get_crop_by_id(1)
        self.assertIsNotNone(crop_1)
        self.assertEqual(crop_1["name"], "Wheat")

        rabi_crops = fc.get_crops_by_season("Rabi")
        self.assertTrue(all(c["season"] == "Rabi" for c in rabi_crops))

        month_10 = fc.get_crops_for_month(10)
        self.assertIsInstance(month_10, list)

        grid = fc.get_calendar_grid()
        self.assertEqual(len(grid), 12)

        season_summary = fc.get_season_summary()
        self.assertIn("Rabi", season_summary)
        self.assertIn("Kharif", season_summary)


if __name__ == "__main__":
    unittest.main(verbosity=2)
