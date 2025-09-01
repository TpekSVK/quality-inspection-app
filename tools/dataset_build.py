# tools/dataset_build.py
import os, glob, shutil
import yaml
import cv2
import numpy as np

from app.features.annotation.mask_manager import load_masks
from app.features.annotation.roi_manager import load_roi



def _read_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def _write_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def _yolo_to_xyxy(line, img_w, img_h):
    # "cls cx cy w h"
    parts = line.strip().split()
    if len(parts) < 5:
        return None
    cls = int(float(parts[0]))
    cx, cy, w, h = map(float, parts[1:5])
    bw = w * img_w
    bh = h * img_h
    x1 = (cx * img_w) - bw / 2.0
    y1 = (cy * img_h) - bh / 2.0
    x2 = x1 + bw
    y2 = y1 + bh
    return cls, x1, y1, x2, y2


def _xyxy_to_yolo(cls, x1, y1, x2, y2, new_w, new_h):
    # clip
    x1 = max(0, min(x1, new_w))
    y1 = max(0, min(y1, new_h))
    x2 = max(0, min(x2, new_w))
    y2 = max(0, min(y2, new_h))
    bw = max(0.0, x2 - x1)
    bh = max(0.0, y2 - y1)
    if bw <= 1e-6 or bh <= 1e-6:
        return None
    cx = (x1 + x2) / 2.0 / new_w
    cy = (y1 + y2) / 2.0 / new_h
    w = bw / new_w
    h = bh / new_h
    return f"{cls} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def _list_images(folder):
    exts = ("*.png", "*.jpg", "*.jpeg", "*.bmp")
    files = []
    for e in exts:
        files.extend(glob.glob(os.path.join(folder, e)))
    files.sort()
    return files


def build_dataset(apply_masks: bool = False, apply_roi: bool = False,
                  src_root: str = "dataset", dst_root: str = "dataset_build") -> str:
    """
    Vytvorí dočasný dataset do `dst_root` podľa `dataset/dataset.yaml`.
    - apply_masks: prekryje polygóny čiernou (bez zmeny labelov)
    - apply_roi: oreže podľa ROI a PREPOČÍTA labely (default False – ROI nezapekáme)
    Vracia cestu k novému dataset.yaml.
    """
    ds_yaml = os.path.join(src_root, "dataset.yaml")
    if not os.path.exists(ds_yaml):
        raise FileNotFoundError(f"Nenájdené: {ds_yaml}")

    cfg = _read_yaml(ds_yaml)
    names = cfg.get("names", [])
    train_rel = cfg.get("train", "images/train")
    val_rel = cfg.get("val", "images/val")

    train_img_src = os.path.join(src_root, train_rel)
    val_img_src   = os.path.join(src_root, val_rel)
    train_lbl_src = os.path.join(src_root, "labels", "train")
    val_lbl_src   = os.path.join(src_root, "labels", "val")

    train_img_dst = os.path.join(dst_root, "images", "train")
    val_img_dst   = os.path.join(dst_root, "images", "val")
    train_lbl_dst = os.path.join(dst_root, "labels", "train")
    val_lbl_dst   = os.path.join(dst_root, "labels", "val")

    for p in (train_img_dst, val_img_dst, train_lbl_dst, val_lbl_dst):
        os.makedirs(p, exist_ok=True)

    roi = load_roi() if apply_roi else None
    masks = load_masks() if apply_masks else []

    def process_subset(img_src_dir, lbl_src_dir, img_dst_dir, lbl_dst_dir):
        imgs = _list_images(img_src_dir)
        for img_path in imgs:
            base = os.path.splitext(os.path.basename(img_path))[0]
            lbl_path = os.path.join(lbl_src_dir, base + ".txt")
            img = cv2.imread(img_path, cv2.IMREAD_COLOR)
            if img is None:
                continue
            h, w = img.shape[:2]

            # ROI orez (voliteľné – default vypnuté)
            offx = offy = 0
            if roi:
                x1, y1, x2, y2 = roi
                x1 = max(0, min(x1, w))
                x2 = max(0, min(x2, w))
                y1 = max(0, min(y1, h))
                y2 = max(0, min(y2, h))
                if x2 <= x1 or y2 <= y1:
                    # invalid ROI -> preskoč orez
                    roi_img = img.copy()
                else:
                    roi_img = img[y1:y2, x1:x2].copy()
                    offx, offy = x1, y1
                img = roi_img
                h, w = img.shape[:2]

            # Masky (prekryť čiernou) – po ROI, aby sedeli súradnice
            if masks:
                for poly in masks:
                    pts = np.array([[x - offx, y - offy] for x, y in poly], dtype=np.int32)
                    cv2.fillPoly(img, [pts], (0, 0, 0))

            # Uloženie obrázka
            out_img_path = os.path.join(img_dst_dir, base + ".png")
            cv2.imwrite(out_img_path, img)

            # Labely: ak ROI, prepočítať; inak skopírovať
            out_lbl_path = os.path.join(lbl_dst_dir, base + ".txt")
            if not os.path.exists(lbl_path):
                open(out_lbl_path, "w").close()
                continue

            lines = []
            with open(lbl_path, "r") as lf:
                for line in lf:
                    if not line.strip():
                        continue
                    if roi:
                        parsed = _yolo_to_xyxy(line, img_w=(w + offx), img_h=(h + offy))  # pôvodné rozmery pred ROI
                        if not parsed:
                            continue
                        cls, x1b, y1b, x2b, y2b = parsed
                        # posun do ROI súradníc
                        x1b -= offx; x2b -= offx
                        y1b -= offy; y2b -= offy
                        converted = _xyxy_to_yolo(cls, x1b, y1b, x2b, y2b, w, h)
                        if converted:
                            lines.append(converted)
                    else:
                        # bez ROI – netreba meniť
                        lines.append(line.strip())

            with open(out_lbl_path, "w") as of:
                of.write("\n".join(lines) + ("\n" if lines else ""))

    process_subset(train_img_src, train_lbl_src, train_img_dst, train_lbl_dst)
    process_subset(val_img_src,   val_lbl_src,   val_img_dst,   val_lbl_dst)

    # dataset.yaml do build priečinka
    new_yaml = {
        "path": dst_root,
        "train": "images/train",
        "val": "images/val",
        "nc": len(names),
        "names": names,
    }
    new_yaml_path = os.path.join(dst_root, "dataset.yaml")
    _write_yaml(new_yaml_path, new_yaml)
    return new_yaml_path
