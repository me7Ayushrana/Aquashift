"""AquaShift Machine Learning Predictor Service.

Provides a typed, physically-bounded prediction interface for crop yield and
seasonal supplementary irrigation water demand.
"""
from pathlib import Path
from typing import Dict, List, Optional
import joblib
import numpy as np
import pandas as pd

from backend.app.models.schemas import (
    CropPrediction,
    BatchPredictionResponse,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_ARTIFACTS_DIR = ROOT_DIR / "backend" / "app" / "ml" / "artifacts"
DEFAULT_DATA_DIR = ROOT_DIR / "data"


class AquaShiftPredictor:
    """Inference engine for crop yield and irrigation water demand prediction."""

    def __init__(
        self,
        artifacts_dir: Optional[Path] = None,
        data_dir: Optional[Path] = None,
    ):
        self.artifacts_dir = Path(artifacts_dir or DEFAULT_ARTIFACTS_DIR)
        self.data_dir = Path(data_dir or DEFAULT_DATA_DIR)

        # Load models and metadata
        self.yield_model_path = self.artifacts_dir / "yield_model.joblib"
        self.water_model_path = self.artifacts_dir / "water_demand_model.joblib"
        self.metrics_path = self.artifacts_dir / "metrics.json"

        if not self.yield_model_path.exists() or not self.water_model_path.exists():
            raise FileNotFoundError(
                f"Model artifacts not found in {self.artifacts_dir}. Run scripts/train_model.py first."
            )

        self.yield_model = joblib.load(self.yield_model_path)
        self.water_model = joblib.load(self.water_model_path)

        if self.metrics_path.exists():
            import json
            with open(self.metrics_path, "r", encoding="utf-8") as f:
                self.metrics = json.load(f)
        else:
            self.metrics = {
                "yield_model": {"rmse": 0.0943, "mae": 0.0720},
                "water_demand_model": {"rmse": 98.8802, "mae": 66.5212},
            }

        # Load domain baselines from CSV
        crops_df = pd.read_csv(self.data_dir / "crops.csv")
        weather_df = pd.read_csv(self.data_dir / "weather_scenarios.csv")

        self.crops_lookup: Dict[str, dict] = {
            row["crop_id"].lower(): row.to_dict() for _, row in crops_df.iterrows()
        }
        self.weather_lookup: Dict[str, dict] = {
            row["scenario_id"].lower(): row.to_dict() for _, row in weather_df.iterrows()
        }

    def predict_crop(
        self,
        crop_id: str,
        rainfall_scenario: str,
        water_availability_ratio: float,
    ) -> CropPrediction:
        """Predict yield and seasonal irrigation demand for a single crop.

        Args:
            crop_id: Crop identifier (paddy, wheat, maize, pulses, millets).
            rainfall_scenario: Rainfall scenario (normal, deficit, severe_deficit, surplus).
            water_availability_ratio: Relative water availability (e.g. 0.80 for -20%).

        Returns:
            CropPrediction schema with point estimates and uncertainty ranges.
        """
        c_id = crop_id.strip().lower()
        sc_id = rainfall_scenario.strip().lower()

        if c_id not in self.crops_lookup:
            valid_crops = list(self.crops_lookup.keys())
            raise ValueError(f"Unknown crop_id '{crop_id}'. Available crops: {valid_crops}")

        if sc_id not in self.weather_lookup:
            valid_scenarios = list(self.weather_lookup.keys())
            raise ValueError(
                f"Unknown rainfall_scenario '{rainfall_scenario}'. Available scenarios: {valid_scenarios}"
            )

        crop_info = self.crops_lookup[c_id]
        weather_info = self.weather_lookup[sc_id]

        base_yield = float(crop_info["baseline_yield_t_ha"])
        ky = float(crop_info["drought_sensitivity_ky"])
        seasonal_water = float(crop_info["seasonal_water_m3_ha"])
        crop_name = str(crop_info["crop_name"])

        stress_mult = float(weather_info["yield_stress_multiplier"])
        rain_mult = float(weather_info["effective_rainfall_multiplier"])

        # 1. Yield Prediction
        # Feature names match training DataFrame
        yield_features_df = pd.DataFrame([{
            "baseline_yield_t_ha": base_yield,
            "drought_sensitivity_ky": ky,
            "yield_stress_multiplier": stress_mult,
            "effective_rainfall_multiplier": rain_mult,
            "water_availability_ratio": float(water_availability_ratio),
        }])

        raw_yield = float(self.yield_model.predict(yield_features_df)[0])
        # Numerical stability floor for downstream mathematical programming (0.05 t/ha).
        # Note: This is a numerical floor for solver feasibility, not an agronomic harvest guarantee.
        pred_yield = float(np.round(np.maximum(0.05, raw_yield), 3))

        # 2. Water Demand Prediction
        # Independent of water_availability_ratio
        water_features_df = pd.DataFrame([{
            "seasonal_water_m3_ha": seasonal_water,
            "effective_rainfall_multiplier": rain_mult,
        }])

        raw_water = float(self.water_model.predict(water_features_df)[0])
        # Numerical stability floor: minimal seasonal irrigation floor (200 m3/ha)
        pred_water = float(np.round(np.maximum(200.0, raw_water), 1))

        # 3. Indicative Uncertainty Margins (approximate residual spread: +-1.96 * RMSE)
        # Note: These represent indicative error margins from validation on synthetic data,
        # NOT calibrated frequentist confidence intervals with proven statistical coverage.
        yield_rmse = float(self.metrics["yield_model"].get("rmse", 0.095))
        water_rmse = float(self.metrics["water_demand_model"].get("rmse", 99.0))

        yield_margin = 1.96 * yield_rmse
        water_margin = 1.96 * water_rmse

        # Lower bounds clamped to numerical floors to prevent physically invalid negative outputs
        yield_lower = float(np.round(np.maximum(0.05, pred_yield - yield_margin), 3))
        yield_upper = float(np.round(pred_yield + yield_margin, 3))

        water_lower = float(np.round(np.maximum(200.0, pred_water - water_margin), 1))
        water_upper = float(np.round(pred_water + water_margin, 1))

        return CropPrediction(
            crop_id=c_id,
            crop_name=crop_name,
            predicted_yield_t_ha=pred_yield,
            yield_range_lower=yield_lower,
            yield_range_upper=yield_upper,
            predicted_water_demand_m3_ha=pred_water,
            water_range_lower=water_lower,
            water_range_upper=water_upper,
        )

    def predict_all_crops(
        self,
        rainfall_scenario: str,
        water_availability_ratio: float,
        crops: Optional[List[str]] = None,
    ) -> BatchPredictionResponse:
        """Predict yields and water demands for multiple crops under a scenario."""
        target_crops = crops or list(self.crops_lookup.keys())
        predictions: Dict[str, CropPrediction] = {}

        for crop_id in target_crops:
            pred = self.predict_crop(
                crop_id=crop_id,
                rainfall_scenario=rainfall_scenario,
                water_availability_ratio=water_availability_ratio,
            )
            predictions[crop_id.lower()] = pred

        return BatchPredictionResponse(
            rainfall_scenario=rainfall_scenario.lower(),
            water_availability_ratio=water_availability_ratio,
            predictions=predictions,
        )
