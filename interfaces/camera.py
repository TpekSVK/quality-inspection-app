from abc import ABC, abstractmethod
from typing import Optional, Callable, Tuple
import numpy as np

Frame = np.ndarray  # HxWxC (uint8) alebo HxW (mono)

class ICamera(ABC):
    """Jednoduché rozhranie kamery pre pipeline."""

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def start(self) -> None:
        """Spustí stream (ak je)."""

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def trigger(self) -> None:
        """HW/SW trigger (ak kamera podporuje)."""

    @abstractmethod
    def get_frame(self, timeout_ms: int = 100) -> Optional[Frame]:
        """Vráti posledný snímok (blocking do timeout)."""

    @abstractmethod
    def set_exposure(self, exposure_ms: float) -> None: ...

    @abstractmethod
    def set_gain(self, gain_db: float) -> None: ...

    @abstractmethod
    def set_trigger_mode(self, enabled: bool) -> None: ...

    def on_new_frame(self, cb: Callable[[Frame], None]) -> None:
        """Voliteľné: callback na prichádzajúce snímky (live náhľad)."""
        self._on_new_frame = cb
