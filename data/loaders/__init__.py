"""Data loaders package providing typed integration interfaces for external public datasets."""
from data.loaders.base import (
    BaseAgriDataLoader,
    CropYieldRecord,
    WeatherObservationRecord,
    GroundwaterStatusRecord,
    MandiPriceRecord,
)
from data.loaders.data_gov_in import DataGovInLoader
from data.loaders.icar import ICARDataLoader, ICARCropParameterRecord
from data.loaders.imd import IMDDataLoader
from data.loaders.cgwb import CGWBDataLoader
from data.loaders.agmarknet import AgmarknetDataLoader
from data.loaders.apeda import APEDADataLoader, APEDAExportBenchmarkRecord

__all__ = [
    "BaseAgriDataLoader",
    "CropYieldRecord",
    "WeatherObservationRecord",
    "GroundwaterStatusRecord",
    "MandiPriceRecord",
    "DataGovInLoader",
    "ICARDataLoader",
    "ICARCropParameterRecord",
    "IMDDataLoader",
    "CGWBDataLoader",
    "AgmarknetDataLoader",
    "APEDADataLoader",
    "APEDAExportBenchmarkRecord",
]
