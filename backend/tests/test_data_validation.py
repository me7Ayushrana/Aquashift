"""Data validation test suite for AquaShift agricultural and weather datasets."""
from pathlib import Path
import pandas as pd
import numpy as np
import pytest
from scripts.generate_data import compute_fao_yield, compute_water_demand

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CROPS_PATH = DATA_DIR / "crops.csv"
WEATHER_PATH = DATA_DIR / "weather_scenarios.csv"
TRAINING_PATH = DATA_DIR / "training_data.csv"

EXPECTED_CROPS = {"paddy", "wheat", "maize", "pulses", "millets"}
EXPECTED_WEATHER = {"normal", "deficit", "severe_deficit", "surplus"}

REQUIRED_CROP_COLUMNS = [
    "crop_id",
    "crop_name",
    "baseline_yield_t_ha",
    "seasonal_water_m3_ha",
    "cultivation_cost_inr_ha",
    "price_inr_quintal",
    "calories_kcal_kg",
    "drought_sensitivity_ky",
    "min_land_share",
    "max_land_share",
]

REQUIRED_WEATHER_COLUMNS = [
    "scenario_id",
    "scenario_name",
    "effective_rainfall_multiplier",
    "yield_stress_multiplier",
    "description",
]

REQUIRED_TRAINING_COLUMNS = [
    "crop_id",
    "rainfall_scenario",
    "effective_rainfall_multiplier",
    "water_availability_ratio",
    "drought_sensitivity_ky",
    "baseline_yield_t_ha",
    "seasonal_water_m3_ha",
    "actual_yield_t_ha",
    "water_demand_m3_ha",
]


@pytest.fixture(scope="module")
def crops_df():
    assert CROPS_PATH.exists(), f"Missing {CROPS_PATH}"
    return pd.read_csv(CROPS_PATH)


@pytest.fixture(scope="module")
def weather_df():
    assert WEATHER_PATH.exists(), f"Missing {WEATHER_PATH}"
    return pd.read_csv(WEATHER_PATH)


@pytest.fixture(scope="module")
def training_df():
    assert TRAINING_PATH.exists(), f"Missing {TRAINING_PATH}"
    return pd.read_csv(TRAINING_PATH)


# --- Task 6 Checks ---

def test_1_all_five_crops_exist(crops_df):
    """1. All five required crops must exist in crops.csv."""
    present_crops = set(crops_df["crop_id"].str.lower())
    assert present_crops == EXPECTED_CROPS, f"Missing crops: {EXPECTED_CROPS - present_crops}"


def test_2_crop_identifiers_are_unique(crops_df):
    """2. Crop identifiers must be strictly unique."""
    assert crops_df["crop_id"].is_unique, "Duplicate crop_id detected in crops.csv"


def test_3_required_columns_exist(crops_df, weather_df, training_df):
    """3. Required columns must be present in all datasets."""
    for col in REQUIRED_CROP_COLUMNS:
        assert col in crops_df.columns, f"Missing crop column: {col}"
    for col in REQUIRED_WEATHER_COLUMNS:
        assert col in weather_df.columns, f"Missing weather column: {col}"
    for col in REQUIRED_TRAINING_COLUMNS:
        assert col in training_df.columns, f"Missing training column: {col}"


def test_4_numerical_values_within_sensible_bounds(crops_df):
    """4. Numerical values must be positive and within realistic agronomic bounds."""
    # Yields: between 0.5 t/ha and 15.0 t/ha
    assert (crops_df["baseline_yield_t_ha"] >= 0.5).all()
    assert (crops_df["baseline_yield_t_ha"] <= 15.0).all()

    # Seasonal water: between 1,000 m3/ha and 25,000 m3/ha
    assert (crops_df["seasonal_water_m3_ha"] >= 1000).all()
    assert (crops_df["seasonal_water_m3_ha"] <= 25000).all()

    # Cultivation cost: between 10,000 INR/ha and 100,000 INR/ha
    assert (crops_df["cultivation_cost_inr_ha"] >= 10000).all()
    assert (crops_df["cultivation_cost_inr_ha"] <= 100000).all()

    # Prices: between 1,000 and 20,000 INR/quintal
    assert (crops_df["price_inr_quintal"] >= 1000).all()
    assert (crops_df["price_inr_quintal"] <= 20000).all()

    # Calories: between 2,000 and 5,000 kcal/kg
    assert (crops_df["calories_kcal_kg"] >= 2000).all()
    assert (crops_df["calories_kcal_kg"] <= 5000).all()

    # Drought sensitivity Ky: between 0.3 and 1.8
    assert (crops_df["drought_sensitivity_ky"] >= 0.3).all()
    assert (crops_df["drought_sensitivity_ky"] <= 1.8).all()


def test_5_crop_min_shares_feasible(crops_df):
    """5. Sum of crop minimum land shares must not exceed 1.0 (feasible allocation)."""
    assert (crops_df["min_land_share"] >= 0.0).all()
    assert (crops_df["min_land_share"] <= 1.0).all()
    total_min_share = crops_df["min_land_share"].sum()
    assert total_min_share <= 1.0, f"Total minimum land share {total_min_share} exceeds 1.0"


def test_6_crop_max_shares_valid(crops_df):
    """6. Max land shares must be >= min_land_share and <= 1.0."""
    assert (crops_df["max_land_share"] <= 1.0).all()
    assert (crops_df["max_land_share"] >= crops_df["min_land_share"]).all()
    assert (crops_df["max_land_share"] > 0.0).all()


def test_7_all_four_weather_scenarios_exist(weather_df):
    """7. All four weather scenarios must exist."""
    present_scenarios = set(weather_df["scenario_id"].str.lower())
    assert present_scenarios == EXPECTED_WEATHER, f"Missing scenarios: {EXPECTED_WEATHER - present_scenarios}"


def test_8_weather_multipliers_valid(weather_df):
    """8. Weather multipliers must be strictly positive and physiologically sensible."""
    assert (weather_df["effective_rainfall_multiplier"] > 0.0).all()
    assert (weather_df["effective_rainfall_multiplier"] <= 3.0).all()
    assert (weather_df["yield_stress_multiplier"] > 0.0).all()
    assert (weather_df["yield_stress_multiplier"] <= 2.0).all()


def test_9_training_dataset_contains_all_crops(training_df):
    """9. Training dataset must contain observations for all five crops."""
    crops_in_train = set(training_df["crop_id"].str.lower())
    assert crops_in_train == EXPECTED_CROPS


def test_10_training_dataset_contains_all_scenarios(training_df):
    """10. Training dataset must contain observations for all four rainfall scenarios."""
    scenarios_in_train = set(training_df["rainfall_scenario"].str.lower())
    assert scenarios_in_train == EXPECTED_WEATHER


def test_11_no_negative_yields_or_water_demand(training_df):
    """11. Actual yields and water demand must be strictly non-negative."""
    assert (training_df["actual_yield_t_ha"] >= 0.0).all(), "Negative actual yield detected"
    assert (training_df["water_demand_m3_ha"] >= 0.0).all(), "Negative water demand detected"


def test_12_controlled_water_stress_monotonicity(crops_df, weather_df):
    """12. Under controlled water-stress conditions, yield must not increase as water availability drops."""
    # Test across all 5 crops and all 4 weather scenarios with 0 noise
    water_grid = np.linspace(0.20, 1.20, 50)  # increasing water availability

    for _, crop in crops_df.iterrows():
        base_yield = float(crop["baseline_yield_t_ha"])
        ky = float(crop["drought_sensitivity_ky"])

        for _, weather in weather_df.iterrows():
            rain_mult = float(weather["effective_rainfall_multiplier"])
            stress_mult = float(weather["yield_stress_multiplier"])

            yields = [
                compute_fao_yield(
                    baseline_yield=base_yield,
                    ky=ky,
                    yield_stress_mult=stress_mult,
                    effective_rain_mult=rain_mult,
                    water_avail_ratio=w,
                    noise=0.0,
                )
                for w in water_grid
            ]

            # Yield must be monotonically non-decreasing as water availability increases
            diffs = np.diff(yields)
            assert (diffs >= -1e-6).all(), (
                f"Monotonicity violation for crop '{crop['crop_id']}' in scenario '{weather['scenario_id']}': "
                f"negative yield change detected when water availability increased"
            )


def test_13_deterministic_water_demand_ordering(crops_df, weather_df):
    """13. Deterministic expected water demand must follow: Severe Deficit > Deficit > Normal > Surplus."""
    scenarios_order = ["severe_deficit", "deficit", "normal", "surplus"]
    weather_map = {row["scenario_id"]: row["effective_rainfall_multiplier"] for _, row in weather_df.iterrows()}

    for _, crop in crops_df.iterrows():
        seasonal_water = float(crop["seasonal_water_m3_ha"])
        demands = [
            compute_water_demand(
                seasonal_water=seasonal_water,
                effective_rain_mult=float(weather_map[sc]),
                noise=0.0,
            )
            for sc in scenarios_order
        ]

        # Verify strictly decreasing demand as rainfall improves (severe_deficit > deficit > normal > surplus)
        for i in range(len(demands) - 1):
            assert demands[i] > demands[i + 1], (
                f"Water demand ordering violation for crop '{crop['crop_id']}': "
                f"{scenarios_order[i]} ({demands[i]}) not > {scenarios_order[i+1]} ({demands[i+1]})"
            )


def test_14_yield_ratio_invariants(crops_df, weather_df, training_df):
    """14. Pre-noise relative yield in [0.05, 1.0]; post-noise actual/potential in [0.0475, 1.05]."""
    # 1. Pre-noise check across parameter space
    water_grid = np.linspace(0.10, 1.30, 25)
    for _, crop in crops_df.iterrows():
        base_yield = float(crop["baseline_yield_t_ha"])
        ky = float(crop["drought_sensitivity_ky"])
        for _, weather in weather_df.iterrows():
            stress_mult = float(weather["yield_stress_multiplier"])
            rain_mult = float(weather["effective_rainfall_multiplier"])
            ym = base_yield * stress_mult

            for w in water_grid:
                det_yield = compute_fao_yield(
                    baseline_yield=base_yield,
                    ky=ky,
                    yield_stress_mult=stress_mult,
                    effective_rain_mult=rain_mult,
                    water_avail_ratio=w,
                    noise=0.0,
                )
                pre_noise_ratio = det_yield / ym
                assert 0.05 - 1e-4 <= pre_noise_ratio <= 1.0 + 1e-4, (
                    f"Pre-noise relative yield {pre_noise_ratio:.4f} outside [0.05, 1.0] for {crop['crop_id']} in {weather['scenario_id']}"
                )

    # 2. Post-noise check across all training data records
    weather_stress = {row["scenario_id"]: float(row["yield_stress_multiplier"]) for _, row in weather_df.iterrows()}
    potential_yields = training_df.apply(
        lambda r: r["baseline_yield_t_ha"] * weather_stress[r["rainfall_scenario"]], axis=1
    )
    post_noise_ratios = training_df["actual_yield_t_ha"] / potential_yields
    assert post_noise_ratios.min() >= 0.0475 - 1e-4, f"Min ratio {post_noise_ratios.min()} < 0.0475"
    assert post_noise_ratios.max() <= 1.05 + 1e-4, f"Max ratio {post_noise_ratios.max()} > 1.05"

