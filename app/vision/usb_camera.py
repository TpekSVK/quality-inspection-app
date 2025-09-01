# usb_camera.py
import sys
import cv2
import threading
import time

class USBCamera:
    """
    Jednoduchý wrapper nad cv2.VideoCapture s vláknom, nastaveniami a fallbackmi backendov.
    API:
      - start_stream(index, frame_callback, settings: dict | None, backend: Optional[int])
      - stop_stream()
      - get_current_frame() -> posledný frame (BGR) alebo None
    """
    def __init__(self):
        self.cap = None
        self.thread = None
        self.running = False
        self.last_frame = None
        self._lock = threading.Lock()

    # ---------------- interné pomocné ----------------
    def _pick_backends(self, preferred=None):
        """Zvoľ preferovaný a fallback backend podľa OS, ak nebol explicitne daný."""
        if preferred is not None:
            if sys.platform.startswith("win"):
                other = cv2.CAP_DSHOW if preferred == cv2.CAP_MSMF else cv2.CAP_MSMF
                return [preferred, other, None]
            return [preferred, None]
        # defaulty
        if sys.platform.startswith("win"):
            return [cv2.CAP_MSMF, cv2.CAP_DSHOW, None]
        elif sys.platform.startswith("linux"):
            return [cv2.CAP_V4L2, None]
        else:
            return [None]

    def _open_with_backends(self, device_index, backends):
        """Skúsi otvoriť kameru postupne s danými backendmi."""
        for bk in backends:
            cap = cv2.VideoCapture(device_index) if bk is None else cv2.VideoCapture(device_index, bk)
            if cap.isOpened():
                return cap
            try:
                cap.release()
            except Exception:
                pass
        # posledný pokus CAP_ANY
        cap = cv2.VideoCapture(device_index)
        if cap.isOpened():
            return cap
        try:
            cap.release()
        except Exception:
            pass
        return None

    def _apply_settings(self, settings: dict):
        """Najlepšie-ako-sa-dá aplikácia parametrov na kameru."""
        if not self.cap or not self.cap.isOpened() or not settings:
            return
        # rozlíšenie a fps
        w = int(settings.get("width", 0) or 0)
        h = int(settings.get("height", 0) or 0)
        fps = float(settings.get("fps", 0) or 0)
        if w > 0 and h > 0:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        if fps > 0:
            self.cap.set(cv2.CAP_PROP_FPS, fps)

        # auto-expozícia / manuálna expozícia / gain
        auto_exp = settings.get("auto_exposure", True)
        exposure = settings.get("exposure", None)
        gain = settings.get("gain", None)

        # CAP_PROP_AUTO_EXPOSURE – rôzne významy podľa backendu/OS:
        # OpenCV (MSMF/DSHOW/V4L2) – skúšame bežné varianty; ak to neprejde, ignorujeme.
        try:
            if auto_exp:
                # MSMF/DSHOW očakáva 1 (auto) alebo 0 (manual) – ale niekedy 0.75/0.25 (V4L2).
                ok = self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
                if not ok:
                    self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)  # V4L2-like
            else:
                ok = self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0)
                if not ok:
                    self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # V4L2-like manual
        except Exception:
            pass

        if exposure is not None and not auto_exp:
            try:
                # Pozn.: hodnota býva v rôznych škálach podľa backendu (niekedy EV, niekedy ms / log).
                self.cap.set(cv2.CAP_PROP_EXPOSURE, float(exposure))
            except Exception:
                pass

        if gain is not None:
            try:
                self.cap.set(cv2.CAP_PROP_GAIN, float(gain))
            except Exception:
                pass

    # ---------------- verejné API ----------------
    def start_stream(self, device_index: int, frame_callback, settings: dict | None = None, backend=None):
        """
        Spustí čítanie z kamery vo vlákne. Volá frame_callback(frame_bgr) pre každý záber.
        """
        self.stop_stream()  # pre istotu

        self.running = True

        def _worker():
            backends = self._pick_backends(backend)
            self.cap = self._open_with_backends(device_index, backends)
            if not self.cap:
                self.running = False
                return

            # aplikuj požadované nastavenia
            self._apply_settings(settings or {})

            # loop
            while self.running:
                ok, frame = self.cap.read()
                if not ok or frame is None:
                    time.sleep(0.01)
                    continue
                with self._lock:
                    self.last_frame = frame.copy()
                try:
                    if callable(frame_callback):
                        frame_callback(frame)
                except Exception:
                    # Nedusíme celé vlákno kvôli chybe v callbacku
                    pass

            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        t = threading.Thread(target=_worker, name="USBCameraThread", daemon=True)
        t.start()
        self.thread = t

    def stop_stream(self):
        self.running = False
        th = self.thread
        self.thread = None
        if th and th.is_alive():
            try:
                th.join(timeout=1.0)
            except Exception:
                pass
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def get_current_frame(self):
        with self._lock:
            return None if self.last_frame is None else self.last_frame.copy()
