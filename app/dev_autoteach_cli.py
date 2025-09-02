# app/dev_autoteach_cli.py
import cv2 as cv
from glob import glob
from core.tools.diff_from_ref import DiffFromRefTool
from core.tools.anomaly_autoteach import AutoteachCalibrator

def load_gray(p):
    img = cv.imread(p, cv.IMREAD_GRAYSCALE)
    if img is None: raise FileNotFoundError(p)
    return img

def main():
    ref = load_gray("samples/ref.png")
    ok_paths = sorted(glob("samples/ok/*.png")) or sorted(glob("samples/ok/*.jpg"))
    ok_imgs = [load_gray(p) for p in ok_paths]

    h, w = ref.shape[:2]
    tool = DiffFromRefTool(
        name="diff_roi_A",
        roi_xywh=(0,0,w//2,h//2),
        params={"blur":3,"thresh":25,"morph_open":1,"min_blob_area":20,"measure":"area"},
        lsl=None, usl=None, units="px"
    )
    cal = AutoteachCalibrator(target_fpr=0.003)
    usl = cal.calibrate_usl(tool, ref, ok_imgs, fixture_transform=None)
    print(f"Navrhnutý USL (FPR~0.3%): {usl:.2f} px")

if __name__ == "__main__":
    main()
