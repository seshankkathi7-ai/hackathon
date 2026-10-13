"""
farming_calendar.py
===================
A modular agricultural calendar engine for Python.

Reads crop_calendar.json and provides:
1. Lookup of tasks scheduled for a specific crop day (relative to sowing).
2. Complete calendar queries for all crops or a single crop.
3. Input validation and custom exceptions for unknown crops and invalid inputs.
4. Proposed crop plans with relative timelines when planting date is unknown,
   or dated calendars when planting date is provided.
5. Backward-compatible helper functions for Flask UI routing.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Import budget calculator for itemized cost attachment.
# Wrapped in try/except so farming_calendar still works standalone.
try:
    import budget_calculator as _bc
    _BC_AVAILABLE = True
except ImportError:  # pragma: no cover
    _bc = None  # type: ignore[assignment]
    _BC_AVAILABLE = False


# ─── Custom Exceptions ────────────────────────────────────────────────────────

class FarmingCalendarError(Exception):
    """Base exception for farming calendar module."""
    pass


class CropNotFoundError(FarmingCalendarError, ValueError, KeyError):
    """Raised when a requested crop cannot be found in the calendar dataset."""
    pass


class InvalidInputError(FarmingCalendarError, ValueError):
    """Raised when an input parameter (crop name, day, date) fails validation."""
    pass


# ─── Core FarmingCalendar Class ───────────────────────────────────────────────

class FarmingCalendar:
    """
    Main engine for reading crop calendar data, scheduling tasks,
    and generating crop plans.
    """

    DEFAULT_DATA_PATH = Path(__file__).resolve().parent / "crop_calendar.json"

    def __init__(self, data_file: Optional[Union[str, Path]] = None) -> None:
        """
        Initialize the calendar engine.
        If data_file is omitted, loads crop_calendar.json from the module directory.
        """
        self.data_path = Path(data_file) if data_file else self.DEFAULT_DATA_PATH
        self._raw_data: Dict[str, Any] = {}
        self._crops_by_name: Dict[str, Dict[str, Any]] = {}
        self._crops_by_id: Dict[int, Dict[str, Any]] = {}
        self.load_data()

    def load_data(self) -> Dict[str, Any]:
        """
        Read and cache crop_calendar.json.
        Validates basic structure and builds fast lookup indexes.
        """
        if not self.data_path.exists():
            raise FileNotFoundError(f"Calendar data file not found at: {self.data_path}")

        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                self._raw_data = json.load(f)
        except json.JSONDecodeError as err:
            raise InvalidInputError(f"Malformed JSON in calendar data: {err}") from err

        if "crops" not in self._raw_data or not isinstance(self._raw_data["crops"], list):
            raise InvalidInputError("Calendar data must contain a 'crops' list.")

        # Re-build indexes
        self._crops_by_name.clear()
        self._crops_by_id.clear()

        for crop in self._raw_data["crops"]:
            name = crop.get("name", "").strip()
            if name:
                self._crops_by_name[name.lower()] = crop
            crop_id = crop.get("id")
            if crop_id is not None:
                self._crops_by_id[int(crop_id)] = crop

        return self._raw_data

    # ─── Helper / Lookup Methods ──────────────────────────────────────────────

    def get_available_crop_names(self) -> List[str]:
        """Return a sorted list of all available crop names in proper casing."""
        return [c.get("name", "") for c in self._raw_data.get("crops", []) if "name" in c]

    def _normalize_crop_name(self, crop_name: Any) -> str:
        """Validate and normalize crop name to lowercase stripped string."""
        if crop_name is None:
            raise InvalidInputError("Crop name cannot be None.")
        if not isinstance(crop_name, str):
            raise InvalidInputError(f"Crop name must be a string, got {type(crop_name).__name__}.")
        clean = crop_name.strip()
        if not clean:
            raise InvalidInputError("Crop name cannot be empty.")
        return clean.lower()

    def _validate_crop_day(self, crop_day: Any) -> int:
        """
        Validate and convert crop_day to an integer.
        Raises InvalidInputError if non-integer or invalid string.
        """
        if crop_day is None:
            raise InvalidInputError("Crop day cannot be None. It must be an integer (e.g. 0, 21, -7).")

        # Reject boolean (since bool is a subclass of int in Python)
        if isinstance(crop_day, bool):
            raise InvalidInputError("Crop day cannot be a boolean value.")

        if isinstance(crop_day, int):
            return crop_day

        if isinstance(crop_day, float):
            if crop_day.is_integer():
                return int(crop_day)
            raise InvalidInputError(f"Crop day must be a whole integer, got decimal float: {crop_day}.")

        if isinstance(crop_day, str):
            clean = crop_day.strip()
            # Allow strings like "21", "-7", "+10"
            if re.match(r"^[-+]?\d+$", clean):
                return int(clean)
            raise InvalidInputError(f"Crop day must be an integer, got invalid string: {crop_day!r}.")

        raise InvalidInputError(f"Invalid type for crop day: {type(crop_day).__name__}. Must be integer.")

    def _validate_acres(self, acres: Any) -> float:
        """
        Validate that acres is a positive real number.
        Defaults to 1.0 if acres is None.
        Raises InvalidInputError if invalid.
        """
        if acres is None:
            return 1.0

        if isinstance(acres, bool):
            raise InvalidInputError("Acreage cannot be a boolean value.")

        try:
            val = float(acres)
        except (TypeError, ValueError) as err:
            raise InvalidInputError(f"Acreage must be a numeric value, got {acres!r}.") from err

        import math
        if math.isnan(val) or math.isinf(val) or val <= 0:
            raise InvalidInputError(f"Acreage must be strictly greater than 0, got {val}.")

        return val

    def get_crop(self, crop_name: str) -> Dict[str, Any]:
        """
        Retrieve crop dictionary by name (case-insensitive).
        Raises CropNotFoundError if not found.
        """
        norm_name = self._normalize_crop_name(crop_name)
        if norm_name not in self._crops_by_name:
            available = ", ".join(self.get_available_crop_names()) or "None"
            raise CropNotFoundError(
                f"Crop '{crop_name}' not found. Available crops: {available}"
            )
        return self._crops_by_name[norm_name]

    def get_crop_by_id(self, crop_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve crop dictionary by integer ID, or None if not found."""
        return self._crops_by_id.get(int(crop_id))

    # ─── Schedule Resolution ──────────────────────────────────────────────────

    def _resolve_task_days(self, task: Dict[str, Any], stage_key: str, crop_duration: int) -> Tuple[int, int, Optional[List[int]]]:
        """
        Resolve the (start_day, end_day, discrete_days) for a given task.
        Priority:
        1. Explicit task['start_day'] and task['end_day'] (or task['day_range'])
        2. Extracted days from timing string or heuristic fallback.
        """
        discrete_days = task.get("discrete_days")

        if "start_day" in task and "end_day" in task:
            return int(task["start_day"]), int(task["end_day"]), discrete_days

        if "day_range" in task and isinstance(task["day_range"], (list, tuple)) and len(task["day_range"]) == 2:
            return int(task["day_range"][0]), int(task["day_range"][1]), discrete_days

        # Heuristic fallback based on stage if no explicit days found
        timing = task.get("timing", "").lower()

        # Check for weeks before sowing
        m_weeks_before = re.search(r"(\d+)\s*[–-]\s*(\d+)\s*weeks?\s+before", timing)
        if m_weeks_before:
            w1, w2 = int(m_weeks_before.group(1)), int(m_weeks_before.group(2))
            return -max(w1, w2) * 7, -min(w1, w2) * 7, None

        # Check for days before sowing
        m_days_before = re.search(r"(\d+)\s*[–-]\s*(\d+)\s*days?\s+before", timing)
        if m_days_before:
            d1, d2 = int(m_days_before.group(1)), int(m_days_before.group(2))
            return -max(d1, d2), -min(d1, d2), None

        # Check for hours before sowing
        if "hours before" in timing:
            return -1, 0, None

        # Check for DAS / DAT range
        m_das_range = re.search(r"(\d+)\s*[–-]\s*(\d+)\s*(?:days?\s+after\s+sowing|das|dat)", timing)
        if m_das_range:
            return int(m_das_range.group(1)), int(m_das_range.group(2)), None

        # Check for sowing
        if "at the time of sowing" in timing or "at sowing" in timing:
            return 0, 0, None

        # Stage based broad fallback
        stage_fallbacks = {
            "land_preparation": (-28, -7),
            "seed_selection": (-14, 0),
            "sowing": (0, 0),
            "fertilizer_application": (0, 30),
            "irrigation": (20, 80),
            "weed_management": (1, 35),
            "pest_disease_monitoring": (20, 80),
            "crop_growth_monitoring": (10, 60),
            "harvesting": (crop_duration - 5, crop_duration),
            "post_harvest_handling": (crop_duration + 1, crop_duration + 7),
            "selling_produce": (crop_duration + 5, crop_duration + 20),
        }
        return stage_fallbacks.get(stage_key, (0, crop_duration)) + (None,)

    def _task_matches_day(self, start_day: int, end_day: int, discrete_days: Optional[List[int]], crop_day: int) -> bool:
        """Determine if a task is active on a specific crop day."""
        if discrete_days:
            if crop_day in discrete_days:
                return True
        return start_day <= crop_day <= end_day

    # ─── Requirement 3: Return all tasks scheduled for that day ───────────────

    def get_tasks_for_day(
        self, crop_name: str, crop_day: Any, acres: Any = 1.0
    ) -> List[Dict[str, Any]]:
        """
        Accept a crop name and crop day, and return all tasks scheduled for that day
        enriched with itemized material requirements, quantities based on acreage,
        unit prices, individual item costs, and daily estimated total.

        Parameters:
            crop_name (str): Name of the crop (e.g. "Wheat", "Rice", "Maize").
            crop_day (int): Integer day relative to sowing (Day 0 = Sowing day,
                            negative days = pre-sowing tasks).
            acres (float): Land area in acres (default 1.0).

        Returns:
            List[Dict[str, Any]]: List of matching task dictionaries enriched with
                                  stage info, crop name, schedule bounds, itemized items,
                                  individual costs, and daily total.
        """
        crop = self.get_crop(crop_name)
        target_day = self._validate_crop_day(crop_day)
        land_area = self._validate_acres(acres)
        crop_duration = crop.get("duration_days", 120)

        scheduled_tasks: List[Dict[str, Any]] = []

        stages = crop.get("stages", {})
        for stage_key, stage_info in stages.items():
            stage_name = stage_info.get("stage_name", stage_key.replace("_", " ").title())
            stage_number = stage_info.get("stage_number", 0)

            for task in stage_info.get("tasks", []):
                start_day, end_day, discrete_days = self._resolve_task_days(task, stage_key, crop_duration)

                if self._task_matches_day(start_day, end_day, discrete_days, target_day):
                    enriched = dict(task)
                    enriched["crop_name"] = crop.get("name", crop_name)
                    enriched["stage_key"] = stage_key
                    enriched["stage_name"] = stage_name
                    enriched["stage_number"] = stage_number
                    enriched["query_day"] = target_day
                    enriched["start_day"] = start_day
                    enriched["end_day"] = end_day
                    enriched["day_range"] = [start_day, end_day]
                    enriched["acres"] = land_area
                    if discrete_days:
                        enriched["discrete_days"] = discrete_days

                    # Itemized cost calculation based on acreage
                    if _BC_AVAILABLE and _bc is not None:
                        costed = _bc.calculate_task_items_and_cost(enriched, land_area)
                        enriched["items"] = costed["items"]
                        enriched["task_total"] = costed["task_total"]
                        enriched["task_total_cost"] = costed["task_total"]
                        enriched["task_is_complete"] = costed["task_is_complete"]
                        enriched["missing_price_items"] = costed["missing_price_items"]
                    else:
                        enriched["task_total"] = 0.0
                        enriched["task_total_cost"] = 0.0
                        enriched["task_is_complete"] = True
                        enriched["missing_price_items"] = []

                    enriched["necessary_precautions"] = enriched.get("safety_precautions", [])
                    scheduled_tasks.append(enriched)

        # Sort tasks by stage number then start day
        scheduled_tasks.sort(key=lambda t: (t.get("stage_number", 0), t.get("start_day", 0)))

        # Daily total is the sum of known costs of all items used for that day's tasks
        daily_total = round(sum(t.get("task_total", 0.0) for t in scheduled_tasks), 2)
        for t in scheduled_tasks:
            t["daily_total"] = daily_total

        return scheduled_tasks

    # ─── Requirement 4: Return the complete calendar when requested ───────────

    def get_complete_calendar(
        self, crop_name: Optional[str] = None, acres: Any = None
    ) -> Dict[str, Any]:
        """
        Return the complete calendar data.
        - If crop_name is None, returns the entire calendar JSON data (all crops,
          seasons, months, and metadata).
        - If crop_name is specified, returns the complete crop lifecycle calendar
          covering all stages from land preparation to selling, enriched with
          per-item quantities scaled to acreage, unit prices, individual item costs,
          daily totals, and the authoritative lifecycle budget without double-counting.
        """
        if crop_name is None:
            return dict(self._raw_data)

        crop = self.get_crop(crop_name)
        land_area = self._validate_acres(acres)
        crop_duration = crop.get("duration_days", 120)

        # Build an enriched deep copy of the crop calendar
        enriched_crop = dict(crop)
        enriched_crop["acres"] = land_area
        enriched_stages: Dict[str, Any] = {}
        all_tasks_costed: List[Dict[str, Any]] = []

        for stage_key, stage_info in crop.get("stages", {}).items():
            st_copy = dict(stage_info)
            stage_name = stage_info.get("stage_name", stage_key.replace("_", " ").title())
            stage_number = stage_info.get("stage_number", 0)
            task_list: List[Dict[str, Any]] = []

            for task in stage_info.get("tasks", []):
                s_day, e_day, discrete = self._resolve_task_days(task, stage_key, crop_duration)
                t_copy = dict(task)
                t_copy["crop_name"] = crop.get("name", crop_name)
                t_copy["stage_key"] = stage_key
                t_copy["stage_name"] = stage_name
                t_copy["stage_number"] = stage_number
                t_copy["start_day"] = s_day
                t_copy["end_day"] = e_day
                t_copy["day_range"] = [s_day, e_day]
                t_copy["acres"] = land_area
                if discrete:
                    t_copy["discrete_days"] = discrete

                if _BC_AVAILABLE and _bc is not None:
                    costed = _bc.calculate_task_items_and_cost(t_copy, land_area)
                    t_copy["items"] = costed["items"]
                    t_copy["task_total"] = costed["task_total"]
                    t_copy["task_total_cost"] = costed["task_total"]
                    t_copy["task_is_complete"] = costed["task_is_complete"]
                    t_copy["missing_price_items"] = costed["missing_price_items"]
                else:
                    t_copy["task_total"] = 0.0
                    t_copy["task_total_cost"] = 0.0
                    t_copy["task_is_complete"] = True
                    t_copy["missing_price_items"] = []

                t_copy["necessary_precautions"] = t_copy.get("safety_precautions", [])
                task_list.append(t_copy)
                all_tasks_costed.append(t_copy)

            st_copy["stage_total"] = round(sum(t.get("task_total", 0.0) for t in task_list), 2)
            st_copy["tasks"] = task_list
            enriched_stages[stage_key] = st_copy

        # Compute daily totals: group tasks by start_day
        day_to_tasks: Dict[int, List[Dict[str, Any]]] = {}
        for t in all_tasks_costed:
            s_d = t.get("start_day", 0)
            day_to_tasks.setdefault(s_d, []).append(t)

        for s_d, day_tasks in day_to_tasks.items():
            d_total = round(sum(t.get("task_total", 0.0) for t in day_tasks), 2)
            for t in day_tasks:
                t["daily_total"] = d_total

        enriched_crop["stages"] = enriched_stages

        # Attach complete crop-cycle budget without double counting
        if _BC_AVAILABLE and _bc is not None:
            try:
                b_info = _bc.calculate_lifecycle_budget_from_calendar(
                    crop.get("name", crop_name), land_area
                )
                enriched_crop["lifecycle_budget"] = b_info["lifecycle_budget"]
                enriched_crop["lifecycle_budget_breakdown"] = b_info["lifecycle_budget_breakdown"]
                enriched_crop["lifecycle_budget_is_complete"] = b_info["lifecycle_budget_is_complete"]
                enriched_crop["lifecycle_task_total"] = b_info["lifecycle_task_total"]
                enriched_crop["data_source_note"] = b_info.get("data_source_note", "")
            except Exception:
                pass

        return enriched_crop

    def get_crop_schedule(
        self, crop_name: str, acres: Any = 1.0
    ) -> List[Dict[str, Any]]:
        """
        Return a flattened, chronologically ordered list of all tasks for a given crop.
        Sorted by start_day from earliest pre-sowing task to post-harvest selling.
        Each task is enriched with itemized costs scaled to the specified acreage.
        """
        crop = self.get_crop(crop_name)
        land_area = self._validate_acres(acres)
        crop_duration = crop.get("duration_days", 120)
        schedule: List[Dict[str, Any]] = []

        for stage_key, stage_info in crop.get("stages", {}).items():
            for task in stage_info.get("tasks", []):
                s_day, e_day, discrete = self._resolve_task_days(task, stage_key, crop_duration)
                entry = dict(task)
                entry["crop_name"] = crop.get("name", crop_name)
                entry["stage_key"] = stage_key
                entry["stage_name"] = stage_info.get("stage_name", stage_key.title())
                entry["stage_number"] = stage_info.get("stage_number", 0)
                entry["start_day"] = s_day
                entry["end_day"] = e_day
                entry["day_range"] = [s_day, e_day]
                entry["acres"] = land_area
                if discrete:
                    entry["discrete_days"] = discrete

                if _BC_AVAILABLE and _bc is not None:
                    costed = _bc.calculate_task_items_and_cost(entry, land_area)
                    entry["items"] = costed["items"]
                    entry["task_total"] = costed["task_total"]
                    entry["task_total_cost"] = costed["task_total"]
                    entry["task_is_complete"] = costed["task_is_complete"]
                    entry["missing_price_items"] = costed["missing_price_items"]
                else:
                    entry["task_total"] = 0.0
                    entry["task_total_cost"] = 0.0
                    entry["task_is_complete"] = True
                    entry["missing_price_items"] = []

                entry["necessary_precautions"] = entry.get("safety_precautions", [])
                schedule.append(entry)

        schedule.sort(key=lambda t: (t["start_day"], t.get("stage_number", 0)))

        # Attach daily totals
        day_to_tasks: Dict[int, List[Dict[str, Any]]] = {}
        for t in schedule:
            s_d = t.get("start_day", 0)
            day_to_tasks.setdefault(s_d, []).append(t)

        for s_d, day_tasks in day_to_tasks.items():
            d_total = round(sum(t.get("task_total", 0.0) for t in day_tasks), 2)
            for t in day_tasks:
                t["daily_total"] = d_total

        return schedule

    # ─── Requirement 6: Support proposed crop plans when planting date is unknown ──

    def generate_crop_plan(
        self,
        crop_name: str,
        planting_date: Optional[Union[str, date, datetime]] = None,
        acres: Any = 1.0,
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive crop plan.

        If planting_date is NOT known (None):
            Returns a proposed crop plan based on relative crop days (Days relative
            to Sowing Day = 0), phase milestones, recommended seasonal window,
            itemized tasks scaled to acreage, and an illustrative projected scenario.

        If planting_date IS known:
            Calculates exact calendar dates (start_date, end_date) for every task
            and milestone based on the given sowing date, with itemized costs.

        Parameters:
            crop_name (str): The crop name to plan for.
            planting_date (str | date | datetime | None): Optional planting date.
                Can be an ISO date string "YYYY-MM-DD", date, or datetime object.
            acres (float): Land area in acres (default 1.0).
        """
        crop = self.get_crop(crop_name)
        land_area = self._validate_acres(acres)
        crop_duration = int(crop.get("duration_days", 120))
        canonical_name = crop.get("name", crop_name)

        # Parse planting date if provided
        parsed_planting_date: Optional[date] = None
        if planting_date is not None:
            if isinstance(planting_date, datetime):
                parsed_planting_date = planting_date.date()
            elif isinstance(planting_date, date):
                parsed_planting_date = planting_date
            elif isinstance(planting_date, str):
                clean_date = planting_date.strip()
                try:
                    parsed_planting_date = datetime.strptime(clean_date, "%Y-%m-%d").date()
                except ValueError as err:
                    raise InvalidInputError(
                        f"Invalid planting date format: '{planting_date}'. Expected 'YYYY-MM-DD'."
                    ) from err
            else:
                raise InvalidInputError(
                    f"Unsupported type for planting_date: {type(planting_date).__name__}."
                )

        planting_date_known = parsed_planting_date is not None

        # Build chronological task schedule scaled to acres
        raw_schedule = self.get_crop_schedule(canonical_name, acres=land_area)
        planned_tasks: List[Dict[str, Any]] = []

        for task in raw_schedule:
            t = dict(task)
            s_day = t["start_day"]
            e_day = t["end_day"]

            # Format relative timing label
            if s_day < 0 and e_day < 0:
                day_label = f"Day {s_day} to {e_day} (Pre-sowing)"
            elif s_day == 0 and e_day == 0:
                day_label = "Day 0 (Sowing Day)"
            elif s_day == e_day:
                day_label = f"Day {s_day} after sowing"
            else:
                day_label = f"Day {s_day} to {e_day} after sowing"
            t["day_label"] = day_label

            # Categorize growth phase
            if e_day < 0:
                t["phase"] = "Pre-Planting Preparation"
            elif s_day <= 0 <= e_day:
                t["phase"] = "Sowing & Basal"
            elif e_day <= 30:
                t["phase"] = "Early Vegetative"
            elif e_day <= 70:
                t["phase"] = "Active Tillering & Mid-Season"
            elif e_day <= crop_duration:
                t["phase"] = "Reproductive & Maturation"
            else:
                t["phase"] = "Post-Harvest & Marketing"

            # Compute actual dates if planting date is known
            if planting_date_known and parsed_planting_date:
                task_start_date = parsed_planting_date + timedelta(days=s_day)
                task_end_date = parsed_planting_date + timedelta(days=e_day)
                t["scheduled_start_date"] = task_start_date.isoformat()
                t["scheduled_end_date"] = task_end_date.isoformat()
                t["scheduled_dates_formatted"] = (
                    task_start_date.strftime("%d %b %Y")
                    if s_day == e_day
                    else f"{task_start_date.strftime('%d %b %Y')} – {task_end_date.strftime('%d %b %Y')}"
                )
            else:
                t["scheduled_start_date"] = None
                t["scheduled_end_date"] = None
                t["scheduled_dates_formatted"] = "TBD (relative to planting day)"

            planned_tasks.append(t)

        # Milestone roadmap
        milestones = [
            {"milestone": "Land Preparation & Soil Testing", "crop_day_range": [-42, -7], "description": "Tillage, soil sampling, and field leveling."},
            {"milestone": "Seed Selection & Treatment", "crop_day_range": [-28, 0], "description": "Procure certified seed and complete seed treatment."},
            {"milestone": "Sowing Day (Day 0)", "crop_day_range": [0, 0], "description": "Primary sowing and basal fertilizer incorporation."},
            {"milestone": "Early Vegetative & First Irrigation", "crop_day_range": [20, 25], "description": "Critical crown root/active tillering irrigation & N top-dressing."},
            {"milestone": "Weed & Pest Control Window", "crop_day_range": [1, 45], "description": "Pre-emergence herbicide and scouting for key pests."},
            {"milestone": "Reproductive / Mid-Season Growth", "crop_day_range": [40, 90], "description": "Panicle/tassel management, foliar checks, jointing irrigation."},
            {"milestone": "Harvest Window", "crop_day_range": [crop_duration - 5, crop_duration], "description": "Maturity assessment and grain harvesting."},
            {"milestone": "Post-Harvest Handling & Selling", "crop_day_range": [crop_duration + 1, crop_duration + 20], "description": "Drying, safe godown storage, and market sales."},
        ]

        # Attach dates to milestones if planting date is known
        if planting_date_known and parsed_planting_date:
            for m in milestones:
                m_start = parsed_planting_date + timedelta(days=m["crop_day_range"][0])
                m_end = parsed_planting_date + timedelta(days=m["crop_day_range"][1])
                m["projected_dates"] = f"{m_start.strftime('%d %b %Y')} – {m_end.strftime('%d %b %Y')}"
        else:
            for m in milestones:
                m["projected_dates"] = "Pending planting date"

        # Month names reference
        months_ref = self._raw_data.get("months", [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ])
        sow_m_idx = crop.get("sowing_month", 1) - 1
        harv_m_idx = crop.get("harvesting_month", 1) - 1
        typical_sowing_month = months_ref[sow_m_idx] if 0 <= sow_m_idx < len(months_ref) else "N/A"
        typical_harvest_month = months_ref[harv_m_idx] if 0 <= harv_m_idx < len(months_ref) else "N/A"

        # Build proposed plan dictionary
        plan: Dict[str, Any] = {
            "crop_name": canonical_name,
            "season": crop.get("season", "N/A"),
            "acres": land_area,
            "duration_days": crop_duration,
            "planting_date_known": planting_date_known,
            "planting_date": parsed_planting_date.isoformat() if parsed_planting_date else None,
            "plan_type": (
                "SCHEDULED_CALENDAR"
                if planting_date_known
                else "PROPOSED_RELATIVE_PLAN"
            ),
            "status": (
                f"Definitive calendar based on planting date {parsed_planting_date.isoformat()}"
                if planting_date_known
                else "Proposed crop schedule (all timings relative to Sowing Day 0). Set a planting date to anchor specific calendar dates."
            ),
            "agronomic_profile": {
                "water_need": crop.get("water_need", "Medium"),
                "soil_type": crop.get("soil_type", "Loamy"),
                "color": crop.get("color", "#4caf50"),
                "short_description": crop.get("short_description", ""),
                "recommended_sowing_month": typical_sowing_month,
                "recommended_harvest_month": typical_harvest_month,
            },
            "timeline_milestones": milestones,
            "tasks_count": len(planned_tasks),
            "schedule": planned_tasks,
        }

        # Attach complete crop-cycle budget without double counting
        if _BC_AVAILABLE and _bc is not None:
            try:
                b_info = _bc.calculate_lifecycle_budget_from_calendar(canonical_name, land_area)
                plan["lifecycle_budget"] = b_info["lifecycle_budget"]
                plan["lifecycle_budget_breakdown"] = b_info["lifecycle_budget_breakdown"]
                plan["lifecycle_budget_is_complete"] = b_info["lifecycle_budget_is_complete"]
                plan["lifecycle_task_total"] = b_info["lifecycle_task_total"]
            except Exception:
                pass

        # If planting date is not known, provide an illustrative projected scenario
        if not planting_date_known:
            now_year = datetime.now().year
            target_month = crop.get("sowing_month", 10)
            # Default to the 1st of the crop's recommended sowing month
            projected_sow_date = date(now_year, target_month, 1)
            projected_harv_date = projected_sow_date + timedelta(days=crop_duration)
            plan["illustrative_scenario"] = {
                "note": (
                    f"This is an illustrative scenario assuming you plant on "
                    f"{projected_sow_date.strftime('%d %B %Y')} (typical {typical_sowing_month} window)."
                ),
                "assumed_planting_date": projected_sow_date.isoformat(),
                "projected_harvest_date": projected_harv_date.isoformat(),
                "duration_days": crop_duration,
            }

        return plan


# ─── Module-Level Singleton & Functions ───────────────────────────────────────
# Provides simple and reusable functional API matching all requirements,
# while preserving complete compatibility with existing app.py endpoints.

_default_calendar = FarmingCalendar()


def reload_calendar(data_file: Optional[Union[str, Path]] = None) -> None:
    """Reload the global default calendar instance."""
    global _default_calendar
    _default_calendar = FarmingCalendar(data_file)


# ─── Functional API (Requirements 2, 3, 4, 6) ─────────────────────────────────

def get_tasks_for_day(crop_name: str, crop_day: Any, acres: Any = 1.0) -> List[Dict[str, Any]]:
    """
    Accept a crop name and crop day, and return all tasks scheduled for that day.

    Example:
        >>> tasks = get_tasks_for_day("Wheat", 21)
    """
    return _default_calendar.get_tasks_for_day(crop_name, crop_day, acres=acres)


def get_complete_calendar(crop_name: Optional[str] = None, acres: Any = None) -> Dict[str, Any]:
    """
    Return the complete calendar data.
    - If crop_name is None, returns the entire calendar dataset.
    - If crop_name is specified, returns that crop's complete calendar with all stages and tasks.
    """
    return _default_calendar.get_complete_calendar(crop_name, acres=acres)


def get_crop_schedule(crop_name: str, acres: Any = 1.0) -> List[Dict[str, Any]]:
    """Return a chronologically ordered list of all tasks for the given crop."""
    return _default_calendar.get_crop_schedule(crop_name, acres=acres)


def generate_crop_plan(
    crop_name: str,
    planting_date: Optional[Union[str, date, datetime]] = None,
    acres: Any = 1.0,
) -> Dict[str, Any]:
    """
    Generate a proposed crop plan when planting date is unknown,
    or a dated calendar when planting date is provided.
    """
    return _default_calendar.generate_crop_plan(crop_name, planting_date, acres=acres)


# ─── Backward-Compatible Helpers for app.py ───────────────────────────────────

def load_data() -> Dict[str, Any]:
    """Load the raw calendar JSON data."""
    return _default_calendar.get_complete_calendar()


def get_all_crops() -> List[Dict[str, Any]]:
    """Return list of all crop objects."""
    return _default_calendar.get_complete_calendar().get("crops", [])


def get_crop_by_name(crop_name: str) -> Dict[str, Any]:
    """Return a crop by name (case-insensitive)."""
    return _default_calendar.get_crop(crop_name)


def get_crop_by_id(crop_id: int) -> Optional[Dict[str, Any]]:
    """Return a single crop by integer ID."""
    return _default_calendar.get_crop_by_id(crop_id)


def get_crops_by_season(season: str) -> List[Dict[str, Any]]:
    """Return crops filtered by season (Kharif / Rabi / Zaid)."""
    if not season:
        return []
    target = season.strip().lower()
    return [c for c in get_all_crops() if c.get("season", "").strip().lower() == target]


def get_current_season() -> str:
    """Determine the current agricultural season based on the month."""
    month = datetime.now().month
    if 6 <= month <= 10:
        return "Kharif"
    elif month in (11, 12) or 1 <= month <= 3:
        return "Rabi"
    else:
        return "Zaid"


def get_crops_for_month(month: int) -> List[Dict[str, Any]]:
    """
    Return crops active in the given month index (1–12).
    Handles windows wrapping around December (e.g. Oct -> Mar).
    """
    if not 1 <= month <= 12:
        raise InvalidInputError(f"Month must be between 1 and 12, got: {month}")

    results = []
    for crop in get_all_crops():
        sow = crop.get("sowing_month", 1)
        harv = crop.get("harvesting_month", 12)
        if sow <= harv:
            in_window = sow <= month <= harv
        else:
            in_window = (month >= sow) or (month <= harv)
        if in_window:
            results.append(crop)
    return results


def get_calendar_grid() -> List[Dict[str, Any]]:
    """
    Build a 12-month calendar grid used by templates/calendar.html.
    Each entry: { month_index, month_name, season, season_color, active_crops }
    """
    data = _default_calendar.get_complete_calendar()
    months = data.get("months", [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ])
    seasons_info = data.get("seasons", {})
    grid = []

    for idx, month_name in enumerate(months, start=1):
        if 6 <= idx <= 10:
            season = "Kharif"
        elif idx in (11, 12) or 1 <= idx <= 3:
            season = "Rabi"
        else:
            season = "Zaid"

        season_color = seasons_info.get(season, {}).get("color", "#4caf50")
        active = get_crops_for_month(idx)
        grid.append({
            "month_index": idx,
            "month_name": month_name,
            "season": season,
            "season_color": season_color,
            "active_crops": active,
        })
    return grid


def get_season_summary() -> Dict[str, Any]:
    """Return season metadata dictionary."""
    return _default_calendar.get_complete_calendar().get("seasons", {})


# ─── Simple CLI Demo ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Ensure UTF-8 output on Windows consoles if supported
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("[*] Farming Calendar Module Initialized.")
    crops = _default_calendar.get_available_crop_names()
    print(f"Available crops: {', '.join(crops)}")

    if len(sys.argv) > 2 and sys.argv[1].lower() == "day":
        crop_arg = sys.argv[2]
        day_arg = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        tasks = get_tasks_for_day(crop_arg, day_arg)
        print(f"\nTasks for {crop_arg} on Day {day_arg} ({len(tasks)} found):")
        for t in tasks:
            print(f"  - [{t['stage_name']}] {t['task_name']} ({t.get('day_label', t['timing'])})")
    elif len(sys.argv) > 2 and sys.argv[1].lower() == "plan":
        crop_arg = sys.argv[2]
        plan = generate_crop_plan(crop_arg)
        print(f"\nProposed plan for {plan['crop_name']} ({plan['duration_days']} days, {plan['season']}):")
        print(f"Status: {plan['status']}")
        print(f"Total tasks scheduled: {plan['tasks_count']}")
        for m in plan["timeline_milestones"]:
            print(f"  * {m['milestone']}: Day {m['crop_day_range'][0]} to {m['crop_day_range'][1]} -> {m['description']}")
    else:
        # Sample run: Wheat Day 21
        print("\n[Sample Run] Querying Wheat on Day 21 (CRI stage):")
        sample_tasks = get_tasks_for_day("Wheat", 21)
        for t in sample_tasks:
            print(f"  - [{t['stage_name']}] {t['task_name']}")
        print("\n[Sample Run] Generating proposed plan for Rice (planting date unknown):")
        sample_plan = generate_crop_plan("Rice")
        print(f"  Plan status: {sample_plan['status']}")
        print(f"  Tasks in plan: {sample_plan['tasks_count']}")
