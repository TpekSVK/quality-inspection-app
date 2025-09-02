# interfaces/camera_adapters.py
from typing import Optional
import numpy as np
from interfaces.camera import ICamera, Frame

# POZOR:
# Tu zabaľ tvoje existujúce implementácie (io/cameras/ip_camera.py, usb_camera.py)
# do rozhrania ICamera. Neviem ich presnú API, preto sú tu skeletony.

class IPCameraAdapter(ICamera):
    def __init__(self, low_level_cam):
        self.cam = low_level_cam

    def open(self):  self.cam.open()
    def close(self): self.cam.close()
    def start(self): self.cam.start()
    def stop(self):  self.cam.stop()
    def trigger(self): self.cam.trigger()
    def set_exposure(self, ms: float): self.cam.set_exposure(ms)
    def set_gain(self, db: float): self.cam.set_gain(db)
    def set_trigger_mode(self, enabled: bool): self.cam.set_trigger_mode(enabled)

    def get_frame(self, timeout_ms: int = 100) -> Optional[Frame]:
        # mapni na tvoju metódu (napr. read()/get_last_frame())
        return self.cam.get_frame(timeout_ms)

class USBCameraAdapter(ICamera):
    def __init__(self, low_level_cam):
        self.cam = low_level_cam
    # rovnaké forwardy ako hore...
    def open(self):  self.cam.open()
    def close(self): self.cam.close()
    def start(self): self.cam.start()
    def stop(self):  self.cam.stop()
    def trigger(self): self.cam.trigger()
    def set_exposure(self, ms: float): self.cam.set_exposure(ms)
    def set_gain(self, db: float): self.cam.set_gain(db)
    def set_trigger_mode(self, enabled: bool): self.cam.set_trigger_mode(enabled)
    def get_frame(self, timeout_ms: int = 100) -> Optional[Frame]:
        return self.cam.get_frame(timeout_ms)
