"""Local persistence helpers for analysis results."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from .model import FileAnalysis
from .utils import ensure_directory


class AnalysisStore:
    """Handles saving and loading analysis outputs on disk."""

    def __init__(self, base_path: Path | str = "data") -> None:
        self.base_path = Path(base_path)
        self.upload_dir = self.base_path / "uploads"
        self.analysis_dir = self.base_path / "analyses"
        ensure_directory(self.upload_dir)
        ensure_directory(self.analysis_dir)
        self.index_path = self.base_path / "index.json"
        if not self.index_path.exists():
            self._write_index([])

    def generate_file_id(self, stem: str) -> str:
        safe_stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in stem)
        unique = uuid.uuid4().hex[:8]
        return f"{safe_stem}-{unique}"

    def save_analysis(self, analysis: FileAnalysis, original_file: Path) -> None:
        ensure_directory(self.upload_dir)
        ensure_directory(self.analysis_dir)
        upload_target = self.upload_dir / f"{analysis.file_id}.nmon"
        shutil.copy2(original_file, upload_target)
        analysis_path = self.analysis_dir / f"{analysis.file_id}.json"
        with open(analysis_path, "w", encoding="utf-8") as handle:
            json.dump(analysis.as_dict(), handle, indent=2)
        entries = self._read_index()
        entry = {
            "file_id": analysis.file_id,
            "hostname": analysis.hostname,
            "start_time": analysis.start_time.isoformat() if analysis.start_time else None,
            "overall": analysis.overall,
        }
        entries = [item for item in entries if item.get("file_id") != analysis.file_id]
        entries.append(entry)
        self._write_index(entries)

    def load_analysis(self, file_id: str) -> Optional[Dict]:
        analysis_path = self.analysis_dir / f"{file_id}.json"
        if not analysis_path.exists():
            return None
        with open(analysis_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def list_analyses(self) -> List[Dict]:
        entries = self._read_index()
        entries.sort(key=lambda item: item.get("start_time") or "", reverse=True)
        return entries

    def _read_index(self) -> List[Dict]:
        if not self.index_path.exists():
            return []
        with open(self.index_path, "r", encoding="utf-8") as handle:
            try:
                return json.load(handle)
            except json.JSONDecodeError:
                return []

    def _write_index(self, entries: List[Dict]) -> None:
        ensure_directory(self.base_path)
        with open(self.index_path, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2)

    def clear(self) -> None:
        if self.index_path.exists():
            self.index_path.unlink()
        if self.upload_dir.exists():
            shutil.rmtree(self.upload_dir)
        if self.analysis_dir.exists():
            shutil.rmtree(self.analysis_dir)
        ensure_directory(self.upload_dir)
        ensure_directory(self.analysis_dir)
        self._write_index([])
