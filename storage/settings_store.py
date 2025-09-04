# storage/settings_store.py
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

class SettingsStore:
    def __init__(self, path: str = "settings.json"):
        self.path = Path(path)
        self.data = {"camera_profiles": [], "active_profile": None}
        self.load()

    def load(self):
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    # camera profiles
    def profiles(self) -> List[Dict[str,Any]]:
        return list(self.data.get("camera_profiles", []))

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

    def upsert_profile(self, name: str, url: str):
        found = False
        for p in self.data.get("camera_profiles", []):
            if p.get("name")==name:
                p["url"] = url; found = True; break
        if not found:
            self.data.setdefault("camera_profiles", []).append({"name":name,"url":url})
        self.data["active_profile"] = name
        self.save()

    def delete_profile(self, name: str):
        self.data["camera_profiles"] = [p for p in self.data.get("camera_profiles", []) if p.get("name") != name]
        if self.data.get("active_profile") == name:
            self.data["active_profile"] = None
        self.save()
