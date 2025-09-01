# app_logic.py
import os
import glob
import datetime

class AppLogic:
    def __init__(self, dataset_dir="dataset"):
        self.dataset_dir = dataset_dir

        # Prevádzkové snímky držme mimo tréningového datasetu
        self.captures_dir = os.path.join("captures")
        self.ok_dir = os.path.join(self.captures_dir, "OK")
        self.nok_dir = os.path.join(self.captures_dir, "NOK")
        os.makedirs(self.ok_dir, exist_ok=True)
        os.makedirs(self.nok_dir, exist_ok=True)

        self.recent_photos = self.load_recent_photos()

    # ---------------- Fotky ----------------
    def load_recent_photos(self):
        photos = []
        for folder, kind in [(self.ok_dir, "OK"), (self.nok_dir, "NOK")]:
            files = glob.glob(os.path.join(folder, "*.*"))
            for f in files:
                try:
                    mtime = os.path.getmtime(f)
                except OSError:
                    continue
                photos.append((f, kind, mtime))
        photos.sort(key=lambda x: x[2], reverse=True)
        return [(f, kind) for f, kind, _ in photos][:50]

    def save_photo(self, frame, kind):
        import cv2
        filename = f"{kind}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        folder = self.ok_dir if kind == "OK" else self.nok_dir
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, filename)
        cv2.imwrite(path, frame)
        self.recent_photos.insert(0, (path, kind))
        if len(self.recent_photos) > 50:
            self.recent_photos.pop()
        return path
