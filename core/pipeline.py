# core/pipeline.py
import time
from typing import List, Dict, Optional
import numpy as np
from .tools.base_tool import BaseTool, ToolResult



class Pipeline:
    """
    Orchestruje: fixtúra -> tools -> verdict.
    """
    def __init__(self, tools: List[BaseTool], fixture, pxmm: Optional[Dict] = None):
        self.tools = tools
        self.fixture = fixture  # objekt s .estimate_transform(img)->np.ndarray
        self.pxmm = pxmm or {}

    def process(self, img_ref: np.ndarray, img_cur: np.ndarray) -> Dict:
        t0 = time.perf_counter()
        H = self.fixture.estimate_transform(img_cur) if self.fixture else None

        results: List[ToolResult] = []
        for tool in self.tools:
            r = tool.run(img_ref, img_cur, H)
            results.append(r)

        verdict = all(r.ok for r in results)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "ok": verdict,
            "elapsed_ms": elapsed_ms,
            "results": results,
            "fixture": {"H": H.tolist() if isinstance(H, np.ndarray) else None}
        }
