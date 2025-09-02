# interfaces/camera_dummy.py
import cv2 as cv
import numpy as np
from typing import Optional, Callable
from interfaces.camera import ICamera, Frame

class DummyCamera(ICamera):
    """
    ELI5: Pre dev. číta opakovane samples/cur.png (alebo posledný zachytený),
    trigger iba „oznámi“ že ďalší frame je pripravený.
    """
    def __init__(self, img_path: str = "samples/cur.png"):
        self.img_path = img_path
        self._on_new_frame = None

    def open(self) -> None: pass
    def close(self) -> None: pass
    def start(self) -> None: pass
    def stop(self) -> None: pass
    def set_exposure(self, exposure_ms: float) -> None: pass
    def set_gain(self, gain_db: float) -> None: pass
    def set_trigger_mode(self, enabled: bool) -> None: pass

    def trigger(self) -> None:
        # nič, snímka sa načíta na požiadanie
        pass

    def get_frame(self, timeout_ms: int = 100) -> Optional[Frame]:
        img = cv.imread(self.img_path, cv.IMREAD_GRAYSCALE)
        return img
