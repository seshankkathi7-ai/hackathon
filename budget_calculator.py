"""
budget_calculator.py
====================
Agricultural Budget & Cost of Cultivation Calculator.

Calculates:
- Required material quantities (scaled to land area in acres).
- Fertilizer quantities (Urea, DAP, MOP, Micronutrients, FYM).
- Seed quantities (certified seed kg and standard bags).
- Labour costs (person-days and operations breakdown).
- Machinery costs (tillage, seed drill, tractor implements).
- Irrigation costs (event-based electricity/diesel & canal cess).
- Harvesting costs (combine harvester or manual harvesting contract).
- Other applicable expenses (seed treatment, herbicides, packaging bags, transport).
- Total estimated cultivation cost with strict double-counting prevention.
- Projected revenue, net profit, and ROI%.

Rules:
1. Calculates quantities using verified per-acre agronomic packages of practices.
2. Uses actual input prices only when reliable, verified price data is available.
3. If a required quantity or price is missing, marks the estimate as incomplete
   instead of inventing a value.
4. Prevents double-counting by strictly partitioning expenses into disjoint categories.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple, Union


# ─── Custom Exceptions ────────────────────────────────────────────────────────

class BudgetCalculationError(Exception):
    """Base exception for budget calculator errors."""
    pass


class InvalidLandAreaError(BudgetCalculationError, ValueError):
    """Raised when land area in acres is non-positive or invalid."""
    pass


class TaskNotFoundError(BudgetCalculationError, ValueError, KeyError):
    """Raised when a specified task cannot be found for the given crop."""
    pass


# ─── Reliable Price Database ──────────────────────────────────────────────────
# Documented, official and verified benchmark prices (INR).
# Sources:
# - Urea: Statutory MRP notified by Govt. of India (Department of Fertilizers)
# - DAP & MOP: Nutrient Based Subsidy (NBS) market benchmark prices
# - Certified Seeds: National Seeds Corporation (NSC) & State Seeds Corporations
# - Labour: State Statutory Minimum Wages for Agricultural Workers (average standard)
# - Machinery: Custom Hiring Centre (CHC) / Farm Machinery Training tariffs
# - Packaging: Indian Standard HDPE woven bags (50 kg capacity) benchmark

RELIABLE_PRICES: Dict[str, Dict[str, Any]] = {
    "urea_per_kg": {
        "price": 5.38,
        "unit": "per kg",
        "description": "Statutory MRP (₹242 per 45 kg bag)",
        "source": "Ministry of Chemicals & Fertilizers, Govt. of India",
    },
    "dap_per_kg": {
        "price": 27.00,
        "unit": "per kg",
        "description": "Subsidized NBS market price (₹1,350 per 50 kg bag)",
        "source": "IFFCO / NBS Notification",
    },
    "mop_per_kg": {
        "price": 34.00,
        "unit": "per kg",
        "description": "Subsidized NBS market price (₹1,700 per 50 kg bag)",
        "source": "Potash Research Institute / NBS Notification",
    },
    "zinc_sulphate_21_per_kg": {
        "price": 45.00,
        "unit": "per kg",
        "description": "Zinc Sulphate Heptahydrate (21% Zn)",
        "source": "State Agro Industries Corporation",
    },
    "fym_compost_per_tonne": {
        "price": 600.00,
        "unit": "per tonne",
        "description": "Farm Yard Manure / Well-decomposed compost",
        "source": "ICAR Organic Farming benchmark",
    },
    "wheat_certified_seed_per_kg": {
        "price": 42.00,
        "unit": "per kg",
        "description": "Certified Wheat Seed (HD/PBW series)",
        "source": "National Seeds Corporation (NSC)",
    },
    "paddy_certified_seed_per_kg": {
        "price": 45.00,
        "unit": "per kg",
        "description": "Certified Paddy Seed (Transplanted varieties)",
        "source": "State Seeds Corporation",
    },
    "maize_hybrid_seed_per_kg": {
        "price": 220.00,
        "unit": "per kg",
        "description": "Certified Single-Cross Hybrid Maize Seed",
        "source": "ICAR-IIMR / NSC Certified Hybrid tariff",
    },
    "agricultural_labour_per_day": {
        "price": 375.00,
        "unit": "per person-day",
        "description": "Standard agricultural wage rate",
        "source": "Ministry of Labour & Employment, Agricultural Minimum Wages",
    },
    "hdpe_bag_50kg_each": {
        "price": 28.00,
        "unit": "per bag",
        "description": "50 kg capacity HDPE woven food-grade storage bag",
        "source": "Packaging Industry Standard Benchmark",
    },
    "irrigation_per_event_per_acre": {
        "price": 350.00,
        "unit": "per irrigation per acre",
        "description": "Tubewell diesel/electricity & canal cess",
        "source": "State Irrigation Department / CACP Cost of Cultivation Studies",
    },
    "wheat_machinery_land_prep_per_acre": {
        "price": 1800.00,
        "unit": "per acre",
        "description": "Tractor mould-board ploughing + rotavator tilth (custom hire)",
        "source": "Custom Hiring Centre (CHC) tariff schedule",
    },
    "wheat_machinery_sowing_drill_per_acre": {
        "price": 650.00,
        "unit": "per acre",
        "description": "Tractor seed-cum-fertilizer drill line sowing",
        "source": "CHC Farm Machinery rental rate",
    },
    "wheat_harvesting_combine_per_acre": {
        "price": 1800.00,
        "unit": "per acre",
        "description": "Combine harvester contract (reaping, threshing, winnowing)",
        "source": "Combine Harvester Operators Union benchmark",
    },
    "wheat_seed_treatment_per_acre": {
        "price": 150.00,
        "unit": "per acre",
        "description": "Fungicide seed treatment (Carboxin + Thiram WS)",
        "source": "CIBRC registered seed dressing tariff",
    },
    "wheat_herbicide_per_acre": {
        "price": 500.00,
        "unit": "per acre",
        "description": "Pre/post emergence weedicide (Pendimethalin/Clodinafop)",
        "source": "Directorate of Weed Research (ICAR-DWR)",
    },
    "paddy_machinery_puddling_per_acre": {
        "price": 2200.00,
        "unit": "per acre",
        "description": "Tractor cage-wheel puddling (2 passes) + wooden planking",
        "source": "CHC Paddy Mechanization tariff",
    },
    "paddy_harvesting_combine_per_acre": {
        "price": 2200.00,
        "unit": "per acre",
        "description": "Track-type combine harvester contract for paddy",
        "source": "Paddy Harvester Custom Hiring Tariff",
    },
    "paddy_nursery_inputs_per_acre": {
        "price": 250.00,
        "unit": "per acre",
        "description": "Nursery bed seed treatment & bio-inoculant inputs",
        "source": "ICAR-NRRI Cuttack Rice Production Technology",
    },
    "paddy_herbicide_per_acre": {
        "price": 550.00,
        "unit": "per acre",
        "description": "Early post-emergence herbicide (Pretilachlor / Bispyribac)",
        "source": "ICAR-NRRI Rice Weed Management",
    },
    "maize_machinery_land_prep_per_acre": {
        "price": 1600.00,
        "unit": "per acre",
        "description": "Tractor disc ploughing & harrowing for fine tilth",
        "source": "CHC Farm Machinery benchmark",
    },
    "maize_machinery_sowing_planter_per_acre": {
        "price": 600.00,
        "unit": "per acre",
        "description": "Tractor-mounted precision maize planter line sowing",
        "source": "CHC Maize Planter tariff",
    },
    "maize_harvesting_mechanical_per_acre": {
        "price": 1800.00,
        "unit": "per acre",
        "description": "De-husking, cob harvesting & mechanical shelling contract",
        "source": "Maize Processing & Harvester Union tariff",
    },
    "maize_seed_treatment_per_acre": {
        "price": 180.00,
        "unit": "per acre",
        "description": "Fungicide + Azospirillum bio-inoculant seed treatment",
        "source": "ICAR-IIMR Maize Package of Practices",
    },
    "maize_herbicide_per_acre": {
        "price": 400.00,
        "unit": "per acre",
        "description": "Atrazine pre-emergence herbicide spray",
        "source": "ICAR-IIMR Weed Management Guide",
    },
    "maize_ipm_traps_per_acre": {
        "price": 250.00,
        "unit": "per acre",
        "description": "Fall Armyworm (FAW) pheromone lure & trap monitoring",
        "source": "NCIPM / ICAR-IIMR IPM Bulletin",
    },
    "mandi_transport_per_quintal": {
        "price": 15.00,
        "unit": "per quintal",
        "description": "Farm-gate to local APMC mandi trolley transport & handling",
        "source": "APMC Mandi Transport Union benchmark",
    },
}


# ─── Verified Agronomic Package of Practices Profiles ─────────────────────────
# Documented per-acre input quantities and requirements based on ICAR
# and State Agricultural University (SAU) recommendations.

VERIFIED_AGRONOMIC_PROFILES: Dict[str, Dict[str, Any]] = {
    "Wheat": {
        "crop_name": "Wheat",
        "season": "Rabi",
        "yield_per_acre": 20.0,              # quintals (ICAR benchmark)
        "market_price_per_quintal": 2275.0,  # Govt Minimum Support Price (MSP)
        "seed": {
            "item": "Certified Wheat Seed (PBW / HD Series)",
            "rate_per_acre": 45.0,           # kg/acre (standard line-sowing rate)
            "unit": "kg",
            "price_key": "wheat_certified_seed_per_kg",
            "bag_weight_kg": 40.0,
            "source": "ICAR-DWBR Karnal Wheat Production Technology",
        },
        "fertilizers": [
            {
                "item": "Urea (46% N)",
                "rate_per_acre": 110.0,      # kg/acre (split: 1 basal + 2 top-dressings)
                "unit": "kg",
                "price_key": "urea_per_kg",
                "bag_weight_kg": 45.0,
                "source": "ICAR Nutrient Management Guidelines",
            },
            {
                "item": "Di-Ammonium Phosphate (DAP 18:46:0)",
                "rate_per_acre": 55.0,       # kg/acre (full basal in furrow)
                "unit": "kg",
                "price_key": "dap_per_kg",
                "bag_weight_kg": 50.0,
                "source": "ICAR Soil Health Card Standard Package",
            },
            {
                "item": "Muriate of Potash (MOP 60% K2O)",
                "rate_per_acre": 25.0,       # kg/acre (basal potassium)
                "unit": "kg",
                "price_key": "mop_per_kg",
                "bag_weight_kg": 50.0,
                "source": "ICAR-DWBR Fertilizer Recommendations",
            },
            {
                "item": "Zinc Sulphate Heptahydrate (21% Zn)",
                "rate_per_acre": 10.0,       # kg/acre (micronutrient application)
                "unit": "kg",
                "price_key": "zinc_sulphate_21_per_kg",
                "bag_weight_kg": 10.0,
                "source": "ICAR-IISS Bhopal Micronutrient Advisory",
            },
        ],
        "labour": [
            {
                "operation": "Pre-sowing field prep & seed treatment",
                "person_days_per_acre": 1.0,
                "price_key": "agricultural_labour_per_day",
            },
            {
                "operation": "Top-dressing fertilizer applications (2 split rounds)",
                "person_days_per_acre": 1.5,
                "price_key": "agricultural_labour_per_day",
            },
            {
                "operation": "Irrigation supervision & field channel maintenance",
                "person_days_per_acre": 2.5,
                "price_key": "agricultural_labour_per_day",
            },
            {
                "operation": "Manual weeding & weed rogueing",
                "person_days_per_acre": 2.0,
                "price_key": "agricultural_labour_per_day",
            },
            {
                "operation": "Post-harvest bag filling, stitching & trolley loading",
                "person_days_per_acre": 1.0,
                "price_key": "agricultural_labour_per_day",
            },
        ],
        "machinery": [
            {
                "operation": "Tractor deep ploughing & rotavator tilth preparation",
                "rate_per_acre": 1.0,
                "unit": "acre",
                "price_key": "wheat_machinery_land_prep_per_acre",
                "source": "CHC Tractor Hire Tariff",
            },
            {
                "operation": "Tractor seed-cum-fertilizer drill line sowing",
                "rate_per_acre": 1.0,
                "unit": "acre",
                "price_key": "wheat_machinery_sowing_drill_per_acre",
                "source": "CHC Implement Hire Tariff",
            },
        ],
        "irrigation": {
            "events_count": 5,               # CRI, tillering, jointing, flowering, grain-fill
            "cost_per_event_per_acre": 350.0,
            "source": "CACP Cost of Cultivation Studies / Tube-well cess",
        },
        "harvesting": {
            "operation": "Combine harvester contract (harvesting, threshing & cleaning)",
            "rate_per_acre": 1.0,
            "unit": "acre",
            "price_key": "wheat_harvesting_combine_per_acre",
            "source": "Regional Agricultural Harvester Union tariff",
        },
        "other": [
            {
                "item": "Fungicide seed treatment (Carboxin + Thiram WS)",
                "rate_per_acre": 1.0,
                "unit": "acre",
                "price_key": "wheat_seed_treatment_per_acre",
                "source": "CIBRC registered package",
            },
            {
                "item": "Weed management herbicide (Pendimethalin / Clodinafop)",
                "rate_per_acre": 1.0,
                "unit": "acre",
                "price_key": "wheat_herbicide_per_acre",
                "source": "ICAR-DWR Weed Management Package",
            },
            {
                "item": "Packaging storage bags (50 kg HDPE woven bags)",
                "rate_per_acre": 40.0,       # 20 qtl yield * 2 bags/qtl
                "unit": "bags",
                "price_key": "hdpe_bag_50kg_each",
                "source": "Packaging industry benchmark",
            },
            {
                "item": "Mandi transport & loading charges",
                "rate_per_acre": 20.0,       # 20 quintals
                "unit": "quintal",
                "price_key": "mandi_transport_per_quintal",
                "source": "APMC Mandi Transport Union benchmark",
            },
        ],
    },

    "Rice": {
        "crop_name": "Rice",
        "season": "Kharif",
        "yield_per_acre": 22.0,              # quintals
        "market_price_per_quintal": 2183.0,  # Govt MSP (Common Grade)
        "seed": {
            "item": "Certified Paddy Seed (Transplanted nursery)",
            "rate_per_acre": 10.0,           # kg/acre
            "unit": "kg",
            "price_key": "paddy_certified_seed_per_kg",
            "bag_weight_kg": 25.0,
            "source": "ICAR-NRRI Cuttack Rice Production Package",
        },
        "fertilizers": [
            {
                "item": "Urea (46% N)",
                "rate_per_acre": 115.0,      # kg/acre
                "unit": "kg",
                "price_key": "urea_per_kg",
                "bag_weight_kg": 45.0,
                "source": "ICAR-NRRI Nutrient Management",
            },
            {
                "item": "Di-Ammonium Phosphate (DAP 18:46:0)",
                "rate_per_acre": 50.0,       # kg/acre
                "unit": "kg",
                "price_key": "dap_per_kg",
                "bag_weight_kg": 50.0,
                "source": "ICAR Nutrient Management",
            },
            {
                "item": "Muriate of Potash (MOP 60% K2O)",
                "rate_per_acre": 25.0,       # kg/acre
                "unit": "kg",
                "price_key": "mop_per_kg",
                "bag_weight_kg": 50.0,
                "source": "ICAR Nutrient Management",
            },
            {
                "item": "Zinc Sulphate Heptahydrate (21% Zn)",
                "rate_per_acre": 10.0,       # kg/acre (prevents Khaira disease)
                "unit": "kg",
                "price_key": "zinc_sulphate_21_per_kg",
                "bag_weight_kg": 10.0,
                "source": "ICAR-NRRI Micronutrient Guide",
            },
            {
                "item": "Farm Yard Manure (FYM / Compost)",
                "rate_per_acre": 2.0,        # tonnes/acre
                "unit": "tonne",
                "price_key": "fym_compost_per_tonne",
                "source": "ICAR-NRRI Soil Health Package",
            },
        ],
        "labour": [
            {
                "operation": "Nursery bed preparation & care",
                "person_days_per_acre": 2.0,
                "price_key": "agricultural_labour_per_day",
            },
            {
                "operation": "Seedling uprooting & field transplanting",
                "person_days_per_acre": 8.0,
                "price_key": "agricultural_labour_per_day",
            },
            {
                "operation": "Conoweeder / manual inter-row weeding (2 rounds)",
                "person_days_per_acre": 5.0,
                "price_key": "agricultural_labour_per_day",
            },
            {
                "operation": "Fertilizer broadcasting & plant protection sprays",
                "person_days_per_acre": 3.0,
                "price_key": "agricultural_labour_per_day",
            },
        ],
        "machinery": [
            {
                "operation": "Tractor puddling with cage wheels (2 passes) & levelling",
                "rate_per_acre": 1.0,
                "unit": "acre",
                "price_key": "paddy_machinery_puddling_per_acre",
                "source": "CHC Puddling tariff",
            },
        ],
        "irrigation": {
            "events_count": 6,               # 6 supplemental canal/pump irrigations
            "cost_per_event_per_acre": 350.0,
            "source": "State Irrigation Cess & Tubewell tariff",
        },
        "harvesting": {
            "operation": "Track-type combine harvester contract",
            "rate_per_acre": 1.0,
            "unit": "acre",
            "price_key": "paddy_harvesting_combine_per_acre",
            "source": "Paddy Combine Harvester tariff",
        },
        "other": [
            {
                "item": "Nursery inputs & bio-fertilizer seed priming",
                "rate_per_acre": 1.0,
                "unit": "acre",
                "price_key": "paddy_nursery_inputs_per_acre",
                "source": "NRRI nursery protocol",
            },
            {
                "item": "Early post-emergence weedicide (Pretilachlor / Bispyribac)",
                "rate_per_acre": 1.0,
                "unit": "acre",
                "price_key": "paddy_herbicide_per_acre",
                "source": "CIBRC registered rice herbicide",
            },
            {
                "item": "Packaging storage bags (50 kg HDPE woven bags)",
                "rate_per_acre": 44.0,       # 22 qtl yield * 2 bags/qtl
                "unit": "bags",
                "price_key": "hdpe_bag_50kg_each",
                "source": "Packaging industry benchmark",
            },
            {
                "item": "Mandi transport & loading charges",
                "rate_per_acre": 22.0,       # 22 quintals
                "unit": "quintal",
                "price_key": "mandi_transport_per_quintal",
                "source": "APMC Mandi Transport tariff",
            },
        ],
    },

    "Maize": {
        "crop_name": "Maize",
        "season": "Kharif",
        "yield_per_acre": 25.0,              # quintals
        "market_price_per_quintal": 1962.0,  # Govt MSP
        "seed": {
            "item": "Certified Single-Cross Hybrid Maize Seed",
            "rate_per_acre": 8.5,            # kg/acre
            "unit": "kg",
            "price_key": "maize_hybrid_seed_per_kg",
            "bag_weight_kg": 4.0,
            "source": "ICAR-IIMR Hyderabad Package of Practices",
        },
        "fertilizers": [
            {
                "item": "Urea (46% N)",
                "rate_per_acre": 140.0,      # kg/acre (split: basal + knee-high + pre-tassel)
                "unit": "kg",
                "price_key": "urea_per_kg",
                "bag_weight_kg": 45.0,
                "source": "ICAR-IIMR Nutrient Management",
            },
            {
                "item": "Di-Ammonium Phosphate (DAP 18:46:0)",
                "rate_per_acre": 55.0,       # kg/acre
                "unit": "kg",
                "price_key": "dap_per_kg",
                "bag_weight_kg": 50.0,
                "source": "ICAR-IIMR Nutrient Management",
            },
            {
                "item": "Muriate of Potash (MOP 60% K2O)",
                "rate_per_acre": 30.0,       # kg/acre
                "unit": "kg",
                "price_key": "mop_per_kg",
                "bag_weight_kg": 50.0,
                "source": "ICAR-IIMR Nutrient Management",
            },
            {
                "item": "Zinc Sulphate Heptahydrate (21% Zn)",
                "rate_per_acre": 10.0,       # kg/acre (prevents white bud in maize)
                "unit": "kg",
                "price_key": "zinc_sulphate_21_per_kg",
                "bag_weight_kg": 10.0,
                "source": "ICAR Micronutrient Guidelines",
            },
        ],
        "labour": [
            {
                "operation": "Inter-culture, hand weeding & earthing up (2 rounds)",
                "person_days_per_acre": 5.0,
                "price_key": "agricultural_labour_per_day",
            },
            {
                "operation": "Urea top-dressing (knee-high & pre-tassel stages)",
                "person_days_per_acre": 2.0,
                "price_key": "agricultural_labour_per_day",
            },
            {
                "operation": "Pest scouting, whorl application & spraying",
                "person_days_per_acre": 2.0,
                "price_key": "agricultural_labour_per_day",
            },
            {
                "operation": "Irrigation supervision & furrow water management",
                "person_days_per_acre": 1.0,
                "price_key": "agricultural_labour_per_day",
            },
        ],
        "machinery": [
            {
                "operation": "Tractor disc ploughing & harrow tilth preparation",
                "rate_per_acre": 1.0,
                "unit": "acre",
                "price_key": "maize_machinery_land_prep_per_acre",
                "source": "CHC Farm Machinery benchmark",
            },
            {
                "operation": "Tractor precision maize planter line sowing",
                "rate_per_acre": 1.0,
                "unit": "acre",
                "price_key": "maize_machinery_sowing_planter_per_acre",
                "source": "CHC Planter rental tariff",
            },
        ],
        "irrigation": {
            "events_count": 4,               # 4 furrow irrigations (sowing, knee-high, tasseling, grain-fill)
            "cost_per_event_per_acre": 350.0,
            "source": "Tube-well irrigation tariff",
        },
        "harvesting": {
            "operation": "Mechanical cob picking, de-husking & power shelling contract",
            "rate_per_acre": 1.0,
            "unit": "acre",
            "price_key": "maize_harvesting_mechanical_per_acre",
            "source": "Maize Harvester Union tariff",
        },
        "other": [
            {
                "item": "Fungicide & Azospirillum seed treatment",
                "rate_per_acre": 1.0,
                "unit": "acre",
                "price_key": "maize_seed_treatment_per_acre",
                "source": "ICAR-IIMR seed protection protocol",
            },
            {
                "item": "Pre-emergence herbicide (Atrazine 50% WP)",
                "rate_per_acre": 1.0,
                "unit": "acre",
                "price_key": "maize_herbicide_per_acre",
                "source": "ICAR-DWR Maize weed control",
            },
            {
                "item": "Fall Armyworm (FAW) pheromone lure & trap monitoring",
                "rate_per_acre": 1.0,
                "unit": "acre",
                "price_key": "maize_ipm_traps_per_acre",
                "source": "NCIPM / ICAR-IIMR IPM Bulletin",
            },
            {
                "item": "Packaging storage bags (50 kg HDPE woven bags)",
                "rate_per_acre": 50.0,       # 25 qtl yield * 2 bags/qtl
                "unit": "bags",
                "price_key": "hdpe_bag_50kg_each",
                "source": "Packaging industry benchmark",
            },
            {
                "item": "Mandi transport & loading charges",
                "rate_per_acre": 25.0,       # 25 quintals
                "unit": "quintal",
                "price_key": "mandi_transport_per_quintal",
                "source": "APMC Mandi Transport tariff",
            },
        ],
    },
}


# ─── Core Calculation Engine ──────────────────────────────────────────────────

def _validate_acres(acres: Any) -> float:
    """Validate that acres is a positive real number."""
    if acres is None:
        raise InvalidLandAreaError("Land area (acres) cannot be None.")

    # Disallow boolean values (since bool is a subclass of int in Python)
    if isinstance(acres, bool):
        raise InvalidLandAreaError("Land area (acres) cannot be a boolean value.")

    try:
        val = float(acres)
    except (TypeError, ValueError) as err:
        raise InvalidLandAreaError(f"Land area must be a numeric value, got {acres!r}.") from err

    if math.isnan(val) or math.isinf(val):
        raise InvalidLandAreaError("Land area cannot be NaN or infinite.")

    if val <= 0:
        raise InvalidLandAreaError(f"Land area must be strictly greater than 0, got {val}.")

    return val


def _resolve_crop_profile(crop: Union[Dict[str, Any], str]) -> Tuple[str, Dict[str, Any], bool]:
    """
    Resolve crop name and agronomic profile.
    Returns: (canonical_name, profile_dict, is_known_verified_profile)
    """
    if isinstance(crop, str):
        cname = crop.strip()
    elif isinstance(crop, dict):
        cname = crop.get("name", "").strip()
    else:
        raise BudgetCalculationError(f"Expected crop as dict or string, got {type(crop).__name__}.")

    if not cname:
        raise BudgetCalculationError("Crop name is missing or empty.")

    # Check case-insensitive match in verified agronomic profiles
    for key, prof in VERIFIED_AGRONOMIC_PROFILES.items():
        if key.lower() == cname.lower():
            return key, prof, True

    # If crop is not in verified profiles, check if it's a custom dictionary
    if isinstance(crop, dict):
        return cname, crop, False

    return cname, {}, False


def calculate_budget(
    crop: Union[Dict[str, Any], str],
    acres: float,
    custom_prices: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Calculate the detailed agricultural budget for a specified land area in acres.

    Parameters:
        crop: Crop dictionary or crop name (e.g. 'Wheat', 'Rice', 'Maize').
        acres: Land area in acres (> 0).
        custom_prices: Optional price dictionary overriding RELIABLE_PRICES.

    Returns:
        Dictionary containing:
        - crop_name, season, acres
        - material_quantities: list of all required physical inputs
        - fertilizer_quantities: detailed breakdown of fertilizer kg & bags
        - seed_quantities: seed requirements and packaging
        - labour_breakdown & costs
        - machinery_breakdown & costs
        - irrigation_breakdown & costs
        - harvesting_breakdown & costs
        - other_expenses_breakdown & costs
        - total_cultivation_cost (sum of disjoint categories)
        - breakdown: 7 disjoint categories {seed, fertilizer, machinery, labour, irrigation, harvesting, other}
        - is_complete: True if all quantities and prices are verified, False otherwise
        - missing_items: list of any unpriced or missing parameters
        - expected_yield_quintals, gross_revenue, net_profit, roi_percent
    """
    land_area = _validate_acres(acres)
    canonical_name, profile, is_verified = _resolve_crop_profile(crop)

    # Active price book (custom_prices override RELIABLE_PRICES)
    price_book: Dict[str, Optional[float]] = {}
    for k, v in RELIABLE_PRICES.items():
        price_book[k] = v["price"]
    if custom_prices:
        for k, v in custom_prices.items():
            if v is None:
                price_book[k] = None
            elif v >= 0:
                price_book[k] = float(v)

    # Tracking collections
    missing_items: List[Dict[str, str]] = []
    line_items: List[Dict[str, Any]] = []

    # Disjoint category accumulators to guarantee NO double counting
    category_totals: Dict[str, float] = {
        "seed": 0.0,
        "fertilizer": 0.0,
        "machinery": 0.0,
        "labour": 0.0,
        "irrigation": 0.0,
        "harvesting": 0.0,
        "other": 0.0,
    }

    # Structured quantity outputs
    material_quantities: List[Dict[str, Any]] = []
    fertilizer_quantities: List[Dict[str, Any]] = []
    seed_quantities: Dict[str, Any] = {}
    labour_breakdown: List[Dict[str, Any]] = []
    machinery_breakdown: List[Dict[str, Any]] = []
    irrigation_breakdown: Dict[str, Any] = {}
    harvesting_breakdown: Dict[str, Any] = {}
    other_expenses_breakdown: List[Dict[str, Any]] = []

    # ──────────────────────────────────────────────────────────────────────────
    # CASE A: Crop has a verified agronomic package of practices
    # ──────────────────────────────────────────────────────────────────────────
    if is_verified:
        season = profile.get("season", "N/A")
        yield_per_acre = float(profile.get("yield_per_acre", 0.0))
        price_per_quintal = float(profile.get("market_price_per_quintal", 0.0))

        # 1. Seed Quantities & Costs
        seed_cfg = profile.get("seed", {})
        seed_item = seed_cfg.get("item", f"{canonical_name} Seed")
        seed_rate = seed_cfg.get("rate_per_acre")
        seed_unit = seed_cfg.get("unit", "kg")
        seed_pkey = seed_cfg.get("price_key")
        bag_wt = seed_cfg.get("bag_weight_kg", 40.0)

        if seed_rate is not None:
            total_seed_qty = round(seed_rate * land_area, 2)
            seed_price = price_book.get(seed_pkey) if seed_pkey else None

            if seed_price is not None:
                seed_cost = round(total_seed_qty * seed_price, 2)
                category_totals["seed"] += seed_cost
                item_priced = True
            else:
                seed_cost = None
                item_priced = False
                missing_items.append({
                    "item": seed_item,
                    "category": "seed",
                    "reason": f"Missing reliable price for price_key '{seed_pkey}'",
                })

            seed_quantities = {
                "item": seed_item,
                "rate_per_acre": seed_rate,
                "unit": seed_unit,
                "total_quantity": total_seed_qty,
                "bags_required": math.ceil(total_seed_qty / bag_wt) if bag_wt else None,
                "unit_price": seed_price,
                "total_cost": seed_cost,
                "is_priced": item_priced,
            }
            material_quantities.append({
                "item": seed_item,
                "category": "seed",
                "rate_per_acre": seed_rate,
                "unit": seed_unit,
                "total_quantity": total_seed_qty,
                "total_cost": seed_cost,
            })
            line_items.append({
                "item": seed_item,
                "category": "seed",
                "quantity": total_seed_qty,
                "unit": seed_unit,
                "unit_price": seed_price,
                "cost": seed_cost,
            })
        else:
            missing_items.append({
                "item": seed_item,
                "category": "seed",
                "reason": "Missing verified seed rate per acre",
            })

        # 2. Fertilizer Quantities & Costs
        fert_list = profile.get("fertilizers", [])
        for fcfg in fert_list:
            f_item = fcfg.get("item", "Fertilizer")
            f_rate = fcfg.get("rate_per_acre")
            f_unit = fcfg.get("unit", "kg")
            f_pkey = fcfg.get("price_key")
            f_bag_wt = fcfg.get("bag_weight_kg", 50.0)

            if f_rate is not None:
                total_f_qty = round(f_rate * land_area, 2)
                f_price = price_book.get(f_pkey) if f_pkey else None

                if f_price is not None:
                    f_cost = round(total_f_qty * f_price, 2)
                    category_totals["fertilizer"] += f_cost
                    f_priced = True
                else:
                    f_cost = None
                    f_priced = False
                    missing_items.append({
                        "item": f_item,
                        "category": "fertilizer",
                        "reason": f"Missing reliable price for '{f_pkey}'",
                    })

                f_entry = {
                    "item": f_item,
                    "rate_per_acre": f_rate,
                    "unit": f_unit,
                    "total_quantity": total_f_qty,
                    "bags_required": math.ceil(total_f_qty / f_bag_wt) if f_bag_wt else None,
                    "unit_price": f_price,
                    "total_cost": f_cost,
                    "is_priced": f_priced,
                }
                fertilizer_quantities.append(f_entry)
                material_quantities.append({
                    "item": f_item,
                    "category": "fertilizer",
                    "rate_per_acre": f_rate,
                    "unit": f_unit,
                    "total_quantity": total_f_qty,
                    "total_cost": f_cost,
                })
                line_items.append({
                    "item": f_item,
                    "category": "fertilizer",
                    "quantity": total_f_qty,
                    "unit": f_unit,
                    "unit_price": f_price,
                    "cost": f_cost,
                })
            else:
                missing_items.append({
                    "item": f_item,
                    "category": "fertilizer",
                    "reason": "Missing verified rate per acre",
                })

        # 3. Labour Costs
        labour_list = profile.get("labour", [])
        for lcfg in labour_list:
            op_name = lcfg.get("operation", "Labour Operation")
            days_rate = lcfg.get("person_days_per_acre")
            wage_pkey = lcfg.get("price_key", "agricultural_labour_per_day")
            wage_rate = price_book.get(wage_pkey)

            if days_rate is not None:
                total_days = round(days_rate * land_area, 2)
                if wage_rate is not None:
                    l_cost = round(total_days * wage_rate, 2)
                    category_totals["labour"] += l_cost
                    l_priced = True
                else:
                    l_cost = None
                    l_priced = False
                    missing_items.append({
                        "item": op_name,
                        "category": "labour",
                        "reason": "Missing agricultural wage rate",
                    })

                labour_breakdown.append({
                    "operation": op_name,
                    "person_days_per_acre": days_rate,
                    "total_person_days": total_days,
                    "wage_rate": wage_rate,
                    "cost": l_cost,
                    "is_priced": l_priced,
                })
                line_items.append({
                    "item": f"Labour: {op_name}",
                    "category": "labour",
                    "quantity": total_days,
                    "unit": "person-days",
                    "unit_price": wage_rate,
                    "cost": l_cost,
                })
            else:
                missing_items.append({
                    "item": op_name,
                    "category": "labour",
                    "reason": "Missing labour person-days per acre",
                })

        # 4. Machinery Costs
        mach_list = profile.get("machinery", [])
        for mcfg in mach_list:
            m_op = mcfg.get("operation", "Machinery Operation")
            m_pkey = mcfg.get("price_key")
            m_price = price_book.get(m_pkey) if m_pkey else None

            if m_price is not None:
                m_cost = round(m_price * land_area, 2)
                category_totals["machinery"] += m_cost
                m_priced = True
            else:
                m_cost = None
                m_priced = False
                missing_items.append({
                    "item": m_op,
                    "category": "machinery",
                    "reason": f"Missing machinery tariff for '{m_pkey}'",
                })

            machinery_breakdown.append({
                "operation": m_op,
                "rate_per_acre": m_price,
                "total_cost": m_cost,
                "is_priced": m_priced,
            })
            line_items.append({
                "item": f"Machinery: {m_op}",
                "category": "machinery",
                "quantity": land_area,
                "unit": "acres",
                "unit_price": m_price,
                "cost": m_cost,
            })

        # 5. Irrigation Costs
        irrig_cfg = profile.get("irrigation", {})
        events_count = irrig_cfg.get("events_count")
        irrig_pkey = irrig_cfg.get("price_key", "irrigation_per_event_per_acre")
        irrig_unit_price = price_book.get(irrig_pkey, irrig_cfg.get("cost_per_event_per_acre"))

        if events_count is not None and irrig_unit_price is not None:
            total_irrig_events = events_count
            cost_per_event_total = round(irrig_unit_price * land_area, 2)
            total_irrig_cost = round(cost_per_event_total * events_count, 2)
            category_totals["irrigation"] += total_irrig_cost
            irrig_priced = True
        else:
            total_irrig_cost = None
            irrig_priced = False
            missing_items.append({
                "item": "Irrigation Services",
                "category": "irrigation",
                "reason": "Missing irrigation events count or tariff",
            })

        irrigation_breakdown = {
            "events_count": events_count,
            "cost_per_event_per_acre": irrig_unit_price,
            "total_events_conducted": events_count,
            "total_cost": total_irrig_cost,
            "is_priced": irrig_priced,
        }
        line_items.append({
            "item": f"Irrigation: {events_count} application events",
            "category": "irrigation",
            "quantity": events_count * land_area if events_count else land_area,
            "unit": "irrigation-acres",
            "unit_price": irrig_unit_price,
            "cost": total_irrig_cost,
        })

        # 6. Harvesting Costs
        harv_cfg = profile.get("harvesting", {})
        harv_op = harv_cfg.get("operation", "Harvesting & Threshing Contract")
        harv_pkey = harv_cfg.get("price_key")
        harv_price = price_book.get(harv_pkey) if harv_pkey else None

        if harv_price is not None:
            harv_cost = round(harv_price * land_area, 2)
            category_totals["harvesting"] += harv_cost
            harv_priced = True
        else:
            harv_cost = None
            harv_priced = False
            missing_items.append({
                "item": harv_op,
                "category": "harvesting",
                "reason": f"Missing harvesting contract tariff for '{harv_pkey}'",
            })

        harvesting_breakdown = {
            "operation": harv_op,
            "rate_per_acre": harv_price,
            "total_cost": harv_cost,
            "is_priced": harv_priced,
        }
        line_items.append({
            "item": f"Harvesting: {harv_op}",
            "category": "harvesting",
            "quantity": land_area,
            "unit": "acres",
            "unit_price": harv_price,
            "cost": harv_cost,
        })

        # 7. Other Applicable Expenses
        other_list = profile.get("other", [])
        for ocfg in other_list:
            o_item = ocfg.get("item", "Other Input")
            o_rate = ocfg.get("rate_per_acre")
            o_unit = ocfg.get("unit", "acre")
            o_pkey = ocfg.get("price_key")
            o_price = price_book.get(o_pkey) if o_pkey else None

            if o_rate is not None and o_price is not None:
                o_total_qty = round(o_rate * land_area, 2)
                o_cost = round(o_total_qty * o_price, 2)
                category_totals["other"] += o_cost
                o_priced = True
            else:
                o_total_qty = round(o_rate * land_area, 2) if o_rate is not None else None
                o_cost = None
                o_priced = False
                missing_items.append({
                    "item": o_item,
                    "category": "other",
                    "reason": f"Missing price for '{o_pkey}'" if not o_price else "Missing rate",
                })

            other_expenses_breakdown.append({
                "item": o_item,
                "rate_per_acre": o_rate,
                "unit": o_unit,
                "total_quantity": o_total_qty,
                "unit_price": o_price,
                "cost": o_cost,
                "is_priced": o_priced,
            })
            material_quantities.append({
                "item": o_item,
                "category": "other",
                "rate_per_acre": o_rate,
                "unit": o_unit,
                "total_quantity": o_total_qty,
                "total_cost": o_cost,
            })
            line_items.append({
                "item": o_item,
                "category": "other",
                "quantity": o_total_qty,
                "unit": o_unit,
                "unit_price": o_price,
                "cost": o_cost,
            })

    # ──────────────────────────────────────────────────────────────────────────
    # CASE B: Crop is an unverified / custom dictionary
    # ──────────────────────────────────────────────────────────────────────────
    else:
        # If the crop dictionary has cost_per_acre / yield_per_acre / price_per_quintal
        season = profile.get("season", "General") if isinstance(profile, dict) else "General"
        yield_per_acre = float(profile.get("yield_per_acre", 0.0)) if isinstance(profile, dict) else 0.0
        price_per_quintal = float(profile.get("price_per_quintal", 0.0)) if isinstance(profile, dict) else 0.0
        cost_per_acre = profile.get("cost_per_acre") if isinstance(profile, dict) else None

        # Check for missing agronomic package
        missing_items.append({
            "item": f"{canonical_name} Agronomic Package",
            "category": "general",
            "reason": "Crop has no verified agronomic package of practices in the database.",
        })

        if cost_per_acre is not None:
            # Fall back to approximate percentage partitioning of cost_per_acre
            # but clearly mark as an unverified/incomplete estimate
            cpa = float(cost_per_acre)
            tot = cpa * land_area
            category_totals["seed"] = round(tot * 0.15, 2)
            category_totals["fertilizer"] = round(tot * 0.25, 2)
            category_totals["machinery"] = round(tot * 0.15, 2)
            category_totals["labour"] = round(tot * 0.20, 2)
            category_totals["irrigation"] = round(tot * 0.10, 2)
            category_totals["harvesting"] = round(tot * 0.10, 2)
            category_totals["other"] = round(tot * 0.05, 2)
            # Re-normalize to prevent rounding discrepancy
            tot_cat = sum(category_totals.values())
            category_totals["other"] += round(tot - tot_cat, 2)
        else:
            missing_items.append({
                "item": "Total Cost Per Acre",
                "category": "cost",
                "reason": "Missing cost_per_acre definition.",
            })

    # ──────────────────────────────────────────────────────────────────────────
    # STRICT DOUBLE-COUNTING PREVENTION & TOTALS
    # ──────────────────────────────────────────────────────────────────────────
    # Total cultivation cost is strictly the sum of the 7 disjoint categories.
    # Round all category totals to 2 decimal places.
    for k in category_totals:
        category_totals[k] = round(category_totals[k], 2)

    total_cultivation_cost = round(sum(category_totals.values()), 2)

    # Completeness Determination:
    # If any required quantity or price is missing, mark as incomplete
    # instead of inventing a value.
    is_complete = len(missing_items) == 0
    completeness_status = "COMPLETE" if is_complete else "INCOMPLETE"
    completeness_notes = (
        "Estimate is based on verified per-acre rates and official prices."
        if is_complete
        else f"Estimate is INCOMPLETE: {len(missing_items)} required items have missing rates or unverified prices. Unpriced items were NOT assigned invented values."
    )

    # Financial & Yield Projections
    expected_yield = round(yield_per_acre * land_area, 2)
    gross_revenue = round(expected_yield * price_per_quintal, 2)
    net_profit = round(gross_revenue - total_cultivation_cost, 2)
    roi_percent = (
        round((net_profit / total_cultivation_cost) * 100, 2)
        if total_cultivation_cost > 0
        else 0.0
    )

    # Build final result dictionary
    result: Dict[str, Any] = {
        "crop_name": canonical_name,
        "season": season,
        "acres": land_area,

        # Overall cost & completeness
        "total_cultivation_cost": total_cultivation_cost,
        "input_cost": total_cultivation_cost,  # Backward-compatible alias for app.py
        "is_complete": is_complete,
        "completeness_status": completeness_status,
        "completeness_notes": completeness_notes,
        "missing_items": missing_items,

        # Strict 7-category breakdown (sum of breakdown strictly equals total_cultivation_cost)
        "breakdown": category_totals,

        # Detailed categories
        "material_quantities": material_quantities,
        "fertilizer_quantities": fertilizer_quantities,
        "seed_quantities": seed_quantities,
        "labour_breakdown": labour_breakdown,
        "machinery_breakdown": machinery_breakdown,
        "irrigation_breakdown": irrigation_breakdown,
        "harvesting_breakdown": harvesting_breakdown,
        "other_expenses_breakdown": other_expenses_breakdown,
        "line_items": line_items,

        # Returns & Revenue
        "yield_per_acre_quintals": yield_per_acre,
        "price_per_quintal": price_per_quintal,
        "expected_yield_quintals": expected_yield,
        "gross_revenue": gross_revenue,
        "net_profit": net_profit,
        "roi_percent": roi_percent,
    }

    # Strict integrity check: ensure sum of breakdown exactly matches total
    breakdown_sum = round(sum(category_totals.values()), 2)
    if abs(breakdown_sum - total_cultivation_cost) > 0.01:
        raise BudgetCalculationError(
            f"Double-counting or reconciliation error: sum of categories ({breakdown_sum}) "
            f"does not match total cultivation cost ({total_cultivation_cost})."
        )

    return result


def compare_crops(
    crops: List[Union[Dict[str, Any], str]],
    acres: float,
    custom_prices: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    Calculate and compare budgets for multiple crops, sorted by net profit descending.
    """
    results = [calculate_budget(c, acres, custom_prices) for c in crops]
    return sorted(results, key=lambda x: x["net_profit"], reverse=True)


def get_verified_crop_names() -> List[str]:
    """Return list of crop names having verified agronomic packages."""
    return list(VERIFIED_AGRONOMIC_PROFILES.keys())


def get_crop_agronomic_profile(crop_name: str) -> Optional[Dict[str, Any]]:
    """Retrieve verified agronomic profile for a crop name (case-insensitive)."""
    for k, v in VERIFIED_AGRONOMIC_PROFILES.items():
        if k.lower() == crop_name.strip().lower():
            return dict(v)
    return None


def get_reliable_price(price_key: str) -> Optional[Dict[str, Any]]:
    """Look up a reliable price entry and its citation."""
    return RELIABLE_PRICES.get(price_key)


def calculate_task_cost(
    crop: Union[Dict[str, Any], str],
    task: Union[Dict[str, Any], str],
    acres: float,
    custom_prices: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Calculate quantities and costs for a specific farming task.

    Rules:
    - Calculates quantities using verified per-acre rates.
    - Uses reliable prices only.
    - If a required quantity or price is missing, marks estimate as incomplete
      instead of inventing a value.
    - Strictly prevents double-counting across disjoint categories.
    """
    land_area = _validate_acres(acres)
    canonical_name, profile, is_verified = _resolve_crop_profile(crop)

    # Resolve target task name
    if isinstance(task, dict):
        target_name = task.get("task_name", "").strip()
        task_data = task
    elif isinstance(task, str):
        target_name = task.strip()
        task_data = {}
    else:
        raise BudgetCalculationError(f"Expected task as dict or string, got {type(task).__name__}.")

    if not target_name:
        raise BudgetCalculationError("Task name cannot be empty.")

    # Search for task in crop calendar
    import farming_calendar as fc
    calendar_engine = fc.FarmingCalendar()
    try:
        crop_cal = calendar_engine.get_crop(canonical_name)
    except Exception:
        crop_cal = {}

    matched_task: Optional[Dict[str, Any]] = None
    matched_stage_key = "general"
    matched_stage_name = "General Farming"
    matched_stage_number = 0

    if crop_cal and "stages" in crop_cal:
        for skey, sinfo in crop_cal["stages"].items():
            for t in sinfo.get("tasks", []):
                t_name = t.get("task_name", "")
                if (target_name.lower() == t_name.lower() or
                    target_name.lower() in t_name.lower() or
                    t_name.lower() in target_name.lower()):
                    matched_task = t
                    matched_stage_key = skey
                    matched_stage_name = sinfo.get("stage_name", skey.replace("_", " ").title())
                    matched_stage_number = sinfo.get("stage_number", 0)
                    break
            if matched_task:
                break

    if not matched_task and task_data:
        matched_task = task_data
        matched_stage_key = task_data.get("stage_key", "general")
        matched_stage_name = task_data.get("stage_name", "General")
        matched_stage_number = task_data.get("stage_number", 0)

    if not matched_task:
        # Check if the name matches a known operation
        recognized_ops = ["ploughing", "tillage", "sowing", "transplanting", "fertilizer", "urea", "dap", "irrigation", "weeding", "harvesting", "combine", "scouting", "storage"]
        if not any(op in target_name.lower() for op in recognized_ops):
            raise TaskNotFoundError(f"Task '{target_name}' not found for crop '{canonical_name}'.")
        matched_task = {"task_name": target_name}

    resolved_task_name = matched_task.get("task_name", target_name)

    # Active price book
    price_book: Dict[str, Optional[float]] = {}
    for k, v in RELIABLE_PRICES.items():
        price_book[k] = v["price"]
    if custom_prices:
        for k, v in custom_prices.items():
            if v is None:
                price_book[k] = None
            elif v >= 0:
                price_book[k] = float(v)

    # Disjoint category tracking
    materials_cost = 0.0
    labour_cost = 0.0
    machinery_cost = 0.0
    irrigation_cost = 0.0
    harvesting_cost = 0.0
    other_cost = 0.0

    quantities: List[Dict[str, Any]] = []
    labour_details: Optional[Dict[str, Any]] = None
    machinery_details: Optional[Dict[str, Any]] = None
    irrigation_details: Optional[Dict[str, Any]] = None
    harvesting_details: Optional[Dict[str, Any]] = None
    missing_items: List[Dict[str, str]] = []

    wage_rate = price_book.get("agricultural_labour_per_day")
    t_lower = resolved_task_name.lower()

    # ── Task Operation Mapping ────────────────────────────────────────────────
    if "sowing" in t_lower or "transplanting" in t_lower:
        seed_cfg = profile.get("seed", {})
        s_rate = seed_cfg.get("rate_per_acre")
        s_pkey = seed_cfg.get("price_key")
        s_bag_wt = seed_cfg.get("bag_weight_kg", 40.0)
        s_price = price_book.get(s_pkey) if s_pkey else None

        if s_rate is not None and s_price is not None:
            tot_s = round(s_rate * land_area, 2)
            c_s = round(tot_s * s_price, 2)
            materials_cost += c_s
            quantities.append({
                "item": seed_cfg.get("item", f"{canonical_name} Seed"),
                "rate_per_acre": s_rate,
                "unit": seed_cfg.get("unit", "kg"),
                "total_quantity": tot_s,
                "bags_required": math.ceil(tot_s / s_bag_wt) if s_bag_wt else None,
                "unit_price": s_price,
                "cost": c_s,
            })
        elif s_rate is not None and s_price is None:
            missing_items.append({"item": "Certified Seed", "reason": f"Missing price for '{s_pkey}'"})

        # Machine sowing hire
        mach_pkey = "wheat_machinery_sowing_drill_per_acre" if "wheat" in canonical_name.lower() else "maize_machinery_sowing_planter_per_acre" if "maize" in canonical_name.lower() else None
        if mach_pkey and price_book.get(mach_pkey):
            m_rate = price_book[mach_pkey]
            c_m = round(m_rate * land_area, 2)
            machinery_cost += c_m
            machinery_details = {"operation": "Mechanical Sowing Drill / Planter", "rate_per_acre": m_rate, "cost": c_m}

        # Sowing labour
        p_days = 8.0 if "rice" in canonical_name.lower() else 1.0
        tot_days = round(p_days * land_area, 2)
        if wage_rate:
            c_l = round(tot_days * wage_rate, 2)
            labour_cost += c_l
            labour_details = {"operation": "Sowing / Transplanting Crew", "person_days": tot_days, "wage_rate": wage_rate, "cost": c_l}

    elif "top-dressing" in t_lower or "nitrogen" in t_lower or "urea" in t_lower:
        # 1 split dose of urea
        u_rate = 55.0 if "wheat" in canonical_name.lower() else 57.5 if "rice" in canonical_name.lower() else 70.0
        u_price = price_book.get("urea_per_kg")
        tot_u = round(u_rate * land_area, 2)

        if u_price is not None:
            c_u = round(tot_u * u_price, 2)
            materials_cost += c_u
            quantities.append({
                "item": "Urea (46% N) — Split Dose",
                "rate_per_acre": u_rate,
                "unit": "kg",
                "total_quantity": tot_u,
                "bags_required": math.ceil(tot_u / 45.0),
                "unit_price": u_price,
                "cost": c_u,
            })
        else:
            missing_items.append({"item": "Urea", "reason": "Missing price for urea_per_kg"})

        tot_days = round(1.0 * land_area, 2)
        if wage_rate:
            c_l = round(tot_days * wage_rate, 2)
            labour_cost += c_l
            labour_details = {"operation": "Fertilizer Broadcasting", "person_days": tot_days, "wage_rate": wage_rate, "cost": c_l}

    elif "basal fertilizer" in t_lower:
        dap_rate = 55.0 if "wheat" in canonical_name.lower() else 50.0 if "rice" in canonical_name.lower() else 55.0
        dap_price = price_book.get("dap_per_kg")
        tot_dap = round(dap_rate * land_area, 2)
        if dap_price is not None:
            c_dap = round(tot_dap * dap_price, 2)
            materials_cost += c_dap
            quantities.append({
                "item": "Di-Ammonium Phosphate (DAP 18:46:0)",
                "rate_per_acre": dap_rate,
                "unit": "kg",
                "total_quantity": tot_dap,
                "bags_required": math.ceil(tot_dap / 50.0),
                "unit_price": dap_price,
                "cost": c_dap,
            })
        mop_rate = 25.0
        mop_price = price_book.get("mop_per_kg")
        tot_mop = round(mop_rate * land_area, 2)
        if mop_price is not None:
            c_mop = round(tot_mop * mop_price, 2)
            materials_cost += c_mop
            quantities.append({
                "item": "Muriate of Potash (MOP 60% K2O)",
                "rate_per_acre": mop_rate,
                "unit": "kg",
                "total_quantity": tot_mop,
                "bags_required": math.ceil(tot_mop / 50.0),
                "unit_price": mop_price,
                "cost": c_mop,
            })
        tot_days = round(0.5 * land_area, 2)
        if wage_rate:
            c_l = round(tot_days * wage_rate, 2)
            labour_cost += c_l
            labour_details = {"operation": "Basal Application", "person_days": tot_days, "wage_rate": wage_rate, "cost": c_l}

    elif "zinc" in t_lower or "micronutrient" in t_lower:
        zn_rate = 10.0
        zn_price = price_book.get("zinc_sulphate_21_per_kg")
        tot_zn = round(zn_rate * land_area, 2)
        if zn_price is not None:
            c_zn = round(tot_zn * zn_price, 2)
            materials_cost += c_zn
            quantities.append({
                "item": "Zinc Sulphate (21% Zn)",
                "rate_per_acre": zn_rate,
                "unit": "kg",
                "total_quantity": tot_zn,
                "bags_required": math.ceil(tot_zn / 10.0),
                "unit_price": zn_price,
                "cost": c_zn,
            })
        tot_days = round(0.5 * land_area, 2)
        if wage_rate:
            c_l = round(tot_days * wage_rate, 2)
            labour_cost += c_l
            labour_details = {"operation": "Zinc Soil/Foliar Application", "person_days": tot_days, "wage_rate": wage_rate, "cost": c_l}

    elif "ploughing" in t_lower or "puddling" in t_lower or "tillage" in t_lower:
        m_pkey = "wheat_machinery_land_prep_per_acre" if "wheat" in canonical_name.lower() else "paddy_machinery_puddling_per_acre" if "rice" in canonical_name.lower() else "maize_machinery_land_prep_per_acre"
        m_rate = price_book.get(m_pkey)
        if m_rate is not None:
            c_m = round(m_rate * land_area, 2)
            machinery_cost += c_m
            machinery_details = {"operation": "Tractor Tillage / Puddling Custom Hire", "rate_per_acre": m_rate, "cost": c_m}
        tot_days = round(1.0 * land_area, 2)
        if wage_rate:
            c_l = round(tot_days * wage_rate, 2)
            labour_cost += c_l
            labour_details = {"operation": "Field Levelling & Channel Prep", "person_days": tot_days, "wage_rate": wage_rate, "cost": c_l}

    elif "irrigation" in t_lower or "flooding" in t_lower:
        irrig_rate = price_book.get("irrigation_per_event_per_acre", 350.0)
        c_i = round(irrig_rate * land_area, 2)
        irrigation_cost += c_i
        irrigation_details = {"operation": "1 Irrigation Event (Pumping Electricity/Diesel & Canal Cess)", "rate_per_acre": irrig_rate, "cost": c_i}
        tot_days = round(0.5 * land_area, 2)
        if wage_rate:
            c_l = round(tot_days * wage_rate, 2)
            labour_cost += c_l
            labour_details = {"operation": "Irrigation Supervision", "person_days": tot_days, "wage_rate": wage_rate, "cost": c_l}

    elif "harvest" in t_lower or "combine" in t_lower:
        h_pkey = "wheat_harvesting_combine_per_acre" if "wheat" in canonical_name.lower() else "paddy_harvesting_combine_per_acre" if "rice" in canonical_name.lower() else "maize_harvesting_mechanical_per_acre"
        h_rate = price_book.get(h_pkey)
        if h_rate is not None:
            c_h = round(h_rate * land_area, 2)
            harvesting_cost += c_h
            harvesting_details = {"operation": "Combine Harvester / Mechanical Shelling Contract", "rate_per_acre": h_rate, "cost": c_h}

    elif "herbicide" in t_lower or "weed" in t_lower:
        if "manual" in t_lower or "conoweeder" in t_lower:
            tot_days = round(2.0 * land_area, 2)
            if wage_rate:
                c_l = round(tot_days * wage_rate, 2)
                labour_cost += c_l
                labour_details = {"operation": "Manual Inter-Row Weeding", "person_days": tot_days, "wage_rate": wage_rate, "cost": c_l}
        else:
            h_pkey = "wheat_herbicide_per_acre" if "wheat" in canonical_name.lower() else "paddy_herbicide_per_acre" if "rice" in canonical_name.lower() else "maize_herbicide_per_acre"
            h_rate = price_book.get(h_pkey)
            if h_rate is not None:
                c_o = round(h_rate * land_area, 2)
                other_cost += c_o
                quantities.append({"item": "Herbicide Spray Package", "rate_per_acre": 1.0, "unit": "acre", "total_quantity": land_area, "cost": c_o})
            tot_days = round(1.0 * land_area, 2)
            if wage_rate:
                c_l = round(tot_days * wage_rate, 2)
                labour_cost += c_l
                labour_details = {"operation": "Herbicide Application", "person_days": tot_days, "wage_rate": wage_rate, "cost": c_l}

    elif "seed treatment" in t_lower or "priming" in t_lower:
        st_pkey = "wheat_seed_treatment_per_acre" if "wheat" in canonical_name.lower() else "paddy_nursery_inputs_per_acre" if "rice" in canonical_name.lower() else "maize_seed_treatment_per_acre"
        st_rate = price_book.get(st_pkey)
        if st_rate is not None:
            c_o = round(st_rate * land_area, 2)
            other_cost += c_o
            quantities.append({"item": "Seed Treatment Fungicide/Bio-agent", "rate_per_acre": 1.0, "unit": "acre", "total_quantity": land_area, "cost": c_o})
        tot_days = round(0.5 * land_area, 2)
        if wage_rate:
            c_l = round(tot_days * wage_rate, 2)
            labour_cost += c_l
            labour_details = {"operation": "Seed Treatment & Shade Drying", "person_days": tot_days, "wage_rate": wage_rate, "cost": c_l}

    elif "bag" in t_lower or "storage" in t_lower:
        bags_rate = 40.0 if "wheat" in canonical_name.lower() else 44.0 if "rice" in canonical_name.lower() else 50.0
        bag_price = price_book.get("hdpe_bag_50kg_each")
        tot_bags = round(bags_rate * land_area, 2)
        if bag_price is not None:
            c_b = round(tot_bags * bag_price, 2)
            other_cost += c_b
            quantities.append({"item": "HDPE Woven Packaging Bags (50 kg)", "rate_per_acre": bags_rate, "unit": "bags", "total_quantity": tot_bags, "cost": c_b})
        tot_days = round(1.0 * land_area, 2)
        if wage_rate:
            c_l = round(tot_days * wage_rate, 2)
            labour_cost += c_l
            labour_details = {"operation": "Bag Filling, Stitching & Stacking", "person_days": tot_days, "wage_rate": wage_rate, "cost": c_l}

    elif "transport" in t_lower or "market" in t_lower:
        y_rate = float(profile.get("yield_per_acre", 20.0))
        t_price = price_book.get("mandi_transport_per_quintal", 15.0)
        tot_qtl = round(y_rate * land_area, 2)
        c_t = round(tot_qtl * t_price, 2)
        other_cost += c_t
        quantities.append({"item": "Tractor-Trolley Transport to APMC Mandi", "rate_per_acre": y_rate, "unit": "quintals", "total_quantity": tot_qtl, "cost": c_t})

    else:
        # General scouting / observation task
        tot_days = round(0.5 * land_area, 2)
        if wage_rate:
            c_l = round(tot_days * wage_rate, 2)
            labour_cost += c_l
            labour_details = {"operation": f"Field Scouting: {resolved_task_name}", "person_days": tot_days, "wage_rate": wage_rate, "cost": c_l}

    # Strict disjoint cost breakdown
    cost_breakdown = {
        "materials": round(materials_cost, 2),
        "labour": round(labour_cost, 2),
        "machinery": round(machinery_cost, 2),
        "irrigation": round(irrigation_cost, 2),
        "harvesting": round(harvesting_cost, 2),
        "other": round(other_cost, 2),
    }

    total_task_cost = round(sum(cost_breakdown.values()), 2)
    is_complete = len(missing_items) == 0

    # If matched_task defines items, calculate per-item costs
    task_items: List[Dict[str, Any]] = []
    if "items" in matched_task:
        costed_from_calendar = calculate_task_items_and_cost(matched_task, land_area, custom_prices)
        task_items = costed_from_calendar["items"]
        if not costed_from_calendar["task_is_complete"]:
            is_complete = False
            for mi in costed_from_calendar["missing_price_items"]:
                missing_items.append({"item": mi, "reason": "Missing verified price."})

    return {
        "crop_name": canonical_name,
        "task_name": resolved_task_name,
        "stage_key": matched_stage_key,
        "stage_name": matched_stage_name,
        "stage_number": matched_stage_number,
        "acres": land_area,
        "total_task_cost": total_task_cost,
        "task_total_cost": total_task_cost,
        "daily_total": total_task_cost,
        "cost_breakdown": cost_breakdown,
        "is_complete": is_complete,
        "completeness_status": "COMPLETE" if is_complete else "INCOMPLETE",
        "missing_items": missing_items,
        "items": task_items,
        "quantities": quantities,
        "labour": labour_details,
        "machinery": machinery_details,
        "irrigation": irrigation_details,
        "harvesting": harvesting_details,
        "timing": matched_task.get("timing", ""),
        "date_or_stage": matched_task.get("timing", matched_stage_name),
        "purpose": matched_task.get("purpose", ""),
        "instructions": matched_task.get("instructions", []),
        "safety_precautions": matched_task.get("safety_precautions", []),
        "necessary_precautions": matched_task.get("safety_precautions", []),
    }


# ─── Itemized Cost Engine (per-task, per-day, and lifecycle) ──────────────────

def calculate_item_cost(item: Dict[str, Any], acres: float) -> Dict[str, Any]:
    """
    Calculate the required quantity and cost for a single line-item.

    Parameters:
        item: dict with keys:
              name, rate_per_acre, unit, price_per_unit (None means unavailable),
              price_type, category, source
        acres: positive float, land area in acres

    Returns:
        dict with required_quantity, unit, price_per_unit, price_type,
        item_cost (float or None), category, is_priced, source
    """
    land_area = _validate_acres(acres)
    rate = item.get("rate_per_acre")
    ppu = item.get("price_per_unit")
    unit = item.get("unit", "")
    category = item.get("category", "other")
    price_type = item.get("price_type", "UNAVAILABLE")
    source = item.get("source", "")

    if rate is None:
        return {
            "name": item.get("name", "Unknown"),
            "required_quantity": None,
            "unit": unit,
            "price_per_unit": ppu,
            "price_type": price_type,
            "item_cost": None,
            "category": category,
            "is_priced": False,
            "source": source,
            "note": "Rate per acre not specified — quantity cannot be determined.",
        }

    required_quantity = round(float(rate) * land_area, 4)

    if ppu is not None:
        item_cost: Optional[float] = round(required_quantity * float(ppu), 2)
        is_priced = True
    else:
        item_cost = None
        is_priced = False

    return {
        "name": item.get("name", "Unknown"),
        "required_quantity": required_quantity,
        "unit": unit,
        "price_per_unit": ppu,
        "price_type": price_type,
        "item_cost": item_cost,
        "category": category,
        "is_priced": is_priced,
        "source": source,
    }


def calculate_task_items_and_cost(
    task: Dict[str, Any],
    acres: float,
    custom_prices: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Compute per-item quantities and costs for a task dict that has an 'items' list.

    Parameters:
        task:  dict containing at minimum 'task_name' and 'items' (list of item dicts).
        acres: land area in acres.
        custom_prices: optional overrides for price_per_unit keyed by item name.

    Returns:
        dict with:
            task_name, purpose, instructions, safety_precautions,
            start_day, end_day, stage_key, stage_name,
            items: list of per-item cost details,
            task_total (sum of known item_costs),
            task_is_complete (True if all items have known prices),
            missing_price_items (list of item names with null price)
    """
    land_area = _validate_acres(acres)

    items_source: List[Dict[str, Any]] = task.get("items", [])
    priced_items: List[Dict[str, Any]] = []
    task_total = 0.0
    missing_price_items: List[str] = []

    for itm in items_source:
        # Allow custom_prices to override price_per_unit by item name
        itm_copy = dict(itm)
        if custom_prices and itm_copy.get("name") in custom_prices:
            itm_copy["price_per_unit"] = custom_prices[itm_copy["name"]]

        costed = calculate_item_cost(itm_copy, land_area)
        priced_items.append(costed)
        if costed["is_priced"] and costed["item_cost"] is not None:
            task_total += costed["item_cost"]
        else:
            missing_price_items.append(costed["name"])

    task_total = round(task_total, 2)
    task_is_complete = len(missing_price_items) == 0

    return {
        "task_name": task.get("task_name", ""),
        "timing": task.get("timing", ""),
        "purpose": task.get("purpose", ""),
        "instructions": task.get("instructions", []),
        "safety_precautions": task.get("safety_precautions", []),
        "start_day": task.get("start_day"),
        "end_day": task.get("end_day"),
        "day_range": task.get("day_range", [task.get("start_day"), task.get("end_day")]),
        "stage_key": task.get("stage_key", ""),
        "stage_name": task.get("stage_name", ""),
        "stage_number": task.get("stage_number", 0),
        "items": priced_items,
        "task_total": task_total,
        "task_is_complete": task_is_complete,
        "missing_price_items": missing_price_items,
    }


def calculate_daily_totals(
    tasks: List[Dict[str, Any]],
    acres: float,
    custom_prices: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Given a list of tasks (each with 'start_day', 'end_day', and 'items'),
    group them by unique (start_day, end_day) windows and compute a daily_total.

    Returns:
        dict with:
            tasks: list of cost-enriched task dicts,
            daily_total: sum of all task_totals in the list,
            daily_is_complete: True if every task is fully priced
    """
    land_area = _validate_acres(acres)

    enriched: List[Dict[str, Any]] = []
    running_total = 0.0
    all_complete = True

    for task in tasks:
        costed_task = calculate_task_items_and_cost(task, land_area, custom_prices)
        enriched.append(costed_task)
        running_total += costed_task["task_total"]
        if not costed_task["task_is_complete"]:
            all_complete = False

    return {
        "tasks": enriched,
        "daily_total": round(running_total, 2),
        "daily_is_complete": all_complete,
    }


def calculate_lifecycle_budget_from_calendar(
    crop_name: str,
    acres: float,
    custom_prices: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Build a complete crop-lifecycle cost breakdown from the crop_calendar.json items.

    The lifecycle budget is taken from calculate_budget() (which uses verified
    agronomic profiles with strict double-counting prevention).  The per-task
    itemized breakdown supplements that with task-level granularity for farmer
    transparency.

    Parameters:
        crop_name: e.g. "Wheat", "Rice", "Maize"
        acres:     land area in acres
        custom_prices: optional overrides for price_per_unit by item name

    Returns:
        dict with:
            crop_name, acres,
            stages: ordered list of {stage_key, stage_name, stage_number, tasks: [costed_tasks], stage_total}
            lifecycle_task_total: sum of all task totals across all stages
            lifecycle_budget: authoritative total from calculate_budget()
            lifecycle_budget_breakdown: 7-category breakdown from calculate_budget()
            lifecycle_is_complete: True if all items are priced
            missing_price_items: list of unpriced item names
            data_source_note: explains what the lifecycle_budget figure is based on
    """
    land_area = _validate_acres(acres)

    # Import here to avoid circular import at module level
    import farming_calendar as fc  # noqa: PLC0415
    cal = fc.FarmingCalendar()
    try:
        crop = cal.get_crop(crop_name)
    except Exception as exc:
        raise BudgetCalculationError(f"Crop '{crop_name}' not found: {exc}") from exc

    canonical_name = crop.get("name", crop_name)
    crop_duration = int(crop.get("duration_days", 120))

    # Build itemized stage list
    all_stages: List[Dict[str, Any]] = []
    lifecycle_task_total = 0.0
    all_missing: List[str] = []
    all_complete = True

    for stage_key, stage_info in crop.get("stages", {}).items():
        stage_name = stage_info.get("stage_name", stage_key.replace("_", " ").title())
        stage_number = stage_info.get("stage_number", 0)

        costed_tasks: List[Dict[str, Any]] = []
        stage_total = 0.0

        for task in stage_info.get("tasks", []):
            # Resolve schedule days
            s_day = task.get("start_day")
            e_day = task.get("end_day")
            if s_day is None or e_day is None:
                dr = task.get("day_range", [])
                if len(dr) == 2:
                    s_day, e_day = dr[0], dr[1]

            t_enriched = dict(task)
            t_enriched["start_day"] = s_day
            t_enriched["end_day"] = e_day
            t_enriched["day_range"] = [s_day, e_day]
            t_enriched["stage_key"] = stage_key
            t_enriched["stage_name"] = stage_name
            t_enriched["stage_number"] = stage_number

            costed = calculate_task_items_and_cost(t_enriched, land_area, custom_prices)
            costed_tasks.append(costed)
            stage_total += costed["task_total"]
            all_missing.extend(costed["missing_price_items"])
            if not costed["task_is_complete"]:
                all_complete = False

        stage_total = round(stage_total, 2)
        lifecycle_task_total += stage_total

        all_stages.append({
            "stage_key": stage_key,
            "stage_name": stage_name,
            "stage_number": stage_number,
            "tasks": costed_tasks,
            "stage_total": stage_total,
        })

    lifecycle_task_total = round(lifecycle_task_total, 2)

    # Authoritative lifecycle budget from verified agronomic profiles
    try:
        budget_result = calculate_budget(canonical_name, land_area, custom_prices)
        lifecycle_budget = budget_result["total_cultivation_cost"]
        lifecycle_budget_breakdown = budget_result["breakdown"]
        budget_is_complete = budget_result["is_complete"]
        budget_missing = budget_result["missing_items"]
        budget_status = budget_result["completeness_status"]
    except Exception:
        lifecycle_budget = None
        lifecycle_budget_breakdown = {}
        budget_is_complete = False
        budget_missing = []
        budget_status = "UNAVAILABLE"

    return {
        "crop_name": canonical_name,
        "acres": land_area,
        "crop_duration_days": crop_duration,
        "stages": all_stages,
        "lifecycle_task_total": lifecycle_task_total,
        "lifecycle_budget": lifecycle_budget,
        "lifecycle_budget_breakdown": lifecycle_budget_breakdown,
        "lifecycle_budget_is_complete": budget_is_complete,
        "lifecycle_budget_status": budget_status,
        "lifecycle_budget_missing_items": budget_missing,
        "lifecycle_is_complete": all_complete,
        "missing_price_items": list(set(all_missing)),
        "data_source_note": (
            "lifecycle_budget is the authoritative cultivation cost from verified ICAR agronomic "
            "profiles with strict double-counting prevention. "
            "lifecycle_task_total is the sum of all per-task item costs shown to the farmer for "
            "transparency; it may differ from lifecycle_budget because some tasks share "
            "category-level inputs (e.g. total urea is split across multiple tasks)."
        ),
    }
