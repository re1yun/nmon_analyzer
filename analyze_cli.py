"""Command line batch analyzer for NMON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from core import AnalysisStore, parse_nmon, run_all_rules
from core.model import FileAnalysis


def load_thresholds(config_path: Path) -> dict:
    with open(config_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def analyze_file(path: Path, thresholds: dict) -> FileAnalysis:
    nmon = parse_nmon(path)
    checks, overall = run_all_rules(nmon, thresholds)
    file_id = path.stem
    return FileAnalysis(
        file_id=file_id,
        source_path=str(path),
        hostname=nmon.hostname,
        start_time=nmon.start_time,
        checks=checks,
        overall=overall,
    )


def analyze_directory(input_dir: Path, output_dir: Path, thresholds_path: Path) -> None:
    thresholds = load_thresholds(thresholds_path)
    store = AnalysisStore(output_dir)
    files = sorted(path for path in input_dir.glob("*.nmon"))
    total = len(files)
    ok_files = warn_files = crit_files = warn_checks = crit_checks = 0
    for path in files:
        analysis = analyze_file(path, thresholds)
        warn_checks += sum(1 for check in analysis.checks if check.level == "WARN")
        crit_checks += sum(1 for check in analysis.checks if check.level == "CRIT")
        if analysis.overall == "CRIT":
            crit_files += 1
        elif analysis.overall == "WARN":
            warn_files += 1
        else:
            ok_files += 1
        store.save_analysis(analysis, path)
    summary = (
        f"TOTAL: files={total} | OK={ok_files} | CRIT(files)={crit_files} | "
        f"WARN(files)={warn_files} | WARN(checks)={warn_checks} | CRIT(checks)={crit_checks}"
    )
    print(summary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze NMON files in batch mode")
    parser.add_argument("--in", dest="input_dir", required=True, help="Input directory containing .nmon files")
    parser.add_argument("--out", dest="output_dir", required=True, help="Output data directory")
    parser.add_argument(
        "--thresholds",
        dest="thresholds",
        default="config/thresholds.json",
        help="Path to thresholds JSON configuration",
    )
    return parser


def main(argv: List[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    thresholds_path = Path(args.thresholds)
    if not input_dir.exists():
        raise SystemExit(f"Input directory {input_dir} does not exist")
    analyze_directory(input_dir, output_dir, thresholds_path)


if __name__ == "__main__":
    main()
