"""System configuration and metadata endpoint router."""
from pathlib import Path
from fastapi import APIRouter
import pandas as pd

from backend.app.models.schemas import (
    ConfigResponse,
    CropConstraintConfig,
    InputRangeConfig,
    WeatherScenarioConfig,
)
from backend.app.optimizer.model import AquaShiftOptimizer

router = APIRouter(tags=["Configuration"])

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
_optimizer = AquaShiftOptimizer()


@router.get("/config", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    """Return available crops, weather scenarios, optimization modes, input bounds, and units."""
    # 1. Load crops from data/crops.csv
    crops_path = DATA_DIR / "crops.csv"
    crops_df = pd.read_csv(crops_path)
    crops_list = [
        CropConstraintConfig(
            crop_id=str(row["crop_id"]),
            crop_name=str(row["crop_name"]),
            baseline_yield_t_ha=float(row["baseline_yield_t_ha"]),
            seasonal_water_m3_ha=float(row["seasonal_water_m3_ha"]),
            cultivation_cost_inr_ha=float(row["cultivation_cost_inr_ha"]),
            price_inr_quintal=float(row["price_inr_quintal"]),
            calories_kcal_kg=float(row["calories_kcal_kg"]),
            drought_sensitivity_ky=float(row["drought_sensitivity_ky"]),
            min_land_share=float(row["min_land_share"]),
            max_land_share=float(row["max_land_share"]),
        )
        for _, row in crops_df.iterrows()
    ]

    # 2. Load weather scenarios from data/weather_scenarios.csv
    weather_path = DATA_DIR / "weather_scenarios.csv"
    weather_df = pd.read_csv(weather_path)
    scenarios_list = [
        WeatherScenarioConfig(
            scenario_id=str(row["scenario_id"]),
            scenario_name=str(row["scenario_name"]),
            effective_rainfall_multiplier=float(row["effective_rainfall_multiplier"]),
            yield_stress_multiplier=float(row["yield_stress_multiplier"]),
            description=str(row["description"]),
        )
        for _, row in weather_df.iterrows()
    ]

    # 3. Input ranges
    input_ranges = [
        InputRangeConfig(
            parameter="total_land_ha",
            min_value=0.1,
            max_value=1000.0,
            unit="hectares (ha)",
            description="Total available farm land area",
        ),
        InputRangeConfig(
            parameter="water_budget_m3",
            min_value=0.0,
            max_value=5000000.0,
            unit="cubic meters (m³)",
            description="Available seasonal irrigation water quota",
        ),
        InputRangeConfig(
            parameter="water_budget_reduction_pct",
            min_value=0.0,
            max_value=100.0,
            unit="percentage (%)",
            description="Percentage cut in water quota relative to baseline",
        ),
        InputRangeConfig(
            parameter="water_availability_ratio",
            min_value=0.05,
            max_value=2.0,
            unit="ratio [0.05, 2.0]",
            description="Relative water availability ratio for crop evapotranspiration",
        ),
        InputRangeConfig(
            parameter="food_target_increase_pct",
            min_value=-100.0,
            max_value=500.0,
            unit="percentage (%)",
            description="Percentage adjustment to nutritional food target relative to baseline",
        ),
        InputRangeConfig(
            parameter="income_target_increase_pct",
            min_value=-100.0,
            max_value=500.0,
            unit="percentage (%)",
            description="Percentage adjustment to net income target relative to baseline",
        ),
    ]

    # 4. Units dictionary
    units_dict = {
        "land_area": "hectares (ha)",
        "yield": "tonnes per hectare (t/ha)",
        "water_demand": "cubic meters per hectare (m³/ha)",
        "water_volume": "cubic meters (m³)",
        "food_energy": "kilocalories (kcal)",
        "monetary": "Indian Rupees (INR / ₹)",
        "price": "INR per quintal (₹/quintal)",
        "cost": "INR per hectare (₹/ha)",
        "caloric_density": "kcal per kilogram (kcal/kg)",
    }

    # 5. Baseline assumptions (dynamically derived from canonical optimizer baseline)
    _, ref_baseline = _optimizer.calculate_baseline(
        total_land_ha=10.0,
        rainfall_scenario="normal",
        water_availability_ratio=1.0,
        selected_crops=_optimizer.all_crops,
    )
    baseline_assumptions = {
        "reference_land_ha": 10.0,
        "paddy_share": 0.70,
        "maize_share": 0.30,
        "baseline_water_m3": ref_baseline["total_water_use_m3"],
        "baseline_food_kcal": ref_baseline["total_food_kcal"],
        "baseline_net_income_inr": ref_baseline["total_net_income_inr"],
    }

    return ConfigResponse(
        region_name="Punjab/Haryana-style paddy-wheat reference belt",
        synthetic_data_disclosure="Synthetic demo data calibrated to public agri statistics.",
        crops=crops_list,
        rainfall_scenarios=scenarios_list,
        optimization_modes=["weighted", "lexicographic"],
        supported_priorities=["water", "food", "income", "water_first_priority"],
        default_land_ha=10.0,
        baseline_assumptions=baseline_assumptions,
        input_ranges=input_ranges,
        units=units_dict,
    )
