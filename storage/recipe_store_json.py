import json, hashlib, time
from pathlib import Path
from typing import Any, Dict, Optional, List

class RecipeStoreJSON:
    def __init__(self, root: str = "recipes"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _now_tag(self) -> str:
        return time.strftime("%Y%m%d-%H%M%S")

    def _version_path(self, name: str, tag: str) -> Path:
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{name}_{tag}.json"

    def save_version(self, name: str, recipe: Dict[str, Any]) -> str:
        tag = self._now_tag()
        p = self._version_path(name, tag)
        with p.open("w", encoding="utf-8") as f:
            json.dump(recipe, f, ensure_ascii=False, indent=2)
        # symlink current
        current = self.root / name / "current.json"
        if current.exists() or current.is_symlink():
            current.unlink()
        current.symlink_to(p.name)
        return tag

    def load(self, name: str, version: Optional[str] = None) -> Dict[str, Any]:
        if version is None:
            p = self.root / name / "current.json"
            if p.is_symlink():
                p = p.resolve()
        else:
            p = self._version_path(name, version)
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)

    def list_versions(self, name: str) -> List[str]:
        d = self.root / name
        if not d.exists(): return []
        return sorted([x.stem.split("_")[-1] for x in d.glob(f"{name}_*.json")])

    def rollback(self, name: str, version: str) -> None:
        p = self._version_path(name, version)
        current = self.root / name / "current.json"
        if current.exists() or current.is_symlink():
            current.unlink()
        current.symlink_to(p.name)
