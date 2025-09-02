# app/run_loop.py
import cv2 as cv
import numpy as np
from typing import Optional, Dict, Any, Tuple
from core.pipeline import Pipeline
from core.fixture.template_fixture import TemplateFixture
from core.tools.diff_from_ref import DiffFromRefTool
from core.tools.yolo_roi import YOLOInROITool
from core.tools.codes_decoder import decode_codes
from storage.recipe_store_json import RecipeStoreJSON
from storage.recipe_router import RecipeRouter
from qcio.plc.modbus_server import ModbusApp
from qcio.plc.plc_controller import PLCController
from config.plc_map import HR_RECIPE_ID

# Demo fallback cesty
DEFAULT_RECIPE = "FORMA_X_PRODUCT_Y"
REF_IMG_DEFAULT = "samples/ref.png"
CUR_IMG_DEFAULT = "samples/cur.png"

# ROI pre kód (napr. pravý dolný roh 400x400) – uprav podľa reality
def code_roi(img_shape: Tuple[int,int], size: int = 400) -> Tuple[int,int,int,int]:
    h, w = img_shape[:2]
    x = max(0, w - size)
    y = max(0, h - size)
    return (x, y, size, size)

class RunApp:
    def __init__(self):
        self.router = RecipeRouter()
        self.store = RecipeStoreJSON()
        self.current_recipe: Optional[str] = None
        self.ref_img = None
        self.pipe: Optional[Pipeline] = None

    def build_pipeline_from_recipe(self, recipe_name: str):
        recipe = self.store.load(recipe_name)
        # načítaj referenčný obrázok
        ref_path = recipe.get("reference_image", REF_IMG_DEFAULT)
        ref = cv.imread(ref_path, cv.IMREAD_GRAYSCALE)
        if ref is None:
            raise FileNotFoundError(f"Chýba referenčný obrázok: {ref_path}")
        self.ref_img = ref

        # fixture – z receptu (tpl_xywh)
        fx = recipe.get("fixture", {"type":"template", "tpl_xywh":[ref.shape[1]//2-100, ref.shape[0]//2-100, 200, 200], "min_score":0.6})
        x,y,w,h = fx.get("tpl_xywh", [0,0,200,200])
        tpl = ref[y:y+h, x:x+w].copy()
        fixture = TemplateFixture(tpl, min_score=float(fx.get("min_score", 0.6)))

        # tools – pre jednoduchosť dve položky (diff + YOLO), z receptu vieš spraviť dynamiku
        tools_conf = recipe.get("tools", [])
        tools = []
        for t in tools_conf:
            ttype = t.get("type")
            if ttype == "diff_from_ref":
                tools.append(DiffFromRefTool(
                    name=t.get("name","diff"),
                    roi_xywh=tuple(t.get("roi_xywh",[0,0,ref.shape[1]//2, ref.shape[0]//2])),
                    params=t.get("params",{}),
                    lsl=t.get("lsl",None), usl=t.get("usl",None),
                    units=t.get("units","px")
                ))
            elif ttype == "yolo_roi":
                tools.append(YOLOInROITool(
                    name=t.get("name","yolo"),
                    roi_xywh=tuple(t.get("roi_xywh",[ref.shape[1]//2,0,ref.shape[1]//2, ref.shape[0]//2])),
                    params=t.get("params",{}),
                    lsl=t.get("lsl",None), usl=t.get("usl",None),
                    units=t.get("units","count")
                ))
            # sem môžeš doplniť ďalšie tool typy (presence_absence, edgesHough,...)

        self.pipe = Pipeline(tools, fixture=fixture, pxmm=recipe.get("pxmm", None))
        self.current_recipe = recipe_name
        print(f"[RUN] Nahratý recept: {recipe_name}")

    def ensure_recipe(self, plc_id: Optional[int], cur_bgr: np.ndarray):
        # 1) PLC má prioritu
        if plc_id is not None:
            rname = self.router.resolve_by_id(plc_id)
            if rname and rname != self.current_recipe:
                self.build_pipeline_from_recipe(rname)
                return

        # 2) Auto-switch podľa kódu (ak PLC nič nedalo)
        # Pozor: bež na BGR (decoder to chce) a malú ROI
        roi = code_roi(cur_bgr.shape, size=400)
        codes = decode_codes(cur_bgr, roi)
        for c in codes:
            rname = self.router.resolve_by_code(c)
            if rname and rname != self.current_recipe:
                print(f"[RUN] Auto-switch podľa kódu {c} -> {rname}")
                self.build_pipeline_from_recipe(rname)
                return

        # 3) Fallback: ak nemáme nič, drž aktuálny; ak na štarte nič, načítaj default
        if self.current_recipe is None:
            self.build_pipeline_from_recipe(DEFAULT_RECIPE)

    # DEMO capture – nahraď ICamera integráciou (trigger/get_frame)
    def capture_frame(self) -> np.ndarray:
        img = cv.imread(CUR_IMG_DEFAULT, cv.IMREAD_GRAYSCALE)
        if img is None:
            raise FileNotFoundError(CUR_IMG_DEFAULT)
        return img

    def on_cycle(self, plc_ctx: ModbusApp) -> Dict[str,Any]:
        # PLC ID (ak PLC nevie, necháva 0/nezapisuje)
        try:
            plc_id = plc_ctx.get_hr(HR_RECIPE_ID)
            if plc_id == 0: plc_id = None
        except:
            plc_id = None

        cur = self.capture_frame()
        cur_bgr = cv.cvtColor(cur, cv.COLOR_GRAY2BGR)

        # zabezpeč správny recept
        self.ensure_recipe(plc_id, cur_bgr)

        # spracovanie
        out = self.pipe.process(self.ref_img, cur) if self.pipe else {"ok": True, "elapsed_ms": 0.0, "results":[]}
        return out

def main():
    app = RunApp()
    # pre istotu načítaj default (ak PLC/kód nepríde)
    app.build_pipeline_from_recipe(DEFAULT_RECIPE)

    modbus = ModbusApp(host="0.0.0.0", port=5020)
    modbus.start()

    plc = PLCController(modbus, on_capture_and_process=lambda: app.on_cycle(modbus))
    plc.loop()

if __name__ == "__main__":
    main()
