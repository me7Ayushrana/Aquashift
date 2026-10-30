# AquaShift — Indicative Agricultural & Hydrological Assumptions

> **Mandatory Disclaimer:**  
> **All values are indicative synthetic demo assumptions calibrated to public agricultural statistics. They are not official district-level measurements or agronomic recommendations.**

This document details every numerical assumption, calibration source, parameter domain, and limitation embedded within the AquaShift data foundation for the Punjab/Haryana-style paddy-wheat reference agricultural system.

---

## 1. Crop Assumptions (`data/crops.csv`)

| Crop ID | Crop Name | Baseline Yield (`baseline_yield_t_ha`) | Seasonal Water (`seasonal_water_m3_ha`) | Cultivation Cost (`cultivation_cost_inr_ha`) | Market/MSP Price (`price_inr_quintal`) | Caloric Value (`calories_kcal_kg`) | Drought Sensitivity (`drought_sensitivity_ky`) | Min Land Share | Max Land Share |
|---|---|---|---|---|---|---|---|---|---|
| `paddy` | Paddy (Rice) | 4.8 t/ha | 12,500 m³/ha | 38,000 ₹/ha | 2,200 ₹/quintal | 3,600 kcal/kg | 1.20 | 0.00 | 0.80 |
| `wheat` | Wheat | 4.5 t/ha | 4,500 m³/ha | 30,000 ₹/ha | 2,300 ₹/quintal | 3,400 kcal/kg | 1.00 | 0.00 | 0.80 |
| `maize` | Maize | 4.0 t/ha | 5,500 m³/ha | 26,000 ₹/ha | 2,150 ₹/quintal | 3,650 kcal/kg | 1.15 | 0.00 | 0.60 |
| `pulses` | Pulses (e.g. Moong/Gram) | 1.2 t/ha | 3,000 m³/ha | 22,000 ₹/ha | 7,500 ₹/quintal | 3,450 kcal/kg | 0.85 | 0.00 | 0.50 |
| `millets` | Millets (e.g. Bajra/Jowar) | 2.0 t/ha | 2,200 m³/ha | 18,000 ₹/ha | 2,550 ₹/quintal | 3,300 kcal/kg | 0.65 | 0.00 | 0.50 |

### Detailed Parameter Rationales & Sources:

1. **Paddy (Oryza sativa):**
   - **Baseline Yield (4.8 t/ha):** Calibrated from Punjab Directorate of Agriculture historical averages (~4.5–5.2 t/ha). Synthetic benchmark.
   - **Seasonal Water (12,500 m³/ha = 1,250 mm):** Reflects flood-irrigation water depth in northwest India based on Central Ground Water Board (CGWB) water footprint studies (typical range 12,000–15,000 m³/ha).
   - **Cultivation Cost (38,000 ₹/ha):** CACP (Commission for Agricultural Costs and Prices) comprehensive cost A2+FL estimates.
   - **Price (2,200 ₹/quintal):** Aligned with Government of India Kharif Minimum Support Price (MSP) for Common Paddy (2023–24).
   - **Calorie Density (3,600 kcal/kg):** Standard raw milled rice nutritional values (ICMR-NIN).
   - **Drought Sensitivity ($K_y = 1.20$):** FAO Irrigation and Drainage Paper 56/33; paddy exhibits high susceptibility to water deficit during flowering and panicle initiation.
   - **Land Constraints:** Min share 0.0 allows complete diversification away from paddy under extreme water crises; max share 0.80 prevents monoculture exhaustion.

2. **Wheat (Triticum aestivum):**
   - **Baseline Yield (4.5 t/ha):** Representative of irrigated Rabi wheat in Ludhiana/Karnal belts.
   - **Seasonal Water (4,500 m³/ha = 450 mm):** Reflects 4–5 crown-root and flowering irrigations under northern conditions.
   - **Cultivation Cost (30,000 ₹/ha):** CACP Rabi cost reports for Punjab.
   - **Price (2,300 ₹/quintal):** Aligned with Rabi MSP for wheat (2023–24).
   - **Calorie Density (3,400 kcal/kg):** Standard whole grain wheat nutritional density (ICMR-NIN).
   - **Drought Sensitivity ($K_y = 1.00$):** Standard FAO-56 crop coefficient representing linear yield reduction with evapotranspiration deficit.

3. **Maize (Zea mays):**
   - **Baseline Yield (4.0 t/ha):** Indicative composite hybrid maize yield.
   - **Seasonal Water (5,500 m³/ha = 550 mm):** Substantially lower water requirement than paddy, serving as a primary diversification alternative.
   - **Cultivation Cost (26,000 ₹/ha):** Moderate seed and fertilizer expenses.
   - **Price (2,150 ₹/quintal):** Kharif MSP benchmark.
   - **Drought Sensitivity ($K_y = 1.15$):** Sensitive during silking and tasseling phases.

4. **Pulses (e.g. Summer Moong / Gram):**
   - **Baseline Yield (1.2 t/ha):** Calibrated to short-duration pulse varieties.
   - **Seasonal Water (3,000 m³/ha = 300 mm):** Low water requirement; fixes atmospheric nitrogen.
   - **Cultivation Cost (22,000 ₹/ha):** Lower chemical fertilizer requirements due to rhizobial symbiosis.
   - **Price (7,500 ₹/quintal):** High-value cash return reflecting pulses MSP and domestic market demand.
   - **Drought Sensitivity ($K_y = 0.85$):** Moderate tolerance to intermittent moisture deficits.

5. **Millets (e.g. Pearl Millet / Bajra):**
   - **Baseline Yield (2.0 t/ha):** Calibrated to arid/semi-arid rainfed cultivars.
   - **Seasonal Water (2,200 m³/ha = 220 mm):** Lowest water footprint among cereal alternatives.
   - **Cultivation Cost (18,000 ₹/ha):** Low input costs.
   - **Price (2,550 ₹/quintal):** Aligned with Bajra MSP.
   - **Drought Sensitivity ($K_y = 0.65$):** Highly drought-hardy C4 photosynthetic crop with high water-use efficiency.

---

## 2. Weather Scenarios (`data/weather_scenarios.csv`)

| Scenario ID | Name | Effective Rainfall Multiplier | Yield Stress Multiplier | Description |
|---|---|---|---|---|
| `normal` | Normal | 1.00 | 1.00 | Baseline historical seasonal rainfall (approx. 500 mm Kharif / 100 mm Rabi) and average reference evapotranspiration ($ET_0$). |
| `deficit` | Deficit | 0.70 | 0.85 | 30% reduction in effective monsoon rainfall; moderate vapor pressure deficit elevation. |
| `severe_deficit` | Severe Deficit | 0.40 | 0.65 | 60% reduction in rainfall combined with heat stress ($ET_0$ spike), severe groundwater recharge drop. |
| `surplus` | Surplus | 1.25 | 1.05 | 25% surplus rainfall with soil moisture saturation benefits. |

---

## 3. FAO-56 Yield Response Model & Physics Invariants

The synthetic data generation enforces the standard FAO-56 crop-water equation:

$$\frac{Y_a}{Y_m} = 1 - K_y \times \left(1 - \frac{ET_a}{ET_m}\right)$$

Where:
- $Y_m = \text{baseline\_yield} \times \text{yield\_stress\_multiplier}$ represents the potential yield under the prevailing seasonal climate.
- $\frac{ET_a}{ET_m} = \min\left(1.0, W_{\text{avail}} \times \left(0.80 + 0.20 \times \text{effective\_rainfall\_multiplier}\right)\right)$ represents relative water satisfaction.
- **Physical Invariant 1 (Monotonicity):** Under identical crop, climate, and management conditions, $\frac{\partial Y_a}{\partial W_{\text{avail}}} \ge 0$. Worsening water stress never causes yield to increase.
- **Physical Invariant 2 (Non-Negativity):** $Y_a \ge 0.05$ t/ha (minimum salvageable stover/biomass) and $W_{\text{demand}} \ge 200.0$ m³/ha.

---

## 4. Synthetic Training Dataset Generation Parameters

- **Random Seed:** `42` (Fixed PRNG `numpy.random.RandomState(42)`).
- **Total Observations:** 2,000 rows (5 crops $\times$ 4 rainfall scenarios $\times$ 100 water availability samples).
- **Water Availability Range:** Linearly spaced from 0.20 (extreme deficit) to 1.20 (surplus) with uniform jitter $\pm 0.02$.
- **Stochastic Noise:**
  - Yield noise: Gaussian $\mathcal{N}(0, 0.02^2)$, clipped to $[-0.05, 0.05]$ ($\pm 5\%$).
  - Water demand noise: Gaussian $\mathcal{N}(0, 0.015^2)$, clipped to $[-0.04, 0.04]$ ($\pm 4\%$).
- **Reproducibility Guarantee:** SHA-256 hash verified as `965c6588376038cb4fc7ef44a44c775b887532f63936078b3dff3a68a9925c02`.

---

## 5. Reference Farm & Baseline Allocation Assumptions

For default simulator demonstrations:
- **Default Reference Farm Area:** 10.0 hectares.
- **Baseline Allocation (Paddy-heavy Punjab Model):**
  - Paddy: 7.0 ha (70% land share)
  - Wheat / Fallow / Maize: 3.0 ha (30% land share)
  - Baseline seasonal water consumption: $\approx 7.0 \times 12,500 + 3.0 \times 5,500 = 104,000\text{ m}^3$ (approx. 10,400 m³/ha average).
- **Tuned Extreme Scenario Settings:**
  - Water availability: $-80\%$ ($20,800$ m³ total budget)
  - Food target: $+10\%$
  - Income target: $+50\%$
  - Expected bottleneck hierarchy: **Water: Critical**, **Income: High**, **Food: Moderate**.

---

## 6. Limitations & Real-World Translation

1. **Indicative Calibration:** Values represent aggregated seasonal averages. Real farm yields depend on cultivar traits, sowing dates, soil types (sandy loam vs. clay), and pest incidence.
2. **Static Pricing:** Prices reflect current MSP floors. Real farm gate realizations depend on local Mandi arrivals and quality grade.
3. **No Multi-Season Carryover:** Soil moisture and aquifer drawdown are evaluated on a single-season planning horizon rather than multi-year dynamic hydrology.
4. **Simplified Synthetic Physics:** The weather multipliers and water-demand scaling formulas (`rain_offset = 0.25 * (effective_rain_mult - 1.0)`) are simplified synthetic demo assumptions designed for rapid decision-space exploration in a hackathon setting. They do not constitute a validated physical crop-water simulation (such as FAO AquaCrop, DSSAT, or APSIM) and must not be deployed for precision field irrigation scheduling.
5. **Numerical Stability Floor vs. Agronomic Guarantee:** The 0.05 t/ha lower clamp on yield is strictly a numerical stability floor to ensure feasible floating-point linear programming and avoid division-by-zero in economic ratios. It does not represent an agronomic minimum harvest guarantee. Total crop failure (0 t/ha) can occur under severe unmitigated drought.
6. **Uncertainty Error Margins:** Uncertainty bounds (`yield_range_lower/upper`, `water_range_lower/upper`) represent indicative error bounds based on validation residual root-mean-squared error spread ($\pm 1.96 \times \text{RMSE}$). They are approximate error margins on synthetic data, not empirically calibrated frequentist coverage intervals.
