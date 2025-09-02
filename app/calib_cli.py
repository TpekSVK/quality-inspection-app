# app/calib_cli.py
import cv2 as cv
import argparse, json
from core.calibration import calibrate_checkerboard, calibrate_two_points

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", required=True, help="cesta k snímke pre kalibráciu (png/jpg)")
    ap.add_argument("--mode", choices=["checkerboard","2pt"], required=True)
    ap.add_argument("--pattern", default="7x7", help="vnútorné rohy, napr. 7x7")
    ap.add_argument("--square_mm", type=float, default=5.0, help="veľkosť štvorčeka v mm")
    ap.add_argument("--pt1", default=None, help="formát x,y (pre 2pt)")
    ap.add_argument("--pt2", default=None, help="formát x,y (pre 2pt)")
    ap.add_argument("--mm", type=float, default=10.0, help="reálna vzdialenosť v mm (pre 2pt)")
    args = ap.parse_args()

    img = cv.imread(args.img, cv.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(args.img)

    if args.mode == "checkerboard":
        w,h = map(int, args.pattern.lower().split("x"))
        res = calibrate_checkerboard(img, (w,h), args.square_mm)
    else:
        if args.pt1 is None or args.pt2 is None:
            raise ValueError("pre 2pt uveď --pt1 a --pt2 vo formáte x,y")
        x1,y1 = map(int, args.pt1.split(","))
        x2,y2 = map(int, args.pt2.split(","))
        res = calibrate_two_points((x1,y1),(x2,y2), args.mm)

    print(json.dumps(res, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
