"""NMON parser implementation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .model import NmonFile, NmonSeries


_TIME_FORMATS = [
    ("%H:%M:%S", "%d-%b-%Y"),
    ("%H:%M:%S", "%Y-%m-%d"),
    ("%H:%M:%S", "%m/%d/%Y"),
]


def _parse_timestamp(label: str, time_str: str, date_str: str) -> Optional[datetime]:
    for time_fmt, date_fmt in _TIME_FORMATS:
        try:
            dt = datetime.strptime(f"{date_str} {time_str}", f"{date_fmt} {time_fmt}")
            return dt
        except ValueError:
            continue
    return None


def _as_float(value: str) -> Optional[float]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    value = value.replace(",", "")
    try:
        return float(value)
    except ValueError:
        return None


class NmonParser:
    """Parses NMON formatted files into structured series."""

    def __init__(self) -> None:
        self.headers: Dict[str, List[str]] = {}
        self.timestamp_labels: Dict[str, datetime] = {}
        self.hostname: Optional[str] = None
        self.start_time: Optional[datetime] = None
        self.cpu_rows: List[Tuple[datetime, List[str]]] = []
        self.mem_rows: List[Tuple[datetime, List[str]]] = []
        self.disk_rows: List[Tuple[datetime, List[str]]] = []
        self.net_rows: List[Tuple[datetime, List[str]]] = []

    def feed_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        parts = [part.strip() for part in line.split(",")]
        key = parts[0]
        if key == "AAA" and len(parts) >= 3:
            label = parts[1].lower()
            if label in {"hostname", "host"}:
                self.hostname = parts[2]
        elif key == "BBB" and len(parts) >= 3:
            label = parts[1].lower()
            if label == "date" and not self.start_time:
                try:
                    self.start_time = datetime.strptime(parts[2], "%d-%b-%Y")
                except ValueError:
                    self.start_time = None
        elif key == "ZZZZ" and len(parts) >= 4:
            label = parts[1]
            time_str = parts[2]
            date_str = parts[3]
            dt = _parse_timestamp(label, time_str, date_str)
            if dt is not None:
                if self.start_time is None:
                    self.start_time = dt
                self.timestamp_labels[label] = dt
        else:
            if len(parts) > 1 and not parts[1].startswith("T"):
                self.headers[key] = parts[1:]
                return
            if len(parts) > 1 and parts[1].startswith("T"):
                label = parts[1]
                dt = self.timestamp_labels.get(label)
                if not dt:
                    return
                payload = parts[2:]
                if key.startswith("CPU_ALL") or key.startswith("CPU_TOT"):
                    self.cpu_rows.append((dt, payload))
                elif key == "MEM":
                    self.mem_rows.append((dt, payload))
                elif key in {"DISKWRITE", "DISKXFER"}:
                    self.disk_rows.append((dt, payload))
                elif key in {"NET", "NETPACK"}:
                    self.net_rows.append((dt, payload))

    def to_nmon_file(self, source_path: str) -> NmonFile:
        series: Dict[str, NmonSeries] = {}
        if self.cpu_rows:
            timestamps = [row[0] for row in self.cpu_rows]
            idle_idx = None
            header = self.headers.get("CPU_ALL", self.headers.get("CPU_TOT", []))
            if header:
                for idx, name in enumerate(header):
                    if "idle" in name.lower():
                        idle_idx = idx
                        break
            values = []
            for _, payload in self.cpu_rows:
                idle_val = None
                if idle_idx is not None and idle_idx < len(payload):
                    idle_val = _as_float(payload[idle_idx])
                elif payload:
                    idle_val = _as_float(payload[-1])
                values.append(100.0 - idle_val if idle_val is not None else float("nan"))
            series["cpu_busy_pct"] = NmonSeries(
                name="cpu_busy_pct", timestamps=timestamps, values=values
            )
        if self.mem_rows:
            timestamps = [row[0] for row in self.mem_rows]
            header = [h.lower() for h in self.headers.get("MEM", [])]
            active_idx = None
            used_idx = None
            free_idx = None
            for idx, name in enumerate(header):
                if active_idx is None and "active" in name:
                    active_idx = idx
                if used_idx is None and "used" in name and "swap" not in name:
                    used_idx = idx
                if free_idx is None and "free" in name and "swap" not in name:
                    free_idx = idx
            active_vals = []
            used_vals = []
            free_vals = []
            for _, payload in self.mem_rows:
                def get(idx):
                    if idx is None or idx >= len(payload):
                        return float("nan")
                    val = _as_float(payload[idx])
                    return val if val is not None else float("nan")

                active_vals.append(get(active_idx))
                used_vals.append(get(used_idx))
                free_vals.append(get(free_idx))
            series["mem_active_kb"] = NmonSeries(
                name="mem_active_kb", timestamps=timestamps, values=active_vals
            )
            series["mem_used_kb"] = NmonSeries(
                name="mem_used_kb", timestamps=timestamps, values=used_vals
            )
            series["mem_free_kb"] = NmonSeries(
                name="mem_free_kb", timestamps=timestamps, values=free_vals
            )
        if self.disk_rows:
            device_points: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
            for dt, payload in self.disk_rows:
                for idx in range(0, len(payload), 2):
                    device = payload[idx]
                    value = _as_float(payload[idx + 1]) if idx + 1 < len(payload) else None
                    if device and value is not None:
                        device_points[device].append((dt, value))
            for device, points in device_points.items():
                points.sort(key=lambda item: item[0])
                timestamps = [ts for ts, _ in points]
                values = [val for _, val in points]
                series_name = f"disk_write_kbps::{device}"
                series[series_name] = NmonSeries(
                    name=series_name, timestamps=timestamps, values=values
                )
        if self.net_rows:
            iface_rx: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
            iface_tx: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
            totals: Dict[datetime, float] = defaultdict(float)
            for dt, payload in self.net_rows:
                step = 3 if len(payload) % 3 == 0 else 2
                for idx in range(0, len(payload), step):
                    iface = payload[idx]
                    rx = _as_float(payload[idx + 1]) if idx + 1 < len(payload) else None
                    tx = _as_float(payload[idx + 2]) if idx + 2 < len(payload) else None
                    if iface:
                        if rx is not None:
                            iface_rx[iface].append((dt, rx))
                            totals[dt] += rx
                        if tx is not None:
                            iface_tx[iface].append((dt, tx))
                            totals[dt] += tx
            for iface, points in iface_rx.items():
                points.sort(key=lambda item: item[0])
                timestamps = [ts for ts, _ in points]
                values = [val for _, val in points]
                name = f"net_rx_kbps::{iface}"
                series[name] = NmonSeries(name=name, timestamps=timestamps, values=values)
            for iface, points in iface_tx.items():
                points.sort(key=lambda item: item[0])
                timestamps = [ts for ts, _ in points]
                values = [val for _, val in points]
                name = f"net_tx_kbps::{iface}"
                series[name] = NmonSeries(name=name, timestamps=timestamps, values=values)
            if totals:
                timestamps = sorted(totals)
                values = [totals[ts] for ts in timestamps]
                series["net_total_kbps"] = NmonSeries(
                    name="net_total_kbps", timestamps=timestamps, values=values
                )
        return NmonFile(
            source_path=source_path,
            hostname=self.hostname,
            start_time=self.start_time,
            series=series,
        )


def parse_nmon(path: str | Path) -> NmonFile:
    parser = NmonParser()
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            parser.feed_line(line)
    return parser.to_nmon_file(str(path))
