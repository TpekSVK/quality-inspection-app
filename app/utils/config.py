from dataclasses import dataclass

@dataclass
class AppConfig:
    model_path: str = "models/best.pt"
    camera_index: int = 0
