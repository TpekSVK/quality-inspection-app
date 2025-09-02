# storage/recipe_router.py
import json
from pathlib import Path
from typing import Optional, Dict

class RecipeRouter:
    def __init__(self, root: str = "recipes"):
        self.root = Path(root)
        self.ids_path = self.root/"index_ids.json"
        self.codes_path = self.root/"index_codes.json"
        self._ids = {}
        self._codes = {}
        self._load()

    def _load(self):
        if self.ids_path.exists():
            self._ids = json.loads(self.ids_path.read_text(encoding="utf-8"))
        if self.codes_path.exists():
            self._codes = json.loads(self.codes_path.read_text(encoding="utf-8"))

    def save(self):
        self.ids_path.write_text(json.dumps(self._ids, ensure_ascii=False, indent=2), encoding="utf-8")
        self.codes_path.write_text(json.dumps(self._codes, ensure_ascii=False, indent=2), encoding="utf-8")

    def set_id(self, plc_id: int, recipe_name: str):
        self._ids[str(int(plc_id))] = recipe_name

    def set_code(self, code: str, recipe_name: str):
        self._codes[str(code)] = recipe_name

    def resolve_by_id(self, plc_id: int) -> Optional[str]:
        return self._ids.get(str(int(plc_id)))

    def resolve_by_code(self, code: str) -> Optional[str]:
        return self._codes.get(str(code))
