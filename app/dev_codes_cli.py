# app/dev_codes_cli.py
# ELI5: načíta obrázok (alebo samples/qr_demo.png) a skúsi načítať kódy.
import argparse, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import cv2 as cv
from core.tools.codes_decoder import decode_codes

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", default="samples/qr_demo.png")
    args = ap.parse_args()

    img = cv.imread(args.img)
    if img is None:
        raise FileNotFoundError(args.img)

    out = decode_codes(img, None)
    print(out)

if __name__ == "__main__":
    main()
