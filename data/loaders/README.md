# External Agricultural & Hydrological Data Loaders

This directory contains typed integration interfaces and contract schemas designed to plug in official, empirical data sources to replace or calibrate AquaShift's synthetic demo priors.

> **Zero Live Network Dependencies:**  
> These interfaces document schemas, units, missing-value protocols, and transformation pipelines. They do not execute live external HTTP requests during hackathon evaluation.

---

## 1. Supported Data Sources & Contracts

| Source | Organization | Focus Area | Standard Contract Model | Key Fields & Units |
|---|---|---|---|---|
| **data.gov.in** | Open Government Data Platform India | District Area, Production, Yield (APY) | `CropYieldRecord` | Area (`ha`), Production (`tonnes`), Yield (`t/ha`) |
| **ICAR** | Indian Council of Agricultural Research | Agronomic coefficients & crop water | `ICARCropParameterRecord` | $K_c$ stages, $K_y$ drought sensitivity, Duration (`days`), Water (`mm`) |
| **IMD** | India Meteorological Department | Gridded daily precipitation & temperature | `WeatherObservationRecord` | Rainfall (`mm`), $T_{\min}, T_{\max}$ (`°C`), $ET_0$ (`mm/day`) |
| **CGWB** | Central Ground Water Board | Aquifer extraction & water table dynamics | `GroundwaterStatusRecord` | Extraction stage (`%`), Category (`Over-Exploited/Critical`), Depth (`m bgl`) |
| **Agmarknet** | Directorate of Marketing & Inspection | Daily wholesale APMC market arrivals & prices | `MandiPriceRecord` | Modal price (`₹/quintal`), Arrivals (`tonnes`) |
| **APEDA** | Agri & Processed Food Export Dev Authority | Export benchmarks & international trade | `APEDAExportBenchmarkRecord` | Export volume (`MT`), Realization (`USD/MT`), FOB (`₹/quintal`) |

---

## 2. Missing-Data & Calibration Policies

1. **Production & Yield Discrepancies:**
   - Where official production is unrecorded but area is non-zero, loaders apply a 3-year district rolling median yield before generating fallback estimates.
2. **Rainfall & Meteorological Gaps:**
   - Missing daily rainfall readings are imputed as 0.0 mm (dry-day assumption). Temperature gaps fall back to 30-year IMD gridded climatological normals.
3. **Mandi Price Outliers:**
   - Observations with non-positive prices or values exceeding $3\times$ the interquartile range (IQR) are flagged and excluded to prevent market shock distortions in net income calculation.
4. **Groundwater Status Fallbacks:**
   - In unmonitored blocks, stage of extraction defaults to state-level block averages from CGWB's latest National Compilation on Dynamic Ground Water Resources of India.
