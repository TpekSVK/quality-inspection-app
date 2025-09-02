# storage/history_logger.py
import csv, time, os
from pathlib import Path
from typing import Dict, Any, List

class HistoryLogger:
    def __init__(self, root="history"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.root/"log.csv"
        if not self.csv_path.exists():
            with self.csv_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["ts","recipe","ok","elapsed_ms","measures_json","img_path"])

    def log(self, recipe: str, ok: bool, elapsed_ms: float, measures_json: str, img_path: str):
        with self.csv_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), recipe, int(ok), int(elapsed_ms), measures_json, img_path])
