"""Data loader integration interface for IMD (India Meteorological Department)."""
from typing import Dict, Any, List
from datetime import datetime
from data.loaders.base import BaseAgriDataLoader, WeatherObservationRecord


class IMDDataLoader(BaseAgriDataLoader):
    """Integrates gridded daily rainfall and temperature observations from IMD."""

    def __init__(self):
        super().__init__(
            source_name="IMD",
            base_url="https://mausam.imd.gov.in/api/gridded-weather",
        )

    def validate_schema(self, raw_data: Dict[str, Any]) -> bool:
        required = ["district", "date", "rainfall_actual_mm", "temp_max", "temp_min"]
        return all(k in raw_data for k in required)

    def handle_missing_data(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Impute missing rainfall with 0.0 (dry day) and temperature with seasonal normal
        for r in records:
            if r.get("rainfall_actual_mm") is None:
                r["rainfall_actual_mm"] = 0.0
            if r.get("temp_max") is None:
                r["temp_max"] = 32.0
            if r.get("temp_min") is None:
                r["temp_min"] = 18.0
        return records

    def transform_to_standard(self, raw_data: List[Dict[str, Any]]) -> List[WeatherObservationRecord]:
        results = []
        for r in self.handle_missing_data(raw_data):
            obs_date = datetime.strptime(str(r["date"]), "%Y-%m-%d").date()
            results.append(
                WeatherObservationRecord(
                    state=str(r.get("state", "Punjab")),
                    district=str(r["district"]),
                    observation_date=obs_date,
                    rainfall_mm=float(r["rainfall_actual_mm"]),
                    temp_min_c=float(r["temp_min"]),
                    temp_max_c=float(r["temp_max"]),
                    et0_mm_day=float(r.get("et0", 4.5)),
                )
            )
        return results
