"""Data loader integration interface for CGWB (Central Ground Water Board)."""
from typing import Dict, Any, List
from data.loaders.base import BaseAgriDataLoader, GroundwaterStatusRecord


class CGWBDataLoader(BaseAgriDataLoader):
    """Integrates National Groundwater Assessment (INGRES) reports from CGWB."""

    def __init__(self):
        super().__init__(
            source_name="CGWB",
            base_url="https://ingres.cgwb.gov.in/api/groundwater-assessment",
        )

    def validate_schema(self, raw_data: Dict[str, Any]) -> bool:
        required = ["state", "district", "assessment_year", "stage_of_extraction", "category"]
        return all(k in raw_data for k in required)

    def handle_missing_data(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for r in records:
            if "water_table_depth_m" not in r or r["water_table_depth_m"] is None:
                # Punjab default average aquifer depth
                r["water_table_depth_m"] = 25.0
        return records

    def transform_to_standard(self, raw_data: List[Dict[str, Any]]) -> List[GroundwaterStatusRecord]:
        results = []
        for r in self.handle_missing_data(raw_data):
            results.append(
                GroundwaterStatusRecord(
                    state=str(r["state"]),
                    district=str(r["district"]),
                    assessment_year=int(r["assessment_year"]),
                    stage_of_extraction_pct=float(r["stage_of_extraction"]),
                    category=str(r["category"]),
                    water_table_depth_m_bgl=float(r["water_table_depth_m"]),
                )
            )
        return results
