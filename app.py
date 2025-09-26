"""Flask entry point for the NMON analyzer."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import List

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename

from core import AnalysisStore, parse_nmon, run_all_rules
from core.model import FileAnalysis
from core.utils import downsample_series

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = BASE_DIR / "config" / "thresholds.json"

app = Flask(__name__)
store = AnalysisStore(DATA_DIR)


def load_thresholds() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_thresholds(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def allowed_file(filename: str) -> bool:
    return filename.lower().endswith(".nmon")


def _analysis_from_upload(temp_path: Path, filename: str, thresholds: dict) -> FileAnalysis:
    nmon = parse_nmon(temp_path)
    checks, overall = run_all_rules(nmon, thresholds)
    stem = Path(secure_filename(filename)).stem or "nmon"
    file_id = store.generate_file_id(stem)
    analysis = FileAnalysis(
        file_id=file_id,
        source_path=filename,
        hostname=nmon.hostname,
        start_time=nmon.start_time,
        checks=checks,
        overall=overall,
    )
    store.save_analysis(analysis, temp_path)
    return analysis


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/files")
def api_files():
    entries = store.list_analyses()
    files = []
    summary = {
        "total_files": 0,
        "ok_files": 0,
        "warn_files": 0,
        "crit_files": 0,
        "warn_checks": 0,
        "crit_checks": 0,
    }
    for entry in entries:
        data = store.load_analysis(entry["file_id"])
        if not data:
            continue
        files.append(data)
        summary["total_files"] += 1
        overall = data.get("overall", "OK")
        if overall == "CRIT":
            summary["crit_files"] += 1
        elif overall == "WARN":
            summary["warn_files"] += 1
        else:
            summary["ok_files"] += 1
        for check in data.get("checks", []):
            if check.get("level") == "WARN":
                summary["warn_checks"] += 1
            elif check.get("level") == "CRIT":
                summary["crit_checks"] += 1
    return jsonify({"files": files, "summary": summary})


@app.post("/upload")
def upload():
    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400
    uploaded_files = request.files.getlist("files")
    thresholds = load_thresholds()
    stored: List[dict] = []
    summary = {
        "total_files": 0,
        "ok_files": 0,
        "warn_files": 0,
        "crit_files": 0,
        "warn_checks": 0,
        "crit_checks": 0,
    }
    for file in uploaded_files:
        if not file.filename or not allowed_file(file.filename):
            continue
        with tempfile.NamedTemporaryFile(delete=False, suffix=".nmon") as temp:
            file.save(temp.name)
            temp_path = Path(temp.name)
        try:
            analysis = _analysis_from_upload(temp_path, file.filename, thresholds)
            data = analysis.as_dict()
            stored.append(data)
            summary["total_files"] += 1
            if analysis.overall == "CRIT":
                summary["crit_files"] += 1
            elif analysis.overall == "WARN":
                summary["warn_files"] += 1
            else:
                summary["ok_files"] += 1
            for check in analysis.checks:
                if check.level == "WARN":
                    summary["warn_checks"] += 1
                elif check.level == "CRIT":
                    summary["crit_checks"] += 1
        finally:
            if temp_path.exists():
                os.unlink(temp_path)
    return jsonify({"summary": summary, "files": stored})


@app.get("/file/<file_id>")
def file_detail(file_id: str):
    data = store.load_analysis(file_id)
    if not data:
        return redirect(url_for("index"))
    return render_template("file_detail.html", analysis=data)


@app.get("/api/file/<file_id>")
def api_file(file_id: str):
    data = store.load_analysis(file_id)
    if not data:
        return jsonify({"error": "Not found"}), 404
    upload_path = store.upload_dir / f"{file_id}.nmon"
    if not upload_path.exists():
        return jsonify({"error": "Upload not available"}), 404
    nmon = parse_nmon(upload_path)
    series_payload = {
        name: downsample_series(series.timestamps, series.values)
        for name, series in nmon.series.items()
    }
    return jsonify({"analysis": data, "series": series_payload})


@app.get("/report")
def report():
    entries = store.list_analyses()
    analyses = []
    for entry in entries:
        data = store.load_analysis(entry["file_id"])
        if data:
            analyses.append(data)
    return render_template(
        "report.html",
        analyses=analyses,
        generated=datetime.now().isoformat(),
    )


@app.get("/export/csv")
def export_csv():
    entries = store.list_analyses()
    headers = [
        "file_id",
        "hostname",
        "start_time",
        "overall",
        "cpu_level",
        "memory_leak_level",
        "emmc_level",
        "network_level",
        "cpu_max_rolling_pct",
        "memory_leak_slope",
        "emmc_p95_kbps",
        "network_p95_kbps",
    ]
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for entry in entries:
        data = store.load_analysis(entry["file_id"])
        if not data:
            continue
        checks = {check["rule"]: check for check in data.get("checks", [])}
        cpu = checks.get("cpu_sustained_high", {})
        mem = checks.get("memory_leak", {})
        emmc = checks.get("excessive_emmc_writes", {})
        net = checks.get("excessive_network_usage", {})
        writer.writerow(
            [
                data.get("file_id"),
                data.get("hostname"),
                data.get("start_time"),
                data.get("overall"),
                cpu.get("level"),
                mem.get("level"),
                emmc.get("level"),
                net.get("level"),
                (cpu.get("metrics", {}) or {}).get("max_rolling_busy_pct"),
                (mem.get("metrics", {}) or {}).get("slope_kb_per_min"),
                (emmc.get("metrics", {}) or {}).get("p95_kbps"),
                (net.get("metrics", {}) or {}).get("p95_kbps"),
            ]
        )
    output.seek(0)
    return Response(
        output.getvalue(),
        headers={
            "Content-Disposition": "attachment; filename=analysis.csv",
            "Content-Type": "text/csv",
        },
    )


@app.get("/config")
def get_config():
    return jsonify(load_thresholds())


@app.post("/config")
def post_config():
    payload = request.get_json(force=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid payload"}), 400
    save_thresholds(payload)
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=False)
