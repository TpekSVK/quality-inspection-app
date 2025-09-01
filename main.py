### main.py
import sys
import cv2

try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
except Exception:
    pass

from PySide6.QtWidgets import QApplication
from gui_main import QualityApp


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QualityApp()
    window.show()
    sys.exit(app.exec())
