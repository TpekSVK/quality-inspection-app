# annotation/roi_manager.py
import os
import yaml

ROI_FILE = os.path.join("dataset", "roi.yaml")

def save_roi(x1, y1, x2, y2):
    os.makedirs("dataset", exist_ok=True)
    roi_data = {"roi": [int(x1), int(y1), int(x2), int(y2)]}
    with open(ROI_FILE, "w") as f:
        yaml.safe_dump(roi_data, f)
    print(f"📄 ROI uložené: {roi_data}")

def load_roi():
    if os.path.exists(ROI_FILE):
        try:
            with open(ROI_FILE, "r") as f:
                data = yaml.safe_load(f)
            return tuple(data.get("roi", []))
        except Exception as e:
            print("⚠️ Chyba pri načítaní ROI:", e)
    return None

def clear_roi():
    """Vymaže uloženú ROI."""
    if os.path.exists(ROI_FILE):
        try:
            os.remove(ROI_FILE)
            print("🧹 roi.yaml odstránený.")
        except Exception as e:
            print("⚠️ Chyba pri mazaní roi.yaml:", e)
