import unittest
from pathlib import Path

from core.parser import parse_nmon
from core.utils import infer_sampling_minutes


class ParserTestCase(unittest.TestCase):
    def setUp(self):
        self.sample_path = Path(__file__).parent / "sample_small.nmon"

    def test_cpu_series_parsed(self):
        nmon = parse_nmon(self.sample_path)
        cpu = nmon.get_series("cpu_busy_pct")
        self.assertIsNotNone(cpu)
        self.assertEqual(len(cpu.values), 2)
        self.assertAlmostEqual(cpu.values[0], 15.0)
        self.assertAlmostEqual(cpu.values[1], 25.0)

    def test_memory_series(self):
        nmon = parse_nmon(self.sample_path)
        mem = nmon.get_series("mem_active_kb")
        self.assertIsNotNone(mem)
        self.assertEqual(mem.values[0], 1000.0)

    def test_disk_series(self):
        nmon = parse_nmon(self.sample_path)
        disk = nmon.get_series("disk_write_kbps::mmcblk0")
        self.assertIsNotNone(disk)
        self.assertEqual(disk.values, [150.0, 200.0])

    def test_network_total(self):
        nmon = parse_nmon(self.sample_path)
        net = nmon.get_series("net_total_kbps")
        self.assertIsNotNone(net)
        self.assertEqual(net.values, [180.0, 210.0])

    def test_sampling_interval(self):
        nmon = parse_nmon(self.sample_path)
        cpu = nmon.get_series("cpu_busy_pct")
        interval = infer_sampling_minutes(cpu.timestamps)
        self.assertAlmostEqual(interval, 1.0)


if __name__ == "__main__":
    unittest.main()
