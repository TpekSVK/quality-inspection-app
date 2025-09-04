# app/calib_cli.py
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

# umožní spúšťanie aj cez "python app/calib_cli.py"
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import cv2 as cv
from core.calibration import pxmm_from_two_points
from storage.recipe_store_json import RecipeStoreJSON

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", required=True, help="Cesta k obrázku (len na kontrolu rozmeru).")
    ap.add_argument("--mode", choices=["2pt"], default="2pt")
    ap.add_argument("--pt1", required=True, help="x,y (px)")
    ap.add_argument("--pt2", required=True, help="x,y (px)")
    ap.add_argument("--mm",  required=True, type=float, help="Skutočná vzdialenosť v mm.")
    ap.add_argument("--recipe", required=False, help="Ak zadané, uloží pxmm do receptu.")
    ap.add_argument("--write", action="store_true", help="Zapísať do receptu.")
    args = ap.parse_args()

    img = cv.imread(args.img, cv.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(args.img)

    pt1 = tuple(int(v) for v in args.pt1.split(","))
    pt2 = tuple(int(v) for v in args.pt2.split(","))
    pxmm = pxmm_from_two_points(pt1, pt2, args.mm)
    out = {"img_shape": img.shape[:2], "pxmm": pxmm}
    print(json.dumps(out, ensure_ascii=False, indent=2))

    if args.recipe and args.write:
        store = RecipeStoreJSON()
        rec = store.load(args.recipe)
        rec["pxmm"] = pxmm
        store.save_version(args.recipe, rec)
        print(f"\nZapísané do receptu {args.recipe}: pxmm={pxmm}")

if __name__ == "__main__":
    main()
