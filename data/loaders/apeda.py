"""Data loader integration interface for APEDA (Agricultural & Processed Food Products Export Development Authority)."""
from typing import Dict, Any, List
from pydantic import BaseModel
from data.loaders.base import BaseAgriDataLoader


class APEDAExportBenchmarkRecord(BaseModel):
    """Export demand, international unit realization, and export price premium."""
    product_category: str
    destination_country: str
    export_quantity_metric_tonnes: float
    unit_value_usd_per_tonne: float
    fob_inr_per_quintal: float


class APEDADataLoader(BaseAgriDataLoader):
    """Integrates agri-export statistics and international benchmark realizations."""

    def __init__(self):
        super().__init__(
            source_name="APEDA",
            base_url="https://apeda.gov.in/api/export-statistics",
        )

    def validate_schema(self, raw_data: Dict[str, Any]) -> bool:
        required = ["category", "country", "quantity_mt", "unit_val_usd"]
        return all(k in raw_data for k in required)

    def handle_missing_data(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [r for r in records if float(r.get("quantity_mt", 0.0) or 0.0) >= 0.0]

    def transform_to_standard(self, raw_data: List[Dict[str, Any]]) -> List[APEDAExportBenchmarkRecord]:
        results = []
        usd_to_inr = 83.5
        for r in self.handle_missing_data(raw_data):
            unit_usd = float(r["unit_val_usd"])
            fob_quintal = (unit_usd * usd_to_inr) / 10.0  # 1 tonne = 10 quintals
            results.append(
                APEDAExportBenchmarkRecord(
                    product_category=str(r["category"]),
                    destination_country=str(r["country"]),
                    export_quantity_metric_tonnes=float(r["quantity_mt"]),
                    unit_value_usd_per_tonne=unit_usd,
                    fob_inr_per_quintal=round(fob_quintal, 2),
                )
            )
        return results
