# ui_style.py
TOOLBUTTON = """
QToolButton {
  background: #2b2b2b;
  color: #ffffff;
  border: 1px solid #3a3a3a;
  border-radius: 8px;
  padding: 6px 10px;
}
QToolButton:hover { background: #333333; }
QToolButton:checked {
  background: #4caf50;
  border-color: #4caf50;
  color: #ffffff;
}
"""

PRIMARY_BUTTON = """
QToolButton {
  background: #2962ff;
  color: #ffffff;
  border: 1px solid #1e40ff;
  border-radius: 8px;
  padding: 8px 14px;
}
QToolButton:hover { background: #1f54ff; }
QToolButton:disabled { background: #555; color: #bbb; border-color: #666; }
"""
