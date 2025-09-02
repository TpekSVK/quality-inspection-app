# io/cameras/rtsp_gst_camera.py
import cv2 as cv
import time, threading
from typing import Optional, Callable
import numpy as np
from interfaces.camera import ICamera, Frame

def build_gst_pipeline(rtsp_url: str, latency_ms: int = 0) -> str:
    """
    ELI5: rtspsrc -> depay -> parse -> HW decode -> konverzia -> appsink
    Pozn.: funguje na Jetson (nvv4l2decoder). Na Windows nemusí byť dostupné.
    """
    # Ak máš H265, zmeň rtph264depay/h264parse na h265 verziu
    return (
        f"rtspsrc location={rtsp_url} latency={latency_ms} ! "
        f"rtph264depay ! h264parse ! "
        f"nvv4l2decoder ! "
        f"nvvidconv ! video/x-raw,format=BGRx ! "
        f"videoconvert ! video/x-raw,format=BGR ! "
        f"appsink drop=true sync=false"
    )

class RTSPGstCamera(ICamera):
    """
    ELI5: GStreamer kamera s HW dekódom. Background thread udržiava posledný frame.
    """
    def __init__(self, url: str, latency_ms: int = 0):
        self.url = url
        self.latency_ms = latency_ms
        self._cap: Optional[cv.VideoCapture] = None
        self._run = False
        self._th: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._last: Optional[Frame] = None
        self._on_new_frame: Optional[Callable[[Frame], None]] = None

    def open(self) -> None:
        pipe = build_gst_pipeline(self.url, self.latency_ms)
        self._cap = cv.VideoCapture(pipe, cv.CAP_GSTREAMER)
        if not self._cap.isOpened():
            raise RuntimeError("GStreamer pipeline sa neotvoril. Skontroluj JetPack/GStreamer a URL.")

    def close(self) -> None:
        self.stop()
        if self._cap is not None:
            try: self._cap.release()
            except: pass
        self._cap = None

    def start(self) -> None:
        if self._run: return
        if self._cap is None:
            self.open()
        self._run = True
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def stop(self) -> None:
        self._run = False
        if self._th:
            self._th.join(timeout=1.0)
        self._th = None

    def trigger(self) -> None: pass
    def set_exposure(self, exposure_ms: float) -> None: pass
    def set_gain(self, gain_db: float) -> None: pass
    def set_trigger_mode(self, enabled: bool) -> None: pass

    def _loop(self):
        while self._run:
            ok, frame = self._cap.read() if self._cap is not None else (False, None)
            if not ok or frame is None:
                time.sleep(0.01)
                continue
            with self._cond:
                self._last = frame
                self._cond.notify_all()
            if self._on_new_frame:
                try: self._on_new_frame(frame)
                except: pass

    def get_frame(self, timeout_ms: int = 100) -> Optional[Frame]:
        with self._cond:
            if self._last is not None:
                return self._last.copy()
            self._cond.wait(timeout=timeout_ms/1000.0)
            return self._last.copy() if self._last is not None else None
