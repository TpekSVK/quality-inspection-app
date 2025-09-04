### ip_camera.py
from qcio.threads.video_thread import VideoThread


class IPCamera:
    def __init__(self):
        self.video_thread = None

    def start_stream(self, url, frame_callback):
        if self.video_thread is not None:
            self.stop_stream()
        self.video_thread = VideoThread(url)
        self.video_thread.frame_ready.connect(frame_callback)
        self.video_thread.start()

    def stop_stream(self):
        if self.video_thread is not None:
            self.video_thread.stop()
            self.video_thread = None

    def get_current_frame(self):
        if self.video_thread:
            return self.video_thread.get_current_frame()
        return None
