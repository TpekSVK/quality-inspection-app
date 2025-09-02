# annotation/mask_manager.py
import os
import yaml

MASKS_FILE = os.path.join("dataset", "masks.yaml")

def _ensure_dir():
    os.makedirs("dataset", exist_ok=True)

def add_mask(points):
    """
    points: list[(x,y)] v pixeloch (int)
    Pridá polygón ako masku.
    """
    _ensure_dir()
    data = {"masks": []}
    if os.path.exists(MASKS_FILE):
        try:
            with open(MASKS_FILE, "r") as f:
                data = yaml.safe_load(f) or {"masks": []}
        except Exception:
            pass

    data["masks"].append({"type": "polygon", "points": [[int(x), int(y)] for x, y in points]})
    with open(MASKS_FILE, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)
    print(f"📄 Maska pridaná, masks.yaml obsahuje {len(data['masks'])} položiek.")

def load_masks():
    """
    Return: list[list[(x,y)]]
    """
    if os.path.exists(MASKS_FILE):
        try:
            with open(MASKS_FILE, "r") as f:
                data = yaml.safe_load(f) or {}
            masks = []
            for m in data.get("masks", []):
                if m.get("type") == "polygon" and "points" in m:
                    pts = [(int(x), int(y)) for x, y in m["points"]]
                    if len(pts) >= 3:
                        masks.append(pts)
            return masks
        except Exception as e:
            print("⚠️ Chyba pri načítaní masiek:", e)
    return []

def clear_masks():
    """Odstráni všetky masky."""
    if os.path.exists(MASKS_FILE):
        try:
            os.remove(MASKS_FILE)
            print("🧹 masks.yaml odstránený.")
        except Exception as e:
            print("⚠️ Chyba pri mazaní masks.yaml:", e)
