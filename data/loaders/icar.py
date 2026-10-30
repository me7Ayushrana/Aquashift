"""Data loader integration interface for ICAR (Indian Council of Agricultural Research)."""
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from data.loaders.base import BaseAgriDataLoader


class ICARCropParameterRecord(BaseModel):
    """Agronomic crop coefficient specifications from ICAR research stations."""
    crop_id: str
    cultivar_group: str
    growing_days: int
    kc_initial: float
    kc_mid: float
    kc_end: float
    ky_seasonal: float = Field(..., description="FAO/ICAR seasonal drought sensitivity factor")
    optimal_water_mm: float


class ICARDataLoader(BaseAgriDataLoader):
    """Integrates ICAR Package of Practices and agronomic crop coefficients."""

    def __init__(self):
        super().__init__(
            source_name="ICAR",
            base_url="https://icar.org.in/agronomic-coefficients",
        )

    def validate_schema(self, raw_data: Dict[str, Any]) -> bool:
        required = ["crop_name", "kc_mid", "seasonal_water_mm", "ky_factor"]
        return all(k in raw_data for k in required)

    def handle_missing_data(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for r in records:
            if "ky_factor" not in r or r["ky_factor"] is None:
                r["ky_factor"] = 1.0  # Conservative default linear sensitivity
        return records

    def transform_to_standard(self, raw_data: List[Dict[str, Any]]) -> List[ICARCropParameterRecord]:
        results = []
        for r in self.handle_missing_data(raw_data):
            results.append(
                ICARCropParameterRecord(
                    crop_id=str(r["crop_name"]).lower().strip(),
                    cultivar_group=str(r.get("cultivar", "Standard")),
                    growing_days=int(r.get("duration_days", 120)),
                    kc_initial=float(r.get("kc_ini", 0.4)),
                    kc_mid=float(r["kc_mid"]),
                    kc_end=float(r.get("kc_end", 0.5)),
                    ky_seasonal=float(r["ky_factor"]),
                    optimal_water_mm=float(r["seasonal_water_mm"]),
                )
            )
        return results
