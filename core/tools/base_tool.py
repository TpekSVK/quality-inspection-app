from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Tuple, Optional
import numpy as np

@dataclass
class ToolResult:
    ok: bool
    measured: float
    lsl: Optional[float]
    usl: Optional[float]
    details: Dict[str, Any]   # napr. plocha_blobov, count, bboxy
    overlay: Optional[np.ndarray] = None  # voliteľná grafika do overlay

class BaseTool(ABC):
    """Všetky tools majú jednotné API a per-ROI nastavenia."""
    def __init__(self, name: str, roi_xywh: Tuple[int,int,int,int], params: Dict[str, Any], lsl=None, usl=None, units: str="px"):
        self.name = name
        self.roi_xywh = roi_xywh
        self.params = params
        self.lsl = lsl
        self.usl = usl
        self.units = units

    @abstractmethod
    def run(self, img_ref: np.ndarray, img_cur: np.ndarray, fixture_transform: Optional[np.ndarray]) -> ToolResult:
        """
        img_ref: referenčná fotka (Teach)
        img_cur: aktuálny snímok (Run)
        fixture_transform: 3x3 homogénna matica (alebo None)
        """
        ...
