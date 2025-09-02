# app/dev_cli_demo.py
import cv2 as cv
import numpy as np
from pathlib import Path

from core.pipeline import Pipeline
from core.fixture.template_fixture import TemplateFixture
from core.tools.diff_from_ref import DiffFromRefTool
from core.tools.presence_absence import PresenceAbsenceTool

def load_gray(p: str) -> np.ndarray:
    img = cv.imread(p, cv.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(p)
    return img

def main():
    # cesty si uprav podľa seba
    ref_path = "samples/ref.png"
    cur_path = "samples/cur.png"

    img_ref = load_gray(ref_path)
    img_cur = load_gray(cur_path)

    # --- Teach: vyrež si template pre fixtúru (tu len príklad) ---
    # napr. stred 200x200
    h, w = img_ref.shape[:2]
    cx, cy = w//2, h//2
    tpl = img_ref[cy-100:cy+100, cx-100:cx+100].copy()
    fixture = TemplateFixture(template_img=tpl, min_score=0.6)

    # --- Tools v ROI ---
    # ROI definujeme ako (x,y,w,h) – príklad: horná ľavá štvrtina
    t1 = DiffFromRefTool(
        name="diff",
        roi_xywh=(0,0,w//2,h//2),
        params={"blur":3, "thresh":25, "morph_open":1, "min_blob_area":20, "measure":"area"},
        lsl=None, usl=200.0, units="px"
    )

    t2 = PresenceAbsenceTool(
        name="presence",
        roi_xywh=(w//2,0,w//2,h//2),
        params={"minScore":0.7},  # template si vezme z referencie v danej ROI
        lsl=None, usl=None, units="score"
    )

    pipe = Pipeline([t1, t2], fixture=fixture, pxmm=None)
    out = pipe.process(img_ref, img_cur)

    print(f"VERDICT: {'OK' if out['ok'] else 'NOK'}   elapsed_ms={out['elapsed_ms']:.2f}")
    for r in out["results"]:
        print(f" - {r}")
    # uložíme overlay ROI pre kontrolu
    Path("out").mkdir(exist_ok=True)
    for r in pipe.tools:
        if hasattr(r, "name") and hasattr(r, "overlay") is False:
            continue
    # Generické: uložíme overlayy ak existujú
    for r in out["results"]:
        if r.overlay is not None:
            # len názov podľa toolu
            name = getattr(r, "name", "tool").replace(" ", "_")
            cv.imwrite(f"out/{name}_overlay.png", r.overlay)

if __name__ == "__main__":
    main()
