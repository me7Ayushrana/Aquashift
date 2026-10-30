"""Base interfaces and schema contracts for agricultural and hydrological data loaders."""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import date
from pydantic import BaseModel, Field


class CropYieldRecord(BaseModel):
    """Standardized crop yield observation."""
    state: str = Field(..., description="Indian State (e.g. Punjab, Haryana)")
    district: str = Field(..., description="District name")
    year: int = Field(..., ge=1990, le=2030, description="Agricultural season year")
    season: str = Field(..., description="Kharif, Rabi, or Zaid")
    crop_id: str = Field(..., description="Normalized crop identifier")
    area_ha: float = Field(..., ge=0.0, description="Area in hectares")
    production_tonnes: float = Field(..., ge=0.0, description="Production in metric tonnes")
    yield_t_ha: float = Field(..., ge=0.0, description="Yield in metric tonnes per hectare")


class WeatherObservationRecord(BaseModel):
    """Standardized meteorological record."""
    state: str = Field(..., description="Indian State")
    district: str = Field(..., description="District name")
    observation_date: date = Field(..., description="Date of observation")
    rainfall_mm: float = Field(..., ge=0.0, description="Observed rainfall in millimeters")
    temp_min_c: float = Field(..., description="Minimum temperature in Celsius")
    temp_max_c: float = Field(..., description="Maximum temperature in Celsius")
    et0_mm_day: Optional[float] = Field(None, ge=0.0, description="Reference evapotranspiration mm/day")


class GroundwaterStatusRecord(BaseModel):
    """Standardized aquifer and groundwater status record."""
    state: str = Field(..., description="State name")
    district: str = Field(..., description="District name")
    assessment_year: int = Field(..., description="Assessment year")
    stage_of_extraction_pct: float = Field(..., ge=0.0, description="Groundwater extraction percentage (>100% is Over-Exploited)")
    category: str = Field(..., description="Safe, Semi-Critical, Critical, or Over-Exploited")
    water_table_depth_m_bgl: float = Field(..., ge=0.0, description="Water table depth in meters below ground level")


class MandiPriceRecord(BaseModel):
    """Standardized wholesale market price record."""
    state: str = Field(..., description="State name")
    district: str = Field(..., description="District name")
    market_name: str = Field(..., description="APMC Mandi name")
    crop_id: str = Field(..., description="Normalized crop identifier")
    arrival_date: date = Field(..., description="Date of market arrival")
    modal_price_inr_quintal: float = Field(..., ge=0.0, description="Modal price in INR per quintal")
    arrivals_tonnes: float = Field(..., ge=0.0, description="Market arrivals in metric tonnes")


class BaseAgriDataLoader(ABC):
    """Abstract base class for all external agricultural data loaders."""

    def __init__(self, source_name: str, base_url: str):
        self.source_name = source_name
        self.base_url = base_url

    @abstractmethod
    def validate_schema(self, raw_data: Dict[str, Any]) -> bool:
        """Validate raw incoming payload against source schema specifications."""
        pass

    @abstractmethod
    def handle_missing_data(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply missing data imputation, seasonal interpolation, or regional fallbacks."""
        pass

    @abstractmethod
    def transform_to_standard(self, raw_data: List[Dict[str, Any]]) -> List[BaseModel]:
        """Transform raw source records into normalized AquaShift domain models."""
        pass
