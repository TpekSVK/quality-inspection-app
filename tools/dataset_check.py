# tools/dataset_check.py
import os, glob
from collections import defaultdict
from app.features.annotation.label_manager import get_names


def _list(folder, exts=(".png",".jpg",".jpeg",".bmp")):
    files = []
    for e in exts:
        files.extend(glob.glob(os.path.join(folder, f"*{e}")))
    return sorted(files)

def analyze_dataset(root="dataset"):
    report = []
    names = get_names()
    report.append(f"Classes ({len(names)}): {', '.join(names)}")

    def analyze_split(split):
        img_dir = os.path.join(root, "images", split)
        lb_dir  = os.path.join(root, "labels", split)
        imgs = _list(img_dir)
        report.append(f"\n[{split.upper()}] images: {len(imgs)}")
        missing = 0
        empty = 0
        per_class = defaultdict(int)
        out_of_range = 0

        for ip in imgs:
            base = os.path.splitext(os.path.basename(ip))[0]
            lp = os.path.join(lb_dir, base + ".txt")
            if not os.path.exists(lp):
                missing += 1
                continue
            lines = [l.strip() for l in open(lp, "r").read().strip().splitlines() if l.strip()]
            if not lines:
                empty += 1
                continue
            for ln in lines:
                parts = ln.split()
                if len(parts) < 5: continue
                cid = int(float(parts[0]))
                x,y,w,h = map(float, parts[1:5])
                if cid < 0 or cid >= len(names) or not (0<=x<=1 and 0<=y<=1 and 0<w<=1 and 0<h<=1):
                    out_of_range += 1
                else:
                    per_class[cid] += 1

        report.append(f"missing label files: {missing}")
        report.append(f"empty labels: {empty}")
        report.append(f"out-of-range boxes: {out_of_range}")
        if per_class:
            report.append("boxes per class:")
            for cid, cnt in sorted(per_class.items()):
                cname = names[cid] if cid < len(names) else f"cls_{cid}"
                report.append(f"  - {cname}: {cnt}")
        else:
            report.append("boxes per class: (none)")

    for sp in ("train","val"):
        analyze_split(sp)

    return "\n".join(report)
