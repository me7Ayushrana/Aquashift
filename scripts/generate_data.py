#!/usr/bin/env python3
"""AquaShift Synthetic Agricultural Data Generator.

Generates reproducible synthetic training data for crop yield and water demand
using FAO-56 crop-water production functions calibrated to the Punjab/Haryana
paddy-wheat agricultural belt.

Physical Principles:
1. FAO-56 Yield Response: Ya / Ym = 1 - Ky * (1 - ETa / ETm)
2. Yield must not increase as water stress worsens, all else equal.
3. Yield and water demand must remain strictly non-negative.
4. Deterministic output guaranteed via fixed random seed.
"""
import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd

DEFAULT_SEED = 42
SAMPLES_PER_PAIR = 100  # 5 crops * 4 weather scenarios * 100 = 2,000 observations


def compute_fao_yield(
    baseline_yield: float,
    ky: float,
    yield_stress_mult: float,
    effective_rain_mult: float,
    water_avail_ratio: float,
    noise: float = 0.0,
) -> float:
    """Calculate crop yield using FAO-56 yield response to water deficits.

    Args:
        baseline_yield: Reference maximum potential yield (t/ha).
        ky: FAO-56 crop drought sensitivity factor (dimensionless).
        yield_stress_mult: Atmospheric/climatic stress multiplier from weather scenario.
        effective_rain_mult: Effective precipitation multiplier from weather scenario.
        water_avail_ratio: Relative irrigation water availability ratio (0.0 to 1.2+).
        noise: Controlled stochastic perturbation (additive percentage).

    Returns:
        Actual yield in tonnes per hectare (strictly non-negative).
    """
    # Potential yield adjusted for ambient seasonal weather stress
    ym = baseline_yield * yield_stress_mult

    # Relative evapotranspiration ratio ETa / ETm based on irrigation and rainfall
    # Rain provides baseline buffer: effective rain buffer factor
    rain_buffer = 0.80 + 0.20 * effective_rain_mult
    eta_etm = np.clip(water_avail_ratio * rain_buffer, 0.10, 1.0)

    # FAO-56 relative yield reduction
    relative_deficit = 1.0 - eta_etm
    yield_reduction = ky * relative_deficit
    relative_yield = np.clip(1.0 - yield_reduction, 0.05, 1.0)

    # Deterministic base yield
    base_yield = ym * relative_yield

    # Apply bounded stochastic perturbation
    noisy_yield = base_yield * (1.0 + noise)

    # Guarantee physical bounds (strictly non-negative, at least minimum biomass)
    return float(np.round(np.maximum(0.05, noisy_yield), 3))


def compute_water_demand(
    seasonal_water: float,
    effective_rain_mult: float,
    noise: float = 0.0,
) -> float:
    """Calculate seasonal crop irrigation water demand under climate scenario.

    Higher effective rainfall reduces required supplementary irrigation water.

    Args:
        seasonal_water: Baseline crop seasonal water requirement (m3/ha).
        effective_rain_mult: Effective precipitation multiplier.
        noise: Controlled stochastic perturbation.

    Returns:
        Irrigation water demand in m3/ha (strictly non-negative).
    """
    # Higher rainfall offsets supplementary irrigation demand
    rain_offset = 0.25 * (effective_rain_mult - 1.0)
    demand_factor = np.clip(1.0 - rain_offset, 0.40, 1.40)

    base_demand = seasonal_water * demand_factor
    noisy_demand = base_demand * (1.0 + noise)

    return float(np.round(np.maximum(200.0, noisy_demand), 1))


def generate_dataset(
    crops_path: Path,
    weather_path: Path,
    output_path: Path,
    seed: int = DEFAULT_SEED,
    samples_per_pair: int = SAMPLES_PER_PAIR,
) -> pd.DataFrame:
    """Generate reproducible synthetic training dataset and save to CSV."""
    rng = np.random.RandomState(seed)

    crops_df = pd.read_csv(crops_path)
    weather_df = pd.read_csv(weather_path)

    records = []

    # Sort to enforce deterministic iteration order regardless of OS file read order
    crops_sorted = crops_df.sort_values("crop_id").to_dict(orient="records")
    weather_sorted = weather_df.sort_values("scenario_id").to_dict(orient="records")

    for crop in crops_sorted:
        crop_id = crop["crop_id"]
        base_yield = float(crop["baseline_yield_t_ha"])
        seasonal_water = float(crop["seasonal_water_m3_ha"])
        ky = float(crop["drought_sensitivity_ky"])

        for weather in weather_sorted:
            scenario_id = weather["scenario_id"]
            rain_mult = float(weather["effective_rainfall_multiplier"])
            stress_mult = float(weather["yield_stress_multiplier"])

            # Uniform grid of water availability ratios from extreme deficit (0.20) to surplus (1.20)
            # with controlled jitter to span the continuous spectrum
            base_ratios = np.linspace(0.20, 1.20, samples_per_pair)
            jitter = rng.uniform(-0.02, 0.02, size=samples_per_pair)
            water_ratios = np.clip(base_ratios + jitter, 0.15, 1.30)

            # Controlled small noise for yield and water demand (+- 3%)
            yield_noises = rng.normal(0.0, 0.02, size=samples_per_pair)
            yield_noises = np.clip(yield_noises, -0.05, 0.05)

            water_noises = rng.normal(0.0, 0.015, size=samples_per_pair)
            water_noises = np.clip(water_noises, -0.04, 0.04)

            for i in range(samples_per_pair):
                w_ratio = float(water_ratios[i])
                y_noise = float(yield_noises[i])
                w_noise = float(water_noises[i])

                actual_yield = compute_fao_yield(
                    baseline_yield=base_yield,
                    ky=ky,
                    yield_stress_mult=stress_mult,
                    effective_rain_mult=rain_mult,
                    water_avail_ratio=w_ratio,
                    noise=y_noise,
                )

                water_demand = compute_water_demand(
                    seasonal_water=seasonal_water,
                    effective_rain_mult=rain_mult,
                    noise=w_noise,
                )

                records.append({
                    "crop_id": crop_id,
                    "rainfall_scenario": scenario_id,
                    "effective_rainfall_multiplier": rain_mult,
                    "water_availability_ratio": round(w_ratio, 4),
                    "drought_sensitivity_ky": ky,
                    "baseline_yield_t_ha": base_yield,
                    "seasonal_water_m3_ha": seasonal_water,
                    "actual_yield_t_ha": actual_yield,
                    "water_demand_m3_ha": water_demand,
                })

    df = pd.DataFrame(records)

    # Sort columns and rows deterministically before saving
    sort_cols = ["crop_id", "rainfall_scenario", "water_availability_ratio"]
    df = df.sort_values(sort_cols).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Write with explicit UTF-8 and standard float formatting to prevent platform float differences
    df.to_csv(output_path, index=False, float_format="%.4f")
    return df


def main():
    parser = argparse.ArgumentParser(description="AquaShift Synthetic Data Generator")
    parser.add_argument("--crops", type=Path, default=Path("data/crops.csv"), help="Path to crops.csv")
    parser.add_argument("--weather", type=Path, default=Path("data/weather_scenarios.csv"), help="Path to weather_scenarios.csv")
    parser.add_argument("--output", type=Path, default=Path("data/training_data.csv"), help="Output path for training_data.csv")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed for reproducibility")
    parser.add_argument("--samples", type=int, default=SAMPLES_PER_PAIR, help="Samples per crop-scenario pair")

    args = parser.parse_args()

    print("🌾 AquaShift Synthetic Agricultural Data Generator")
    print(f"  • Random Seed: {args.seed}")
    print(f"  • Crops file: {args.crops}")
    print(f"  • Weather file: {args.weather}")
    print(f"  • Samples per pair: {args.samples}")

    df = generate_dataset(
        crops_path=args.crops,
        weather_path=args.weather,
        output_path=args.output,
        seed=args.seed,
        samples_per_pair=args.samples,
    )

    print(f"✅ Generated {len(df)} observations saved to {args.output}")
    print("\nDataset Summary:")
    print(f"  • Total Rows: {len(df)}")
    print(f"  • Unique Crops: {df['crop_id'].nunique()} ({list(df['crop_id'].unique())})")
    print(f"  • Unique Scenarios: {df['rainfall_scenario'].nunique()} ({list(df['rainfall_scenario'].unique())})")
    print(f"  • Columns: {list(df.columns)}")
    print("\nSample records:")
    print(df.head(5).to_string())


if __name__ == "__main__":
    main()
