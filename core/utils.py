"""Utility helpers used by the NMON analyzer."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import List, Sequence

import math


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def infer_sampling_minutes(timestamps: Sequence[datetime]) -> float:
    if len(timestamps) < 2:
        return 0.0
    deltas = [
        (b - a).total_seconds() / 60.0
        for a, b in zip(timestamps[:-1], timestamps[1:])
        if b > a
    ]
    if not deltas:
        return 0.0
    return float(median(deltas))


def rolling_mean(values: Sequence[float], window: int) -> List[float]:
    if window <= 1:
        return list(values)
    if len(values) < window:
        return [float("nan")] * len(values)
    cumsum = [0.0]
    total = 0.0
    for value in values:
        total += value if value is not None else 0.0
        cumsum.append(total)
    result = []
    for idx in range(window, len(cumsum)):
        window_sum = cumsum[idx] - cumsum[idx - window]
        result.append(window_sum / window)
    pad = [float("nan")] * (window - 1)
    return pad + result


def safe_percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return float("nan")
    data = sorted(values)
    if not data:
        return float("nan")
    k = (len(data) - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(data[int(k)])
    d0 = data[f] * (c - k)
    d1 = data[c] * (k - f)
    return float(d0 + d1)


def linear_regression(series: Sequence[float], timestamps: Sequence[datetime]):
    if len(series) < 2 or len(series) != len(timestamps):
        return None
    x = [(ts - timestamps[0]).total_seconds() / 60.0 for ts in timestamps]
    y = list(series)
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    ss_xy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    ss_xx = sum((xi - mean_x) ** 2 for xi in x)
    ss_yy = sum((yi - mean_y) ** 2 for yi in y)
    slope = ss_xy / ss_xx if ss_xx else 0.0
    intercept = mean_y - slope * mean_x
    rvalue = ss_xy / math.sqrt(ss_xx * ss_yy) if ss_xx and ss_yy else 0.0
    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "rvalue": float(rvalue),
        "pvalue": 0.0,
        "stderr": 0.0,
    }


def downsample_series(
    timestamps: Sequence[datetime],
    values: Sequence[float],
    max_points: int = 3000,
) -> dict:
    if len(timestamps) <= max_points:
        return {
            "timestamps": [ts.isoformat() for ts in timestamps],
            "values": list(values),
        }
    step = max(1, len(timestamps) // max_points)
    return {
        "timestamps": [ts.isoformat() for ts in timestamps[::step]],
        "values": list(values[::step]),
    }


def now_local() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def dataclass_to_dict(obj) -> dict:
    return asdict(obj)
