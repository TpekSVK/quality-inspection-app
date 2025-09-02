# core/tools/anomaly_utils.py
import numpy as np
from typing import List, Dict

def percentile_threshold(samples: List[float], target_fpr: float = 0.003) -> float:
    """
    ELI5: z listu OK-hodnôt vyberieme taký prah, aby len ~0.3% OK padali nad prah (falošné poplachy).
    target_fpr=0.003 => 99.7. percentil.
    """
    if len(samples) == 0:
        return 0.0
    q = 100.0 * (1.0 - target_fpr)
    return float(np.percentile(np.array(samples, dtype=np.float32), q))
