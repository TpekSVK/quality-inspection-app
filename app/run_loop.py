# app/run_loop.py
import cv2 as cv
import numpy as np
from core.pipeline import Pipeline
from core.fixture.template_fixture import TemplateFixture
from core.tools.diff_from_ref import DiffFromRefTool
from core.tools.yolo_roi import YOLOInROITool
from io.plc.modbus_server import ModbusApp
from io.plc.plc_controller import PLCController

# POZN: Tu si pripoj reálnu kameru cez tvoje ICamera adaptéry.
# Pre demo použijeme dva súbory ako "ref" a "cur".
REF_IMG = "samples/ref.png"
CUR_IMG = "samples/cur.png"

def load_gray(p): 
    img = cv.imread(p, cv.IMREAD_GRAYSCALE)
    if img is None: raise FileNotFoundError(p)
    return img

def build_pipeline(ref_img):
    h, w = ref_img.shape[:2]
    tpl = ref_img[h//2-100:h//2+100, w//2-100:w//2+100].copy()
    fixture = TemplateFixture(tpl, min_score=0.6)

    t_diff = DiffFromRefTool(
        name="diff_A",
        roi_xywh=(0,0,w//2,h//2),
        params={"blur":3, "thresh":25, "morph_open":1, "min_blob_area":20, "measure":"area"},
        lsl=None, usl=200.0, units="px"
    )
    t_yolo = YOLOInROITool(
        name="yolo_B",
        roi_xywh=(w//2,0,w//2,h//2),
        params={"onnx_path":"models/yolo/model.onnx","conf_th":0.25,"iou_th":0.45,"measure":"count"},
        lsl=None, usl=0.0, units="count"
    )
    return Pipeline([t_diff, t_yolo], fixture=fixture)

def main():
    ref = load_gray(REF_IMG)
    pipe = build_pipeline(ref)

    modbus = ModbusApp(host="0.0.0.0", port=5020)
    modbus.start()

    def capture_and_process():
        # Realita: tu zavoláš ICamera.trigger(); frame = ICamera.get_frame()
        cur = load_gray(CUR_IMG)
        out = pipe.process(ref, cur)
        return out

    plc = PLCController(modbus, on_capture_and_process=capture_and_process)
    plc.loop()

if __name__ == "__main__":
    main()
