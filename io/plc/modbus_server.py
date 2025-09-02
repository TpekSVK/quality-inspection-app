from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.datastore import ModbusSequentialDataBlock
from pymodbus.device import ModbusDeviceIdentification
from threading import Thread
from typing import Callable

class ModbusApp:
    def __init__(self, host="0.0.0.0", port=5020):
        # coils, discrete inputs, holding, input registers
        self.store = ModbusSlaveContext(
            di=ModbusSequentialDataBlock(0,  [0]*100),
            co=ModbusSequentialDataBlock(0,  [0]*100),
            hr=ModbusSequentialDataBlock(0,  [0]*200),
            ir=ModbusSequentialDataBlock(0,  [0]*200),
            zero_mode=True
        )
        self.ctx = ModbusServerContext(slaves=self.store, single=True)
        self.host, self.port = host, port
        self._thread = None

    def start(self):
        def _run():
            StartTcpServer(context=self.ctx, address=(self.host, self.port))
        self._thread = Thread(target=_run, daemon=True)
        self._thread.start()

    # convenient setters/getters
    def set_coil(self, addr, val): self.store.setValues(1, addr, [1 if val else 0])
    def get_coil(self, addr): return self.store.getValues(1, addr, count=1)[0]
    def set_hr(self, addr, val): self.store.setValues(3, addr, [int(val)])
    def get_hr(self, addr): return self.store.getValues(3, addr, count=1)[0]
