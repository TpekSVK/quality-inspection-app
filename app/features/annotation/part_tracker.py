### part_tracker.py
import os
from ultralytics import YOLO
import cv2
import datetime
from app.features.annotation.label_manager import id_to_name


class PartTracker:
    def __init__(self, model_path="yolov8n.pt", save_dir="dataset"):
        """
        model_path: cesta k YOLO modelu
        save_dir: hlavný adresár pre ukladanie fotiek (OK/NOK)
        """
        self.model = YOLO(model_path)
        self.save_dir = save_dir
        self.ok_dir = os.path.join(save_dir, "OK")
        self.nok_dir = os.path.join(save_dir, "NOK")
        os.makedirs(self.ok_dir, exist_ok=True)
        os.makedirs(self.nok_dir, exist_ok=True)

    def predict(self, frame):
        """
        Detekuje diely na obrázku a vráti zoznam predikcií:
        [{ "bbox": [x1, y1, x2, y2], "label": "<class_name>", "conf": float }, ...]
        """
        results = self.model.predict(frame, verbose=False)
        detections = []

        for result in results:
            boxes = result.boxes.xyxy.cpu().numpy()  # bounding box: x1,y1,x2,y2
            scores = result.boxes.conf.cpu().numpy()
            labels = result.boxes.cls.cpu().numpy()
            for box, score, cls_id in zip(boxes, scores, labels):

                # mapuj podľa dataset.yaml
                label = id_to_name(int(cls_id))
                detections.append({"bbox": box, "label": label, "conf": float(score)})
        return detections

    def save_frame(self, frame, kind):
        """
        Uloží aktuálny frame ako PNG do príslušnej zložky OK/NOK
        a vráti cestu k uloženému súboru.
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{kind}_{timestamp}.png"
        folder = self.ok_dir if kind == "OK" else self.nok_dir
        path = os.path.join(folder, filename)
        cv2.imwrite(path, frame)
        return path
