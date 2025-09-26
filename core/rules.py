"""Fault detection rules for NMON analyses."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Dict, List, Tuple

from .model import CheckResult, NmonFile, NmonSeries
from .utils import (
    infer_sampling_minutes,
    linear_regression,
    rolling_mean,
    safe_percentile,
)


_LEVEL_ORDER = {"OK": 0, "WARN": 1, "CRIT": 2}


def _series_or_none(nmon_file: NmonFile, name: str) -> NmonSeries | None:
    series = nmon_file.get_series(name)
    if series and not series.is_empty():
        return series
    return None


def cpu_sustained_high(nmon_file: NmonFile, thresholds: Dict) -> CheckResult:
    config = thresholds.get("cpu", {})
    series = _series_or_none(nmon_file, "cpu_busy_pct")
    if not series:
        return CheckResult(
            rule_name="cpu_sustained_high",
            level="OK",
            summary="CPU busy series missing",
            details={"missing_series": True},
        )
    sampling_minutes = infer_sampling_minutes(series.timestamps) or 1.0
    window_points = max(1, int(round(config.get("sustained_minutes", 5) / sampling_minutes)))
    averages = rolling_mean(series.values, window_points)
    warn_threshold = config.get("busy_pct_warn", 75.0)
    crit_threshold = config.get("busy_pct_crit", 90.0)
    warn_window = _first_window_exceedance(averages, series.timestamps, warn_threshold, window_points)
    crit_window = _first_window_exceedance(averages, series.timestamps, crit_threshold, window_points)
    level = "OK"
    evidence = {}
    if crit_window:
        level = "CRIT"
        evidence = _window_to_evidence(crit_window)
    elif warn_window:
        level = "WARN"
        evidence = _window_to_evidence(warn_window)
    valid = [val for val in averages if not math.isnan(val)]
    max_rolling = max(valid) if valid else float("nan")
    summary = (
        f"Max rolling CPU busy {max_rolling:.1f}%" if valid else "No CPU data"
    )
    return CheckResult(
        rule_name="cpu_sustained_high",
        level=level,
        summary=summary,
        evidence=evidence,
        metrics={"max_rolling_busy_pct": max_rolling},
    )


def memory_leak(nmon_file: NmonFile, thresholds: Dict) -> CheckResult:
    config = thresholds.get("memory_leak", {})
    series_name = config.get("series", "mem_active_kb")
    series = _series_or_none(nmon_file, series_name)
    if not series:
        return CheckResult(
            rule_name="memory_leak",
            level="OK",
            summary="Memory series missing",
            details={"missing_series": True},
        )
    sampling_minutes = infer_sampling_minutes(series.timestamps) or 1.0
    window_minutes_min = config.get("window_minutes_min", 20)
    if len(series.timestamps) * sampling_minutes < window_minutes_min:
        return CheckResult(
            rule_name="memory_leak",
            level="OK",
            summary="Not enough data for regression",
            details={"insufficient_points": True},
        )
    regression = linear_regression(series.values, series.timestamps)
    if not regression:
        return CheckResult(
            rule_name="memory_leak",
            level="OK",
            summary="Regression unavailable",
        )
    slope = regression["slope"]
    r2 = regression["rvalue"] ** 2
    warn_threshold = config.get("slope_kb_per_min_warn", 1000)
    crit_threshold = config.get("slope_kb_per_min_crit", 3000)
    r2_min = config.get("r2_min", 0.7)
    level = "OK"
    evidence = {}
    if slope >= crit_threshold and r2 >= r2_min:
        level = "CRIT"
        evidence = {"window_start": series.timestamps[0].isoformat(), "window_end": series.timestamps[-1].isoformat()}
    elif slope >= warn_threshold and r2 >= r2_min:
        level = "WARN"
        evidence = {"window_start": series.timestamps[0].isoformat(), "window_end": series.timestamps[-1].isoformat()}
    summary = f"Slope {slope:.1f} KB/min (R²={r2:.2f})"
    return CheckResult(
        rule_name="memory_leak",
        level=level,
        summary=summary,
        evidence=evidence,
        metrics={"slope_kb_per_min": float(slope), "r2": float(r2)},
    )


def excessive_emmc_writes(nmon_file: NmonFile, thresholds: Dict) -> CheckResult:
    config = thresholds.get("emmc_write", {})
    regex = re.compile(config.get("device_regex", "^(mmcblk\\d+|mmc\\d+)$"))
    device_series = [
        series
        for name, series in nmon_file.series.items()
        if name.startswith("disk_write_kbps::") and regex.search(name.split("::", 1)[1])
    ]
    if not device_series:
        return CheckResult(
            rule_name="excessive_emmc_writes",
            level="OK",
            summary="No eMMC devices found",
            details={"missing_devices": True},
        )
    aggregate = _combine_series(device_series)
    return _bandwidth_rule(
        rule_name="excessive_emmc_writes",
        values=aggregate,
        timestamps=device_series[0].timestamps,
        thresholds=config,
    )


def excessive_network_usage(nmon_file: NmonFile, thresholds: Dict) -> CheckResult:
    config = thresholds.get("network", {})
    regex = re.compile(config.get("iface_include_regex", "^(eth\\d+|enp\\S+|wlan\\d+)$"))
    include_rx = []
    include_tx = []
    for name, series in nmon_file.series.items():
        if name.startswith("net_rx_kbps::"):
            iface = name.split("::", 1)[1]
            if regex.search(iface):
                include_rx.append(series)
        elif name.startswith("net_tx_kbps::"):
            iface = name.split("::", 1)[1]
            if regex.search(iface):
                include_tx.append(series)
    if not include_rx and not include_tx:
        total = nmon_file.get_series("net_total_kbps")
        if not total:
            return CheckResult(
                rule_name="excessive_network_usage",
                level="OK",
                summary="No network series found",
                details={"missing_series": True},
            )
        aggregate_values = total.values
        timestamps = total.timestamps
    else:
        sum_map = defaultdict(float)
        timestamps = include_rx[0].timestamps if include_rx else include_tx[0].timestamps
        for series in include_rx + include_tx:
            for ts, value in zip(series.timestamps, series.values):
                sum_map[ts] += value
        aggregate_values = [sum_map[ts] for ts in timestamps]
    return _bandwidth_rule(
        rule_name="excessive_network_usage",
        values=aggregate_values,
        timestamps=timestamps,
        thresholds=config,
    )


def _combine_series(series_list: List[NmonSeries]) -> List[float]:
    if not series_list:
        return []
    timestamps = series_list[0].timestamps
    totals = [0.0] * len(timestamps)
    for series in series_list:
        for idx, value in enumerate(series.values):
            if idx < len(totals):
                totals[idx] += value if value is not None else 0.0
    return totals


def _bandwidth_rule(rule_name: str, values: List[float], timestamps, thresholds: Dict) -> CheckResult:
    if not values or not timestamps:
        return CheckResult(
            rule_name=rule_name,
            level="OK",
            summary="No data available",
            details={"missing_series": True},
        )
    sustained_minutes = thresholds.get("sustained_minutes", 5)
    sampling_minutes = infer_sampling_minutes(timestamps) or 1.0
    window_points = max(1, int(round(sustained_minutes / sampling_minutes)))
    averages = rolling_mean(values, window_points)
    warn_threshold = thresholds.get("kbps_warn", 0)
    crit_threshold = thresholds.get("kbps_crit", 0)
    warn_window = _first_window_exceedance(averages, timestamps, warn_threshold, window_points)
    crit_window = _first_window_exceedance(averages, timestamps, crit_threshold, window_points)
    percentile_95 = safe_percentile(values, 95) if thresholds.get("use_percentile95", False) else float("nan")
    level = "OK"
    evidence = {}
    if crit_window or (not math.isnan(percentile_95) and percentile_95 >= crit_threshold):
        level = "CRIT"
        if crit_window:
            evidence = _window_to_evidence(crit_window)
    elif warn_window or (not math.isnan(percentile_95) and percentile_95 >= warn_threshold):
        level = "WARN"
        if warn_window:
            evidence = _window_to_evidence(warn_window)
    summary = f"p95 {percentile_95:.1f} KB/s"
    return CheckResult(
        rule_name=rule_name,
        level=level,
        summary=summary,
        evidence=evidence,
        metrics={"p95_kbps": float(percentile_95)},
    )


def _first_window_exceedance(averages, timestamps, threshold, window_points):
    for idx, value in enumerate(averages):
        if math.isnan(value) or value < threshold:
            continue
        start_idx = max(0, idx - window_points + 1)
        if not timestamps:
            return (start_idx, idx, None, None, float(value))
        start_ts = timestamps[start_idx] if start_idx < len(timestamps) else None
        end_ts = timestamps[idx] if idx < len(timestamps) else None
        return (start_idx, idx, start_ts, end_ts, float(value))
    return None


def _window_to_evidence(window) -> Dict[str, str]:
    start_idx, end_idx, start_ts, end_ts, value = window
    evidence = {"window_start_index": start_idx, "window_end_index": end_idx, "window_average": value}
    if start_ts:
        evidence["window_start"] = start_ts.isoformat()
    if end_ts:
        evidence["window_end"] = end_ts.isoformat()
    return evidence


ALL_RULES = [
    cpu_sustained_high,
    memory_leak,
    excessive_emmc_writes,
    excessive_network_usage,
]


def run_all_rules(nmon_file: NmonFile, thresholds: Dict) -> Tuple[List[CheckResult], str]:
    results: List[CheckResult] = []
    for rule in ALL_RULES:
        results.append(rule(nmon_file, thresholds))
    overall = "OK"
    for result in results:
        level = result.level
        if _LEVEL_ORDER[level] > _LEVEL_ORDER[overall]:
            overall = level
    return results, overall
