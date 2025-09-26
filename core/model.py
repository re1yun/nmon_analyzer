"""Data models used across the NMON analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class NmonSeries:
    """Represents a single numerical time series extracted from an NMON file."""

    name: str
    timestamps: List[datetime]
    values: List[float]

    def as_dict(self) -> Dict[str, List]:
        return {
            "name": self.name,
            "timestamps": [ts.isoformat() for ts in self.timestamps],
            "values": self.values,
        }

    def is_empty(self) -> bool:
        return not self.timestamps or not self.values


@dataclass
class NmonFile:
    """Represents the structured contents of an NMON file."""

    source_path: str
    hostname: Optional[str]
    start_time: Optional[datetime]
    series: Dict[str, NmonSeries] = field(default_factory=dict)

    def get_series(self, key: str) -> Optional[NmonSeries]:
        return self.series.get(key)


@dataclass
class CheckResult:
    """Result from executing a single diagnostic rule."""

    rule_name: str
    level: str
    summary: str
    details: Dict[str, object] = field(default_factory=dict)
    evidence: Dict[str, object] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class FileAnalysis:
    """Full analysis output for a single NMON file."""

    file_id: str
    source_path: str
    hostname: Optional[str]
    start_time: Optional[datetime]
    checks: List[CheckResult]
    overall: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "file_id": self.file_id,
            "source": self.source_path,
            "hostname": self.hostname,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "overall": self.overall,
            "checks": [
                {
                    "rule": check.rule_name,
                    "level": check.level,
                    "summary": check.summary,
                    "details": check.details,
                    "evidence": check.evidence,
                    "metrics": check.metrics,
                }
                for check in self.checks
            ],
        }


@dataclass
class BatchSummary:
    """Aggregated summary for a batch upload."""

    total_files: int
    ok_files: int
    warn_files: int
    crit_files: int
    warn_checks: int
    crit_checks: int

    def as_dict(self) -> Dict[str, int]:
        return {
            "total_files": self.total_files,
            "ok_files": self.ok_files,
            "warn_files": self.warn_files,
            "crit_files": self.crit_files,
            "warn_checks": self.warn_checks,
            "crit_checks": self.crit_checks,
        }
