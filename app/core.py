from app.vision.camera import Camera
from app.vision.detection import YoloDetector

class AppCore:
    def __init__(self):
        self.camera = Camera(index=0)
        self.detector = YoloDetector(model_path="models/best.pt")

    def grab_and_detect(self):
        frame = self.camera.read()
        if frame is None:
            return None, []
        detections = self.detector.detect(frame)
        return frame, detections
