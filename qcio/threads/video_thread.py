### video_thread.py
from PySide6.QtCore import QThread, Signal
import cv2

class VideoThread(QThread):
    frame_ready = Signal(object)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.running = True
        self.last_frame = None  # tu uložíme posledný frame

    def run(self):
        cap = cv2.VideoCapture(self.url)
        while self.running:
            ret, frame = cap.read()
            if ret:
                self.last_frame = frame  # uložíme
                self.frame_ready.emit(frame)
        cap.release()

    def stop(self):
        self.running = False
        self.wait()

    def get_current_frame(self):
        return self.last_frame  # vráti posledný frame
