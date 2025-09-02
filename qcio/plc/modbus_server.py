# qcio/plc/modbus_server.py
# Minimal "fake" Modbus server, aby GUI/PLC mód fungoval bez závislostí.
# Neskôr to vieš nahradiť reálnym pymodbus serverom.

class ModbusApp:
    def __init__(self, host="0.0.0.0", port=5020):
        self._coils = {}        # bitové flagy
        self._hrs = {}          # holding registre (int)
        self.host = host
        self.port = port

    def start(self):
        # reálny server by sa tu spúšťal; pre stub netreba
        pass

    # Coils
    def set_coil(self, addr: int, val: int | bool):
        self._coils[int(addr)] = 1 if val else 0

    def get_coil(self, addr: int) -> int:
        return int(self._coils.get(int(addr), 0))

    # Holding Registers
    def set_hr(self, addr: int, val: int):
        self._hrs[int(addr)] = int(val)

    def get_hr(self, addr: int) -> int:
        return int(self._hrs.get(int(addr), 0))
