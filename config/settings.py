### settings.py
from PySide6.QtCore import QSettings

def load_credentials():
    settings = QSettings("MojaFirma", "LowBudgetKeyence")
    ip = settings.value("ip", "192.168.0.104")
    username = settings.value("username", "admin")
    password = settings.value("password", "")
    return ip, username, password

def save_credentials(ip, username, password):
    settings = QSettings("MojaFirma", "LowBudgetKeyence")
    settings.setValue("ip", ip)
    settings.setValue("username", username)
    settings.setValue("password", password)
