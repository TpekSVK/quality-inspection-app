# app/dev_autoteach_cli.py
# ELI5: Prejde OK (a voliteľne NOK) snímky, nameria DiffFromRefTool a navrhne USL pre FPR ~ 0.3 %.
import argparse, json, os, sys
from pathlib import Path

# umožní spúšťanie aj cez "python app/dev_autoteach_cli.py"
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import numpy as np
import cv2 as cv
from storage.recipe_store_json import RecipeStoreJSON
from core.tools.diff_from_ref import DiffFromRefTool

def load_gray(p: Path):
    img = cv.imread(str(p), cv.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(p)
    return img

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", required=True, help="Názov receptu (napr. FORMA_X_PRODUCT_Y)")
    ap.add_argument("--ok_dir", default=None, help="Priečinok s OK snímkami (ak prázdne, použije datasets/<recipe>/ok)")
    ap.add_argument("--nok_dir", default=None, help="Priečinok s NOK snímkami (voliteľné)")
    ap.add_argument("--tool_name", default=None, help="Meno toolu v recepte (ak None, vezme prvý diff_from_ref)")
    ap.add_argument("--target_fpr", type=float, default=0.003, help="Cieľový FPR (napr. 0.003 => 0.3 %)")
    ap.add_argument("--write", action="store_true", help="Zapísať navrhnutý USL do receptu")
    args = ap.parse_args()

    store = RecipeStoreJSON()
    recipe = store.load(args.recipe)
    ref = load_gray(Path(recipe["reference_image"]))

    # nájdi tool
    tool_conf = None
    for t in recipe.get("tools", []):
        if t.get("type") == "diff_from_ref" and (args.tool_name is None or t.get("name")==args.tool_name):
            tool_conf = t; break
    if tool_conf is None:
        raise RuntimeError("V recepte nenašiel som tool 'diff_from_ref'")

    tool = DiffFromRefTool(
        name=tool_conf.get("name","diff"),
        roi_xywh=tuple(tool_conf.get("roi_xywh",[0,0,ref.shape[1]//2, ref.shape[0]//2])),
        params=tool_conf.get("params",{}),
        lsl=tool_conf.get("lsl",None),
        usl=tool_conf.get("usl",None),
        units=tool_conf.get("units","px")
    )

    ok_dir = Path(args.ok_dir) if args.ok_dir else Path("datasets")/args.recipe/"ok"
    nok_dir = Path(args.nok_dir) if args.nok_dir else None
    ok_imgs = sorted([p for p in ok_dir.glob("*.png")] + [p for p in ok_dir.glob("*.jpg")] + [p for p in ok_dir.glob("*.bmp")])
    if not ok_imgs:
        raise RuntimeError(f"Žiadne OK snímky v {ok_dir}. Najprv ich ulož v RUN: 'Uložiť OK'.")

    measures_ok = []
    for p in ok_imgs:
        cur = load_gray(p)
        r = tool.run(ref, cur, fixture_transform=None)
        measures_ok.append(float(r.measured))
    measures_ok = np.array(measures_ok, dtype=float)

    # navrhneme USL: percentil podľa target FPR
    perc = 100.0 * (1.0 - args.target_fpr)
    usl = float(np.percentile(measures_ok, perc))

    out = {
        "n_ok": int(len(measures_ok)),
        "target_fpr": args.target_fpr,
        "suggested_usl": usl,
        "ok_stats": {
            "mean": float(measures_ok.mean()),
            "std": float(measures_ok.std(ddof=1)) if len(measures_ok)>1 else 0.0,
            "p95": float(np.percentile(measures_ok,95)),
            "p99": float(np.percentile(measures_ok,99)),
            "p99_7": float(np.percentile(measures_ok,99.7))
        }
    }

    # ak máme NOK, spočítame TPR pri tejto USL
    if nok_dir and nok_dir.exists():
        nok_imgs = sorted([p for p in nok_dir.glob("*.png")] + [p for p in nok_dir.glob("*.jpg")] + [p for p in nok_dir.glob("*.bmp")])
        hits = 0; vals=[]
        for p in nok_imgs:
            cur = load_gray(p)
            r = tool.run(ref, cur, fixture_transform=None)
            vals.append(float(r.measured))
            if float(r.measured) > usl:
                hits += 1
        out["n_nok"] = int(len(nok_imgs))
        out["tpr_at_usl"] = float(hits / max(1,len(nok_imgs)))
        out["nok_stats"] = {
            "mean": float(np.mean(vals)) if vals else 0.0,
            "p50": float(np.percentile(vals,50)) if vals else 0.0
        }

    print(json.dumps(out, ensure_ascii=False, indent=2))

    if args.write:
        tool_conf["usl"] = usl
        store.save_version(args.recipe, recipe)
        print(f"\nZapísané do receptu {args.recipe}: tool '{tool_conf.get('name')}' USL={usl:.2f}")

if __name__ == "__main__":
    main()
