# annotation/label_manager.py
import os
import yaml
from glob import glob

DATASET_DIR = "dataset"
DATASET_YAML = os.path.join(DATASET_DIR, "dataset.yaml")

def _default_yaml():
    return {
        "path": "dataset",
        "train": "images/train",
        "val": "images/val",
        "nc": 2,
        "names": ["defekt", "ok"],
    }

def ensure_yaml(names=None):
    os.makedirs(DATASET_DIR, exist_ok=True)
    data = read_yaml()
    if names is None:
        names = data.get("names", _default_yaml()["names"])
    out = {
        "path": "dataset",
        "train": "images/train",
        "val": "images/val",
        "nc": len(names),
        "names": names,
    }
    with open(DATASET_YAML, "w") as f:
        yaml.safe_dump(out, f, sort_keys=False)

def read_yaml():
    if os.path.exists(DATASET_YAML):
        try:
            with open(DATASET_YAML, "r") as f:
                data = yaml.safe_load(f) or {}
            if "names" in data and isinstance(data["names"], list):
                data["nc"] = len(data["names"])
            return data
        except Exception:
            pass
    data = _default_yaml()
    ensure_yaml(data["names"])
    return data

def get_names():
    return read_yaml().get("names", _default_yaml()["names"])

def name_to_id(name):
    names = get_names()
    if name in names:
        return names.index(name)
    names.append(name)
    ensure_yaml(names)
    return len(names) - 1

def id_to_name(cls_id: int):
    names = get_names()
    if 0 <= cls_id < len(names):
        return names[cls_id]
    return f"class_{cls_id}"

# ---------- správa tried ----------

def add_class(name: str) -> None:
    names = get_names()
    if name in names:
        return
    names.append(name)
    ensure_yaml(names)

def rename_class(old_name: str, new_name: str) -> None:
    names = get_names()
    if old_name not in names:
        return
    idx = names.index(old_name)
    names[idx] = new_name
    ensure_yaml(names)
    # ID v labeloch sa nemenia (len textový názov v dataset.yaml)

def remove_class(name: str) -> None:
    """Zmaže triedu z dataset.yaml a z labelov vyhodí jej boxy; ID > idx sa dekrementujú."""
    names = get_names()
    if name not in names:
        return
    rm_idx = names.index(name)
    new_names = names[:rm_idx] + names[rm_idx+1:]
    _rewrite_labels_remove_class(rm_idx)
    ensure_yaml(new_names)

def _iter_label_files():
    for sub in ("train", "val"):
        pattern = os.path.join(DATASET_DIR, "labels", sub, "*.txt")
        for p in glob(pattern):
            yield p

def _rewrite_labels_remove_class(rm_idx: int):
    for lf in _iter_label_files():
        if not os.path.exists(lf):
            continue
        lines_out = []
        with open(lf, "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                cid = int(float(parts[0]))
                if cid == rm_idx:
                    # vyhoď boxy tejto triedy
                    continue
                if cid > rm_idx:
                    cid -= 1
                parts[0] = str(cid)
                lines_out.append(" ".join(parts))
        with open(lf, "w") as g:
            g.write("\n".join(lines_out) + ("\n" if lines_out else ""))
