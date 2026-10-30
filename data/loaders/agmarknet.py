"""Data loader integration interface for Agmarknet (Directorate of Marketing & Inspection)."""
from typing import Dict, Any, List
from datetime import datetime
from data.loaders.base import BaseAgriDataLoader, MandiPriceRecord


class AgmarknetDataLoader(BaseAgriDataLoader):
    """Integrates daily wholesale APMC mandi prices and physical arrivals."""

    def __init__(self):
        super().__init__(
            source_name="Agmarknet",
            base_url="https://agmarknet.gov.in/api/daily-prices",
        )

    def validate_schema(self, raw_data: Dict[str, Any]) -> bool:
        required = ["state", "district", "market", "commodity", "arrival_date", "modal_price"]
        return all(k in raw_data for k in required)

    def handle_missing_data(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Impute missing arrivals with 0.0 and filter out invalid non-positive prices
        valid = []
        for r in records:
            if float(r.get("modal_price", 0.0) or 0.0) > 0.0:
                if r.get("arrivals") is None:
                    r["arrivals"] = 0.0
                valid.append(r)
        return valid

    def transform_to_standard(self, raw_data: List[Dict[str, Any]]) -> List[MandiPriceRecord]:
        results = []
        for r in self.handle_missing_data(raw_data):
            arr_date = datetime.strptime(str(r["arrival_date"]), "%Y-%m-%d").date()
            results.append(
                MandiPriceRecord(
                    state=str(r["state"]),
                    district=str(r["district"]),
                    market_name=str(r["market"]),
                    crop_id=str(r["commodity"]).lower().strip(),
                    arrival_date=arr_date,
                    modal_price_inr_quintal=float(r["modal_price"]),
                    arrivals_tonnes=float(r["arrivals"]),
                )
            )
        return results
