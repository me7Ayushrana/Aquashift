"""Test suite for AquaShift Machine Learning Predictor."""
from pathlib import Path
import numpy as np
import pytest

from backend.app.ml.predictor import AquaShiftPredictor
from backend.app.models.schemas import CropPrediction, BatchPredictionResponse
from scripts.train_model import train_models

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "app" / "ml" / "artifacts"
ALL_CROPS = ["paddy", "wheat", "maize", "pulses", "millets"]
ALL_SCENARIOS = ["normal", "deficit", "severe_deficit", "surplus"]


@pytest.fixture(scope="module")
def predictor():
    """Ensure models are trained and return an initialized predictor instance."""
    if not (ARTIFACTS_DIR / "yield_model.joblib").exists():
        train_models(artifacts_dir=ARTIFACTS_DIR)
    return AquaShiftPredictor(artifacts_dir=ARTIFACTS_DIR)


def test_1_models_loaded_successfully(predictor):
    """1. Verify that joblib model artifacts exist and load into predictor."""
    assert (ARTIFACTS_DIR / "yield_model.joblib").exists()
    assert (ARTIFACTS_DIR / "water_demand_model.joblib").exists()
    assert (ARTIFACTS_DIR / "metrics.json").exists()
    assert predictor.yield_model is not None
    assert predictor.water_model is not None
    assert "yield_model" in predictor.metrics
    assert "water_demand_model" in predictor.metrics


def test_2_deterministic_training():
    """2. Verify that training twice with fixed seed yields identical validation metrics."""
    metrics_run1 = train_models(artifacts_dir=ARTIFACTS_DIR, seed=42)
    metrics_run2 = train_models(artifacts_dir=ARTIFACTS_DIR, seed=42)

    # Check random split determinism
    assert metrics_run1["yield_model"]["random_split_80_20"]["mae"] == metrics_run2["yield_model"]["random_split_80_20"]["mae"]
    assert metrics_run1["yield_model"]["random_split_80_20"]["rmse"] == metrics_run2["yield_model"]["random_split_80_20"]["rmse"]
    assert metrics_run1["yield_model"]["random_split_80_20"]["r2"] == metrics_run2["yield_model"]["random_split_80_20"]["r2"]

    # Check block holdout determinism
    assert metrics_run1["yield_model"]["contiguous_block_holdout"]["mae"] == metrics_run2["yield_model"]["contiguous_block_holdout"]["mae"]
    assert metrics_run1["yield_model"]["contiguous_block_holdout"]["rmse"] == metrics_run2["yield_model"]["contiguous_block_holdout"]["rmse"]
    assert metrics_run1["yield_model"]["contiguous_block_holdout"]["r2"] == metrics_run2["yield_model"]["contiguous_block_holdout"]["r2"]

    # Check water model determinism
    assert metrics_run1["water_demand_model"]["random_split_80_20"]["mae"] == metrics_run2["water_demand_model"]["random_split_80_20"]["mae"]
    assert metrics_run1["water_demand_model"]["scenario_holdout"]["mae"] == metrics_run2["water_demand_model"]["scenario_holdout"]["mae"]


def test_3_output_schemas(predictor):
    """3. Verify prediction outputs match Pydantic schemas."""
    pred = predictor.predict_crop(
        crop_id="paddy",
        rainfall_scenario="normal",
        water_availability_ratio=1.0,
    )
    assert isinstance(pred, CropPrediction)
    assert pred.crop_id == "paddy"
    assert pred.crop_name == "Paddy"

    batch = predictor.predict_all_crops(
        rainfall_scenario="deficit",
        water_availability_ratio=0.8,
    )
    assert isinstance(batch, BatchPredictionResponse)
    assert len(batch.predictions) == 5
    for c in ALL_CROPS:
        assert c in batch.predictions
        assert isinstance(batch.predictions[c], CropPrediction)


def test_4_nonnegative_physical_bounds(predictor):
    """4. Predictions and uncertainty intervals must be strictly nonnegative and ordered."""
    for c in ALL_CROPS:
        for sc in ALL_SCENARIOS:
            for w in [0.20, 0.50, 0.80, 1.00]:
                pred = predictor.predict_crop(crop_id=c, rainfall_scenario=sc, water_availability_ratio=w)
                assert pred.predicted_yield_t_ha >= 0.05
                assert pred.predicted_water_demand_m3_ha >= 200.0
                assert pred.yield_range_lower <= pred.predicted_yield_t_ha <= pred.yield_range_upper
                assert pred.water_range_lower <= pred.predicted_water_demand_m3_ha <= pred.water_range_upper


def test_5_input_feature_validation(predictor):
    """5. Invalid crop_id or weather scenario must raise informative ValueError."""
    with pytest.raises(ValueError, match="Unknown crop_id 'invalid_crop'"):
        predictor.predict_crop(
            crop_id="invalid_crop",
            rainfall_scenario="normal",
            water_availability_ratio=1.0,
        )

    with pytest.raises(ValueError, match="Unknown rainfall_scenario 'cyclone'"):
        predictor.predict_crop(
            crop_id="paddy",
            rainfall_scenario="cyclone",
            water_availability_ratio=1.0,
        )


def test_6_exhaustive_water_stress_monotonicity(predictor):
    """6. Exhaustive check: Yield must never decrease as water availability increases.

    Evaluates all 5 crops across all 4 weather scenarios on a dense 101-point grid
    (2,000 total consecutive step comparisons).
    """
    water_grid = np.linspace(0.20, 1.20, 101)  # step 0.01

    for c in ALL_CROPS:
        for sc in ALL_SCENARIOS:
            yields = [
                predictor.predict_crop(
                    crop_id=c,
                    rainfall_scenario=sc,
                    water_availability_ratio=w,
                ).predicted_yield_t_ha
                for w in water_grid
            ]

            diffs = np.diff(yields)
            min_diff = np.min(diffs)
            assert min_diff >= -1e-6, (
                f"Monotonicity violation for crop '{c}' in scenario '{sc}': "
                f"minimum pairwise diff {min_diff:.6f} is negative"
            )


def test_7_water_demand_independent_of_water_availability(predictor):
    """7. Water demand must not vary when water availability ratio changes."""
    for c in ALL_CROPS:
        for sc in ALL_SCENARIOS:
            demand_low_water = predictor.predict_crop(
                crop_id=c,
                rainfall_scenario=sc,
                water_availability_ratio=0.20,
            ).predicted_water_demand_m3_ha

            demand_high_water = predictor.predict_crop(
                crop_id=c,
                rainfall_scenario=sc,
                water_availability_ratio=1.00,
            ).predicted_water_demand_m3_ha

            assert demand_low_water == demand_high_water, (
                f"Water demand varied with water availability for '{c}' in '{sc}': "
                f"{demand_low_water} vs {demand_high_water}"
            )


def test_8_water_demand_meteorological_ordering(predictor):
    """8. Water demand must follow: Severe Deficit > Deficit > Normal > Surplus."""
    scenarios_order = ["severe_deficit", "deficit", "normal", "surplus"]

    for c in ALL_CROPS:
        demands = [
            predictor.predict_crop(
                crop_id=c,
                rainfall_scenario=sc,
                water_availability_ratio=1.0,
            ).predicted_water_demand_m3_ha
            for sc in scenarios_order
        ]

        for i in range(len(demands) - 1):
            assert demands[i] > demands[i + 1], (
                f"Water demand ordering violation in ML predictor for '{c}': "
                f"{scenarios_order[i]} ({demands[i]}) not > {scenarios_order[i+1]} ({demands[i+1]})"
            )


def test_9_dual_validation_metrics_present(predictor):
    """9. Verify both random split and contiguous block holdout metrics exist in metrics.json."""
    assert "random_split_80_20" in predictor.metrics["yield_model"]
    assert "contiguous_block_holdout" in predictor.metrics["yield_model"]
    assert "random_split_80_20" in predictor.metrics["water_demand_model"]
    assert "scenario_holdout" in predictor.metrics["water_demand_model"]

    # Verify block holdout has lower R2 / higher RMSE as expected from true out-of-band evaluation
    rnd_rmse = predictor.metrics["yield_model"]["random_split_80_20"]["rmse"]
    blk_rmse = predictor.metrics["yield_model"]["contiguous_block_holdout"]["rmse"]
    assert blk_rmse > rnd_rmse, f"Block holdout RMSE ({blk_rmse}) should exceed random split RMSE ({rnd_rmse})"


def test_10_interval_bounds_clamped_and_well_ordered(predictor):
    """10. Verify uncertainty interval bounds are strictly well-ordered and clamped to numerical floor."""
    for c in ALL_CROPS:
        for sc in ALL_SCENARIOS:
            for w in [0.20, 0.40, 0.70, 1.00, 1.20]:
                pred = predictor.predict_crop(crop_id=c, rainfall_scenario=sc, water_availability_ratio=w)
                # Lower clamp at 0.05 t/ha
                assert pred.yield_range_lower >= 0.05, f"Yield lower bound {pred.yield_range_lower} < 0.05"
                assert pred.yield_range_lower <= pred.predicted_yield_t_ha
                assert pred.predicted_yield_t_ha <= pred.yield_range_upper
                # Water lower clamp at 200.0 m3/ha
                assert pred.water_range_lower >= 200.0, f"Water lower bound {pred.water_range_lower} < 200.0"
                assert pred.water_range_lower <= pred.predicted_water_demand_m3_ha
                assert pred.predicted_water_demand_m3_ha <= pred.water_range_upper
