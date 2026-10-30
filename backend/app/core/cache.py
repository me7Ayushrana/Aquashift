"""Thread-safe LRU cache for deterministic scenario optimization and prediction results.

Ensures repeated requests with identical input parameters return instantaneously
without re-running solver or model inference, while avoiding stale results.
"""
from collections import OrderedDict
import copy
import hashlib
import json
import threading
from typing import Any, Optional


class ScenarioCache:
    """Thread-safe in-memory LRU cache with caller immutability."""

    def __init__(self, maxsize: int = 256):
        self.maxsize = maxsize
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def make_key(prefix: str, payload: Any) -> str:
        """Create a deterministic hash key from prefix and dictionary or Pydantic model."""
        if hasattr(payload, "model_dump"):
            raw = payload.model_dump()
        elif isinstance(payload, dict):
            raw = payload
        else:
            raw = str(payload)

        # Normalize selected_crops or crops list order if present in dict
        if isinstance(raw, dict):
            raw = dict(raw)
            if "selected_crops" in raw and isinstance(raw["selected_crops"], list):
                raw["selected_crops"] = sorted(raw["selected_crops"])
            if "crops" in raw and isinstance(raw["crops"], list):
                raw["crops"] = sorted(raw["crops"])

        serialized = json.dumps(raw, sort_keys=True, default=str)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"{prefix}:{digest}"

    def get(self, key: str) -> Optional[Any]:
        """Retrieve cached value if present, moving it to MRU and returning an isolated deep copy."""
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return copy.deepcopy(self._cache[key])

    def set(self, key: str, value: Any) -> None:
        """Store deep copy of value in cache, evicting LRU item if capacity is exceeded."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = copy.deepcopy(value)
            if len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        """Purge all entries from cache."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """Return current number of cached items."""
        with self._lock:
            return len(self._cache)


# Global singleton cache instance
scenario_cache = ScenarioCache(maxsize=256)
