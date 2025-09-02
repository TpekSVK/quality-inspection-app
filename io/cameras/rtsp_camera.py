# io/cameras/rtsp_camera.py
import cv2 as cv
import time
import threading
from typing import Optional, Callable
import numpy as np
from interfaces.camera import ICamera, Frame

class RTSPCamera(ICamera):
    """
    ELI5: Načítava RTSP stream do background threadu a drží posledný frame.
    get_frame() vráti posledný snímok (čaká do timeoutu, kým niečo príde).
    Pozn.: RTSP zvyčajne nemá HW trigger; trigger() je tu no-op.
    """

    def __init__(self, url: str, width: Optional[int] = None, height: Optional[int] = None,
                 reconnect_sec: float = 2.0, backend: int = cv.CAP_FFMPEG):
        self.url = url
        self.width = width
        self.height = height
        self.reconnect_sec = reconnect_sec
        self.backend = backend

        self._cap: Optional[cv.VideoCapture] = None
        self._th: Optional[threading.Thread] = None
        self._run = False
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._last: Optional[Frame] = None
        self._on_new_frame: Optional[Callable[[Frame], None]] = None

    def open(self) -> None:
        self._open_cap()

    def _open_cap(self):
        if self._cap is not None:
            try: self._cap.release()
            except: pass
        self._cap = cv.VideoCapture(self.url, self.backend)
        # voliteľné nastavenie rozlíšenia ak stream dovolí
        if self.width:  self._cap.set(cv.CAP_PROP_FRAME_WIDTH,  self.width)
        if self.height: self._cap.set(cv.CAP_PROP_FRAME_HEIGHT, self.height)

    def close(self) -> None:
        self.stop()
        if self._cap is not None:
            try: self._cap.release()
            except: pass
        self._cap = None

    def start(self) -> None:
        if self._th and self._th.is_alive():
            return
        self._run = True
        if self._cap is None:
            self._open_cap()
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def stop(self) -> None:
        self._run = False
        if self._th:
            self._th.join(timeout=1.0)
        self._th = None

    def trigger(self) -> None:
        # RTSP nemá HW trigger; berieme posledný dostupný frame
        pass

    def set_exposure(self, exposure_ms: float) -> None: pass
    def set_gain(self, gain_db: float) -> None: pass
    def set_trigger_mode(self, enabled: bool) -> None: pass

    def _loop(self):
        backoff = self.reconnect_sec
        while self._run:
            if self._cap is None or not self._cap.isOpened():
                self._open_cap()
                time.sleep(backoff)

            ok, frame = (False, None)
            try:
                ok, frame = self._cap.read()
            except Exception:
                ok = False

            if not ok or frame is None:
                # reconnect s malým backoffom
                time.sleep(backoff)
                try:
                    if self._cap is not None:
                        self._cap.release()
                except: pass
                self._cap = None
                continue

            # máme frame
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
            # čakáme na prvý frame
            self._cond.wait(timeout=timeout_ms/1000.0)
            return self._last.copy() if self._last is not None else None
