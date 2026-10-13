"""
app.py
======
Modular Flask backend for the Farming Calendar Module.

API Endpoints:
1. GET  /api/calendar     — Returns the complete crop calendar (or single crop if specified).
2. GET  /api/today-tasks  — Returns tasks applicable to the specified crop day.
3. POST /api/task-cost    — Calculates quantities and costs for a specific task.

Also provides:
- GET  /api/crops         — List crops with optional ?season filter.
- GET  /api/crops/<id>    — Detail for a single crop.
- GET  /api/month/<1-12>  — Crops active in a specific month.
- POST /api/budget        — Comprehensive season budget calculator.
- POST /api/compare       — Crop comparison by net profit.
- GET  /api/crop-plan     — Proposed relative or dated crop plan.
- GET  /                  — Web UI dashboard.

Modularity:
- Exposes `calendar_api` Blueprint (url_prefix="/api") for seamless mounting into another Flask app:
    from app import calendar_api
    another_app.register_blueprint(calendar_api)
- Exposes `create_app()` factory function.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, Optional

from flask import Blueprint, Flask, jsonify, render_template, request

import budget_calculator as bc
import farming_calendar as fc

# ─── Blueprint Definition ─────────────────────────────────────────────────────

calendar_api = Blueprint("calendar_api", __name__, url_prefix="/api")
api_bp = calendar_api  # Convenient alias for integration


# ─── Helper Functions for Input Validation ────────────────────────────────────

def _parse_crop_param(crop_val: Any) -> Optional[Dict[str, Any]]:
    """Resolve crop from integer ID, string ID, or crop name."""
    if crop_val is None:
        return None

    crop_str = str(crop_val).strip()
    if not crop_str:
        return None

    # Check if integer ID
    if crop_str.isdigit():
        crop = fc.get_crop_by_id(int(crop_str))
        if crop:
            return crop

    # Check by name
    try:
        return fc.get_crop_by_name(crop_str)
    except fc.CropNotFoundError:
        return None


# ─── 1. GET /api/calendar — Returns Complete Crop Calendar ────────────────────

@calendar_api.route("/calendar", methods=["GET"])
def api_calendar():
    """
    GET /api/calendar
    Returns the complete crop calendar.

    Query Parameters (optional):
        - crop: Crop name (e.g. ?crop=Wheat) -> returns complete calendar for that crop.
        - crop_id: Crop integer ID (e.g. ?crop_id=1) -> returns complete calendar for that crop.
        - grid: If 'true', returns the 12-month calendar grid used by calendar views.
    """
    grid_param = request.args.get("grid", "").strip().lower()
    if grid_param in ("true", "1", "yes"):
        return jsonify(fc.get_calendar_grid()), 200

    crop_name = request.args.get("crop")
    crop_id = request.args.get("crop_id")
    acres_arg = request.args.get("acres")

    acres_val = None
    if acres_arg is not None:
        try:
            acres_val = float(acres_arg)
            if acres_val <= 0:
                return jsonify({"error": f"Invalid 'acres' parameter: '{acres_arg}'. Must be greater than 0."}), 400
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid 'acres' parameter: '{acres_arg}'. Must be a positive number."}), 400

    # If specific crop requested
    if crop_id:
        if not crop_id.isdigit():
            return jsonify({"error": f"Invalid crop_id: '{crop_id}'. Must be an integer."}), 400
        crop = fc.get_crop_by_id(int(crop_id))
        if not crop:
            return jsonify({"error": f"Crop with id {crop_id} not found."}), 404
        return jsonify(fc.get_complete_calendar(crop["name"], acres=acres_val)), 200

    if crop_name:
        try:
            crop_data = fc.get_complete_calendar(crop_name, acres=acres_val)
            return jsonify(crop_data), 200
        except fc.CropNotFoundError as err:
            return jsonify({"error": str(err)}), 404
        except fc.InvalidInputError as err:
            return jsonify({"error": str(err)}), 400

    # Default: Return complete calendar dataset
    complete_cal = fc.get_complete_calendar(acres=acres_val)
    return jsonify(complete_cal), 200


# ─── 2. GET /api/today-tasks — Tasks for Specified Crop Day ───────────────────

@calendar_api.route("/today-tasks", methods=["GET"])
def api_today_tasks():
    """
    GET /api/today-tasks
    Returns tasks applicable to the specified crop day.

    Query Parameters:
        - crop (or crop_name, crop_id): Required. Name or ID of the crop.
        - day (or crop_day): Integer day in crop cycle (0 = sowing day, negative = pre-sowing).
        - acres: Optional float. Land area in acres (default 1.0).
        - planting_date: Optional date (YYYY-MM-DD). If 'day' is omitted, computes current
                         crop day as (today - planting_date).days.
    """
    crop_arg = request.args.get("crop") or request.args.get("crop_name") or request.args.get("crop_id")
    if not crop_arg:
        return jsonify({"error": "Query parameter 'crop' (or 'crop_id') is required."}), 400

    crop = _parse_crop_param(crop_arg)
    if not crop:
        avail = ", ".join(fc.FarmingCalendar().get_available_crop_names())
        return jsonify({"error": f"Crop '{crop_arg}' not found. Available crops: {avail}"}), 404

    canonical_crop_name = crop["name"]

    # Resolve acreage
    acres_arg = request.args.get("acres")
    acres_val = 1.0
    if acres_arg is not None:
        try:
            acres_val = float(acres_arg)
            if acres_val <= 0:
                return jsonify({"error": f"Invalid 'acres' parameter: '{acres_arg}'. Must be greater than 0."}), 400
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid 'acres' parameter: '{acres_arg}'. Must be a positive number."}), 400

    # Resolve crop day
    day_arg = request.args.get("day") if request.args.get("day") is not None else request.args.get("crop_day")
    planting_date_arg = request.args.get("planting_date") or request.args.get("date")

    target_day: int

    if day_arg is not None:
        clean_day = str(day_arg).strip()
        if not re.match(r"^[-+]?\d+$", clean_day):
            return jsonify({"error": f"Invalid 'day' parameter: '{day_arg}'. Must be an integer (e.g. 0, 21, -7)."}), 400
        target_day = int(clean_day)
    elif planting_date_arg:
        try:
            p_date = datetime.strptime(planting_date_arg.strip(), "%Y-%m-%d").date()
            today_date = date.today()
            target_day = (today_date - p_date).days
        except ValueError:
            return jsonify({"error": f"Invalid 'planting_date': '{planting_date_arg}'. Expected 'YYYY-MM-DD'."}), 400
    else:
        return jsonify({
            "error": "Either 'day' (integer crop day) or 'planting_date' (YYYY-MM-DD) query parameter is required."
        }), 400

    try:
        tasks = fc.get_tasks_for_day(canonical_crop_name, target_day, acres=acres_val)
    except (fc.CropNotFoundError, fc.InvalidInputError) as err:
        return jsonify({"error": str(err)}), 400

    # Daily total is sum of known costs of all items used for that day's tasks
    daily_total = round(sum(t.get("task_total", 0.0) for t in tasks), 2)

    response_data = {
        "crop": canonical_crop_name,
        "season": crop.get("season", "N/A"),
        "crop_day": target_day,
        "acres": acres_val,
        "tasks_count": len(tasks),
        "daily_total": daily_total,
        "tasks": tasks,
    }
    if planting_date_arg:
        response_data["planting_date"] = planting_date_arg.strip()
        response_data["reference_today"] = date.today().isoformat()

    return jsonify(response_data), 200


# ─── 3. POST /api/task-cost — Calculates Quantities & Costs for a Task ────────

@calendar_api.route("/task-cost", methods=["POST"])
def api_task_cost():
    """
    POST /api/task-cost
    Calculates required material quantities and itemized costs for a specific task.

    Request Body (JSON):
        {
            "crop": "Wheat" (or "crop_id": 1),
            "task": "First Top-Dressing of Nitrogen",
            "acres": 2.5,
            "custom_prices": { "urea_per_kg": 5.50 } (optional)
        }
    """
    if not request.is_json:
        return jsonify({"error": "Request body must be valid JSON with 'Content-Type: application/json'."}), 400

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON payload. Expected a JSON object."}), 400

    crop_arg = data.get("crop") or data.get("crop_name") or data.get("crop_id")
    if not crop_arg:
        return jsonify({"error": "Field 'crop' (or 'crop_id') is required."}), 400

    crop = _parse_crop_param(crop_arg)
    if not crop:
        avail = ", ".join(fc.FarmingCalendar().get_available_crop_names())
        return jsonify({"error": f"Crop '{crop_arg}' not found. Available crops: {avail}"}), 404

    task_arg = data.get("task") or data.get("task_name")
    if not task_arg or not str(task_arg).strip():
        return jsonify({"error": "Field 'task' (or 'task_name') is required."}), 400

    acres_arg = data.get("acres")
    if acres_arg is None:
        return jsonify({"error": "Field 'acres' is required."}), 400

    try:
        acres = float(acres_arg)
        if acres <= 0:
            return jsonify({"error": f"Field 'acres' must be greater than 0, got {acres}."}), 400
    except (TypeError, ValueError):
        return jsonify({"error": f"Field 'acres' must be a valid positive number, got {acres_arg!r}."}), 400

    custom_prices = data.get("custom_prices")
    if custom_prices is not None and not isinstance(custom_prices, dict):
        return jsonify({"error": "Field 'custom_prices' must be a JSON object mapping price keys to numbers."}), 400

    try:
        result = bc.calculate_task_cost(
            crop=crop,
            task=str(task_arg).strip(),
            acres=acres,
            custom_prices=custom_prices,
        )
        return jsonify(result), 200
    except bc.TaskNotFoundError as err:
        return jsonify({"error": str(err)}), 404
    except (bc.BudgetCalculationError, ValueError) as err:
        return jsonify({"error": str(err)}), 400


# ─── Additional Modular Endpoints (Crops, Month, Budget, Compare) ─────────────

@calendar_api.route("/crops", methods=["GET"])
def api_all_crops():
    """GET /api/crops — List crops, optionally filtered by ?season."""
    season = request.args.get("season")
    if season:
        crops = fc.get_crops_by_season(season)
    else:
        crops = fc.get_all_crops()
    return jsonify(crops), 200


@calendar_api.route("/crops/<int:crop_id>", methods=["GET"])
def api_crop_detail(crop_id: int):
    """GET /api/crops/<crop_id> — Single crop detail."""
    crop = fc.get_crop_by_id(crop_id)
    if not crop:
        return jsonify({"error": f"Crop with id {crop_id} not found."}), 404
    return jsonify(crop), 200


@calendar_api.route("/month/<int:month>", methods=["GET"])
def api_month(month: int):
    """GET /api/month/<1-12> — Crops active in a specific month."""
    if not 1 <= month <= 12:
        return jsonify({"error": "Month must be between 1 and 12."}), 400
    crops = fc.get_crops_for_month(month)
    return jsonify({"month": month, "crops": crops}), 200


@calendar_api.route("/budget", methods=["POST"])
def api_budget():
    """
    POST /api/budget
    Calculate total cultivation budget, material quantities, and revenue projection.
    Body: { "crop_id": 1, "acres": 2.5 }
    """
    if not request.is_json:
        return jsonify({"error": "Request body must be JSON."}), 400

    data = request.get_json(silent=True) or {}
    crop_arg = data.get("crop_id") or data.get("crop") or data.get("crop_name")
    acres_arg = data.get("acres")

    if crop_arg is None or acres_arg is None:
        return jsonify({"error": "'crop_id' (or 'crop') and 'acres' are required."}), 400

    crop = _parse_crop_param(crop_arg)
    if not crop:
        return jsonify({"error": f"Crop '{crop_arg}' not found."}), 404

    try:
        acres = float(acres_arg)
        if acres <= 0:
            return jsonify({"error": "'acres' must be greater than 0."}), 400
    except (TypeError, ValueError):
        return jsonify({"error": f"'acres' must be a number, got {acres_arg!r}."}), 400

    try:
        result = bc.calculate_budget(crop, acres)
        return jsonify(result), 200
    except ValueError as err:
        return jsonify({"error": str(err)}), 400


@calendar_api.route("/compare", methods=["POST"])
def api_compare():
    """
    POST /api/compare
    Compare crops in a season sorted by net profit.
    Body: { "season": "Kharif", "acres": 2.0 }
    """
    if not request.is_json:
        return jsonify({"error": "Request body must be JSON."}), 400

    data = request.get_json(silent=True) or {}
    season = data.get("season")
    acres_arg = data.get("acres")

    if not season or acres_arg is None:
        return jsonify({"error": "'season' and 'acres' are required."}), 400

    try:
        acres = float(acres_arg)
        if acres <= 0:
            return jsonify({"error": "'acres' must be greater than 0."}), 400
    except (TypeError, ValueError):
        return jsonify({"error": f"'acres' must be a number, got {acres_arg!r}."}), 400

    crops = fc.get_crops_by_season(season)
    if not crops:
        return jsonify([]), 200

    result = bc.compare_crops(crops, acres)
    return jsonify(result), 200


@calendar_api.route("/crop-plan", methods=["GET"])
def api_crop_plan():
    """
    GET /api/crop-plan?crop=Wheat&planting_date=2026-11-01
    Generate a proposed relative plan (if planting_date is omitted)
    or a dated calendar schedule (if planting_date is provided).
    """
    crop_arg = request.args.get("crop") or request.args.get("crop_id")
    if not crop_arg:
        return jsonify({"error": "Query parameter 'crop' is required."}), 400

    crop = _parse_crop_param(crop_arg)
    if not crop:
        return jsonify({"error": f"Crop '{crop_arg}' not found."}), 404

    planting_date = request.args.get("planting_date")
    acres_arg = request.args.get("acres")
    acres_val = 1.0
    if acres_arg is not None:
        try:
            acres_val = float(acres_arg)
            if acres_val <= 0:
                return jsonify({"error": f"Invalid 'acres' parameter: '{acres_arg}'. Must be greater than 0."}), 400
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid 'acres' parameter: '{acres_arg}'. Must be a positive number."}), 400

    try:
        plan = fc.generate_crop_plan(crop["name"], planting_date=planting_date, acres=acres_val)
        return jsonify(plan), 200
    except (fc.CropNotFoundError, fc.InvalidInputError) as err:
        return jsonify({"error": str(err)}), 400


# ─── Application Factory ──────────────────────────────────────────────────────

def create_app(config: Optional[Dict[str, Any]] = None) -> Flask:
    """
    Application factory for the Farming Calendar service.
    Creates and configures the Flask application, mounts the blueprint,
    and sets up error handlers.
    """
    app = Flask(__name__)
    if config:
        app.config.update(config)

    # Register the modular API blueprint
    app.register_blueprint(calendar_api)

    # Web UI Dashboard Route
    @app.route("/")
    def index():
        grid = fc.get_calendar_grid()
        seasons = fc.get_season_summary()
        current_season = fc.get_current_season()
        return render_template(
            "calendar.html",
            grid=grid,
            seasons=seasons,
            current_season=current_season,
        )

    # Centralized JSON error handlers for 400, 404, 500
    @app.errorhandler(400)
    def bad_request(err):
        desc = getattr(err, "description", "Bad Request")
        return jsonify({"error": str(desc)}), 400

    @app.errorhandler(404)
    def not_found(err):
        desc = getattr(err, "description", "Not Found")
        return jsonify({"error": str(desc)}), 404

    @app.errorhandler(500)
    def internal_error(err):
        return jsonify({"error": "Internal Server Error"}), 500

    return app


# ─── Default Application Instance ─────────────────────────────────────────────

app = create_app()


# ─── Run Server ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
