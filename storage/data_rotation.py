# storage/data_rotation.py
import shutil, time
from pathlib import Path
from typing import Optional

class DataRotator:
    """
    ELI5: staré dáta mažeme. NOK nechávame všetky, OK len vzorku.
    """
    def __init__(self, base_dir="data", days_keep=7, ok_sample_every=50):
        self.base = Path(base_dir)
        self.days_keep = days_keep
        self.ok_sample_every = ok_sample_every
        self.base.mkdir(parents=True, exist_ok=True)
        (self.base/"ok").mkdir(exist_ok=True, parents=True)
        (self.base/"nok").mkdir(exist_ok=True, parents=True)

    def save(self, img_path: str, ok: bool, counter_ok: int):
        dst_dir = self.base/"nok" if not ok else self.base/"ok"
        if ok and (counter_ok % self.ok_sample_every != 0):
            return  # OK ukladáme len občas
        ts = time.strftime("%Y%m%d-%H%M%S")
        dst = dst_dir/f"{ts}_{Path(img_path).name}"
        shutil.copy2(img_path, dst)

    def rotate(self):
        cutoff = time.time() - self.days_keep*24*3600
        for sub in ["ok","nok"]:
            for p in (self.base/sub).glob("*"):
                try:
                    if p.stat().st_mtime < cutoff:
                        p.unlink()
                except: pass
