# app/dev_yolo_cli.py
import cv2 as cv
from core.tools.yolo_roi import YOLOInROITool
from core.pipeline import Pipeline

def main():
    img = cv.imread("samples/cur.png", cv.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError("samples/cur.png")

    # fiktívna fixtúra (None), ROI: stred 640x640
    h, w = img.shape[:2]
    roi = (max(0, w//2-320), max(0, h//2-320), 640, 640)

    ytool = YOLOInROITool(
        name="yolo_roi",
        roi_xywh=roi,
        params={
            "onnx_path": "models/yolo/model.onnx",
            "conf_th": 0.25,
            "iou_th": 0.45,
            "measure": "count",
            # "class_whitelist": [0,1]  # napr. len dve triedy
        },
        lsl=None, usl=0.0, units="count"  # napr. nič nechceme nájsť -> USL=0
    )

    pipe = Pipeline([ytool], fixture=None)
    out = pipe.process(img, img)

    print(f"VERDICT: {'OK' if out['ok'] else 'NOK'}  elapsed={out['elapsed_ms']:.2f} ms")
    r = out["results"][0]
    print("details:", r.details)
    if r.overlay is not None:
        cv.imwrite("out/yolo_overlay.png", r.overlay)

if __name__ == "__main__":
    main()
