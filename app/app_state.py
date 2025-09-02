# app/app_state.py
from typing import Optional, Dict, Any
import cv2 as cv
import numpy as np

from storage.recipe_store_json import RecipeStoreJSON
from storage.recipe_router import RecipeRouter
from storage.history_logger import HistoryLogger

from core.pipeline import Pipeline
from core.fixture.template_fixture import TemplateFixture
from core.tools.diff_from_ref import DiffFromRefTool
from core.tools.presence_absence import PresenceAbsenceTool
from core.tools.yolo_roi import YOLOInROITool

from interfaces.camera import ICamera

class AppState:
    """
    Drží: current recipe, referenčný obrázok, pipeline, logger a *kameru*.
    """
    def __init__(self):
        self.store = RecipeStoreJSON()
        self.router = RecipeRouter()
        self.logger = HistoryLogger()
        self.current_recipe: Optional[str] = None
        self.ref_img: Optional[np.ndarray] = None
        self.pipeline: Optional[Pipeline] = None
        self.camera: Optional[ICamera] = None

    # --- kamera ---
    def set_camera(self, cam: ICamera):
        if self.camera:
            try:
                self.camera.stop(); self.camera.close()
            except: pass
        self.camera = cam
        try:
            self.camera.open(); self.camera.start()
        except Exception as e:
            raise RuntimeError(f"Kamera sa nespustila: {e}")

    def get_frame(self, timeout_ms: int = 200) -> Optional[np.ndarray]:
        if not self.camera:
            return None
        frm = self.camera.get_frame(timeout_ms=timeout_ms)
        if frm is None:
            return None
        # pipeline počíta v grayscale, ale zvládne aj BGR; necháme grayscale
        if frm.ndim == 3:
            return cv.cvtColor(frm, cv.COLOR_BGR2GRAY)
        return frm

    # --- recept/pipeline ---
    def build_from_recipe(self, recipe_name: str):
        recipe = self.store.load(recipe_name)
        ref_path = recipe.get("reference_image", None)
        if not ref_path:
            raise FileNotFoundError("V recepte nie je reference_image.")
        ref = cv.imread(ref_path, cv.IMREAD_GRAYSCALE)
        if ref is None:
            raise FileNotFoundError(f"Neviem načítať referenčný obrázok: {ref_path}")
        self.ref_img = ref

        fx = recipe.get("fixture", {"type":"template","tpl_xywh":[ref.shape[1]//2-100, ref.shape[0]//2-100, 200,200], "min_score":0.6})
        x,y,w,h = fx.get("tpl_xywh",[0,0,200,200])
        tpl = ref[y:y+h, x:x+w].copy()
        fixture = TemplateFixture(tpl, min_score=float(fx.get("min_score",0.6)))

        tools_conf = recipe.get("tools", [])
        tools = []
        for t in tools_conf:
            typ = t.get("type","")
            if typ == "diff_from_ref":
                tools.append(DiffFromRefTool(
                    name=t.get("name","diff"),
                    roi_xywh=tuple(t.get("roi_xywh",[0,0,ref.shape[1]//2, ref.shape[0]//2])),
                    params=t.get("params",{}),
                    lsl=t.get("lsl",None), usl=t.get("usl",None), units=t.get("units","px")
                ))
            elif typ == "presence_absence":
                tools.append(PresenceAbsenceTool(
                    name=t.get("name","presence"),
                    roi_xywh=tuple(t.get("roi_xywh",[ref.shape[1]//2,0,ref.shape[1]//2, ref.shape[0]//2])),
                    params=t.get("params",{"minScore":0.7}),
                    lsl=t.get("lsl",None), usl=t.get("usl",None), units=t.get("units","score")
                ))
            elif typ == "yolo_roi":
                tools.append(YOLOInROITool(
                    name=t.get("name","yolo"),
                    roi_xywh=tuple(t.get("roi_xywh",[ref.shape[1]//2,0,ref.shape[1]//2, ref.shape[0]//2])),
                    params=t.get("params",{}),
                    lsl=t.get("lsl",None), usl=t.get("usl",None), units=t.get("units","count")
                ))
        self.pipeline = Pipeline(tools, fixture=fixture, pxmm=recipe.get("pxmm"))
        self.current_recipe = recipe_name

    def process(self, img_cur: np.ndarray) -> Dict[str,Any]:
        assert self.pipeline is not None and self.ref_img is not None, "Pipeline/ref nie sú pripravené"
        return self.pipeline.process(self.ref_img, img_cur)
