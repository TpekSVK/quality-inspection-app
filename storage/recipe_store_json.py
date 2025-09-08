# storage/recipe_store_json.py
import json, time, os, shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
import shutil


class RecipeStoreJSON:
    """
    ELI5: Recept je JSON. Pri uložení vytvoríme novú verziu s timestampom
    a 'current.json' nastavíme na túto verziu.
    Na Windows nerobíme symlink (môže byť bloknutý), ale skúšame poradie:
    symlink -> hardlink -> copy (fallback).
    """

    def __init__(self, root: str = "recipes"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _recipe_dir(self, name: str) -> Path:
        p = self.root / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _atomic_write_json(self, path: Path, data: Dict[str, Any]):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        # atomic replace kde to OS podporuje
        os.replace(tmp, path)

    def save_version(self, name: str, data: Dict[str, Any]) -> str:
        d = self._recipe_dir(name)
        ts = time.strftime("%Y%m%d-%H%M%S")
        version_file = d / f"{name}_{ts}.json"

        # 1) zapíš novú verziu atómovo
        self._atomic_write_json(version_file, data)

        # 2) nastav current.json bez symlinkov (Windows safe)
        current = d / "current.json"
        try:
            if current.exists() or current.is_symlink():
                current.unlink()
        except Exception:
            pass

        # pokus o symlink (na Win zvyčajne zlyhá bez práv)
        try:
            # relatívny cieľ (krajší v repo)
            os.symlink(version_file.name, current)
        except Exception:
            # hardlink → copy fallback
            try:
                os.link(version_file, current)
            except Exception:
                shutil.copy2(version_file, current)

        return str(version_file)

    def load(self, name: str, version: Optional[str] = None) -> Dict[str, Any]:
        d = self._recipe_dir(name)
        if version is None or version == "current":
            p = d / "current.json"
        else:
            # ak priletí už celý názov súboru, použi ho; inak zostav z name+timestamp
            vv = Path(version)
            p = vv if vv.is_file() else d / f"{name}_{version}.json"
        if not p.exists():
            raise FileNotFoundError(f"Recept neexistuje: {p}")
        return json.loads(p.read_text(encoding="utf-8"))

    def list_versions(self, name: str) -> List[str]:
        d = self._recipe_dir(name)
        files = sorted([f.name for f in d.glob(f"{name}_*.json")])
        return files

    def latest_version_path(self, name: str) -> Optional[str]:
        items = self.list_versions(name)
        return str(self.root / name / items[-1]) if items else None
   
    def list_names(self):
        """
        Vráti zoznam názvov receptov (mená priečinkov v self.root),
        ktoré obsahujú aspoň 1 JSON (verziu) alebo current.json.
        """
        names = []
        for p in self.root.iterdir():
            if not p.is_dir():
                continue
            has_json = any((p / "current.json").exists() or list(p.glob("*.json")))
            if has_json:
                names.append(p.name)
        return sorted(names)
   
    def delete(self, name: str) -> bool:
        """
        Zmaže celý priečinok receptu: recipes/<name>
        Vracia True ak sa podarilo, inak False.
        Bezpečnostné kontroly proti '..' a separátorom.
        """
        if not name:
            return False
        if "/" in name or "\\" in name or ".." in name:
            return False
        p = self.root / name
        if p.exists() and p.is_dir():
            shutil.rmtree(p)
            return True
        return False
