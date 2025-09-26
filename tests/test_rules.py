import unittest
from datetime import datetime, timedelta

from core.model import NmonFile, NmonSeries
from core.rules import (
    cpu_sustained_high,
    excessive_emmc_writes,
    excessive_network_usage,
    memory_leak,
)


class RulesTestCase(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2024, 1, 1, 0, 0, 0)
        self.timestamps = [self.start + timedelta(minutes=i) for i in range(10)]

    def test_cpu_rule_triggers_crit(self):
        series = NmonSeries("cpu_busy_pct", self.timestamps, [95.0] * 10)
        nmon = NmonFile("test", "host", self.start, {"cpu_busy_pct": series})
        thresholds = {"cpu": {"busy_pct_warn": 70.0, "busy_pct_crit": 90.0, "sustained_minutes": 5}}
        result = cpu_sustained_high(nmon, thresholds)
        self.assertEqual(result.level, "CRIT")

    def test_memory_leak_warn(self):
        values = [1000 + i * 1500 for i in range(10)]
        series = NmonSeries("mem_active_kb", self.timestamps, values)
        nmon = NmonFile("test", "host", self.start, {"mem_active_kb": series})
        thresholds = {
            "memory_leak": {
                "series": "mem_active_kb",
                "window_minutes_min": 5,
                "slope_kb_per_min_warn": 1000,
                "slope_kb_per_min_crit": 5000,
                "r2_min": 0.5,
            }
        }
        result = memory_leak(nmon, thresholds)
        self.assertEqual(result.level, "WARN")

    def test_emmc_rule_crit(self):
        values = [6000.0] * 10
        series = NmonSeries("disk_write_kbps::mmcblk0", self.timestamps, values)
        nmon = NmonFile("test", "host", self.start, {series.name: series})
        thresholds = {
            "emmc_write": {
                "kbps_warn": 2000,
                "kbps_crit": 5000,
                "sustained_minutes": 2,
                "use_percentile95": True,
            }
        }
        result = excessive_emmc_writes(nmon, thresholds)
        self.assertEqual(result.level, "CRIT")

    def test_network_rule_warn(self):
        values = [3000.0] * 10
        series = NmonSeries("net_total_kbps", self.timestamps, values)
        nmon = NmonFile("test", "host", self.start, {series.name: series})
        thresholds = {
            "network": {
                "iface_include_regex": "^net$",
                "kbps_warn": 2000,
                "kbps_crit": 5000,
                "sustained_minutes": 3,
                "use_percentile95": True,
            }
        }
        result = excessive_network_usage(nmon, thresholds)
        self.assertEqual(result.level, "WARN")


if __name__ == "__main__":
    unittest.main()
