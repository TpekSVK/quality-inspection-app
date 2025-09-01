from ultralytics import YOLO

class YoloDetector:
    def __init__(self, model_path: str):
        self.model = YOLO(model_path)

    def detect(self, img):
        results = self.model.predict(img, verbose=False)
        detections = []
        for r in results:
            for b in r.boxes:
                cls_id = int(b.cls[0])
                conf = float(b.conf[0])
                xyxy = b.xyxy[0].tolist()
                detections.append({"cls": cls_id, "conf": conf, "xyxy": xyxy})
        return detections
