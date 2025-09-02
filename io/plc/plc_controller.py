# io/plc/plc_controller.py
import time
from typing import Callable, Dict, Any, Optional
from .modbus_server import ModbusApp
from config.plc_map import *

class PLCController:
    """
    ELI5: Sledujeme PLC Trigger, spúšťame pipeline, zapisujeme výsledok do registrov.
    App je Modbus/TCP slave (server).
    """
    def __init__(self, modbus: ModbusApp, on_capture_and_process: Callable[[], Dict[str,Any]]):
        self.mb = modbus
        self.on_capture_and_process = on_capture_and_process
        self.ok_count = 0
        self.nok_count = 0
        self.last_cycle_ms = 0.0

    def set_ready(self, val: bool):
        self.mb.set_coil(CO_READY, val)

    def loop(self, poll_ms: int = 5):
        hb = 0
        self.set_ready(True)
        while True:
            # heartbeat
            hb ^= 1
            self.mb.set_coil(CO_HEARTBEAT, hb)

            # Trigger je na PLC strane typicky výstup -> tu očakávame napr. coil 20 (dohodnúť)
            # Pre jednoduchosť si zoberieme Holding register HR_RECIPE_ID (prepínanie receptu)
            # a Trigger coil na adrese 20 (doplň do servera/PLC).
            try:
                trig = self.mb.get_coil(20)
            except:
                trig = 0

            if trig:
                self.mb.set_coil(CO_READY, False)
                self.mb.set_coil(CO_BUSY, True)
                self.mb.set_coil(CO_TRIGGER_ACK, True)

                t0 = time.perf_counter()
                result = self.on_capture_and_process()  # { ok, elapsed_ms, results:[ToolResult-like] }
                self.last_cycle_ms = (time.perf_counter() - t0)*1000.0
                self.mb.set_hr(HR_CYCLE_MS, int(self.last_cycle_ms))

                ok = bool(result.get("ok", False))
                if ok:
                    self.ok_count += 1
                    self.mb.set_coil(CO_RESULT_OK, True)
                    self.mb.set_coil(CO_RESULT_NOK, False)
                    self.mb.set_hr(HR_RESULT_CODE, 0)
                else:
                    self.nok_count += 1
                    self.mb.set_coil(CO_RESULT_OK, False)
                    self.mb.set_coil(CO_RESULT_NOK, True)
                    self.mb.set_hr(HR_RESULT_CODE, 1)

                self.mb.set_hr(HR_OK_COUNT, self.ok_count)
                self.mb.set_hr(HR_NOK_COUNT, self.nok_count)

                # vyplnenie Measures[0..] – uložíme measured prvé 10 tools
                measures = []
                for i, r in enumerate(result.get("results", [])[:10]):
                    measures.append(int(r.measured) if isinstance(r.measured, (int,)) else int(round(float(r.measured))))
                for i, v in enumerate(measures):
                    self.mb.set_hr(HR_MEASURES_0 + i, v)

                # koniec cyklu
                self.mb.set_coil(CO_TRIGGER_ACK, False)
                self.mb.set_coil(CO_BUSY, False)
                self.mb.set_coil(CO_READY, True)

            time.sleep(poll_ms/1000.0)
