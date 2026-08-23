from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class LicensePolicy(Protocol):
    """Single decision point that a future subscription service can replace."""

    def is_enabled(self, license_key: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class StaticLicensePolicy:
    enabled_keys: frozenset[str] = field(
        default_factory=lambda: frozenset({"concretos", "prefabricados"})
    )

    def is_enabled(self, license_key: str) -> bool:
        return license_key in self.enabled_keys
