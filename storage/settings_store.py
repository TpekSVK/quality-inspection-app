# storage/settings_store.py
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

DEFAULTS: Dict[str, Any] = {
    "camera_profiles": [],
    "active_profile": None,
    "ui": {
        "theme": "dark"  # "dark" alebo "light"
    }
}

class SettingsStore:
    def __init__(self, path: str = "settings.json"):
        self.path = Path(path)
        self.data: Dict[str, Any] = {}
        self.load()

    def _merge_defaults(self, data: Dict[str, Any]) -> Dict[str, Any]:
        def merge(d: Dict[str, Any], ref: Dict[str, Any]) -> Dict[str, Any]:
            for k, v in ref.items():
                if k not in d:
                    d[k] = v
                elif isinstance(v, dict) and isinstance(d.get(k), dict):
                    d[k] = merge(d[k], v)
            return d
        return merge(data or {}, json.loads(json.dumps(DEFAULTS)))

    def load(self):
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}
        else:
            self.data = {}
        self.data = self._merge_defaults(self.data)

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- UI: téma ---
    def get_ui_theme(self) -> str:
        return (self.data.get("ui") or {}).get("theme", "dark")

    def set_ui_theme(self, theme: str):
        self.data.setdefault("ui", {})["theme"] = (theme or "dark").lower()
        self.save()

    # --- camera profiles ---
    def profiles(self) -> List[Dict[str,Any]]:
        # doplníme default "type" pre staršie profily
        profs = []
        for p in self.data.get("camera_profiles", []):
            q = dict(p)
            if "type" not in q or not q["type"]:
                q["type"] = "RTSP (OpenCV/FFmpeg)"
            profs.append(q)
        return profs


    def set_profiles(self, profiles: List[Dict[str,Any]]):
        self.data["camera_profiles"] = profiles
        self.save()

    def set_active(self, name: Optional[str]):
        self.data["active_profile"] = name
        self.save()

    def get_active(self) -> Optional[Dict[str,Any]]:
        name = self.data.get("active_profile")
        for p in self.data.get("camera_profiles", []):
            if p.get("name") == name:
                return p
        return None

    def upsert_profile(self, name: str, url: str, cam_type: Optional[str] = None):
        cam_type = cam_type or "RTSP (OpenCV/FFmpeg)"
        found = False
        for p in self.data.get("camera_profiles", []):
            if p.get("name") == name:
                p["url"] = url
                p["type"] = cam_type
                found = True
                break
        if not found:
            self.data.setdefault("camera_profiles", []).append({
                "name": name, "url": url, "type": cam_type
            })
        self.data["active_profile"] = name
        self.save()


    def delete_profile(self, name: str):
        self.data["camera_profiles"] = [p for p in self.data.get("camera_profiles", []) if p.get("name") != name]
        if self.data.get("active_profile") == name:
            self.data["active_profile"] = None
        self.save()
