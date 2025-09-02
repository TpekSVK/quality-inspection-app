# io/plc/plc_qt_controller.py
import time
from typing import Callable, Dict, Any
from io.plc.modbus_server import ModbusApp
from config.plc_map import *

TRIGGER_COIL_ADDR = 20  # dohodnuté v predošlej časti

class PLCQtController:
    def __init__(self, host="0.0.0.0", port=5020):
        self.mb = ModbusApp(host=host, port=port)
        self.mb.start()
        self.ok_count = 0
        self.nok_count = 0
        self._hb = 0
        self._last_trig = 0

        # init flags
        self.mb.set_coil(CO_READY, True)
        self.mb.set_coil(CO_BUSY, False)
        self.mb.set_coil(CO_RESULT_OK, False)
        self.mb.set_coil(CO_RESULT_NOK, False)
        self.mb.set_coil(CO_ERROR, False)
        self.mb.set_hr(HR_OK_COUNT, 0)
        self.mb.set_hr(HR_NOK_COUNT, 0)

    def tick(self, on_capture_and_process: Callable[[], Dict[str,Any]]):
        # heartbeat
        self._hb ^= 1
        self.mb.set_coil(CO_HEARTBEAT, self._hb)

        # Trigger edge
        trig = 0
        try:
            trig = self.mb.get_coil(TRIGGER_COIL_ADDR)
        except:
            trig = 0

        if trig and not self._last_trig:
            # začiatok cyklu
            self.mb.set_coil(CO_READY, False)
            self.mb.set_coil(CO_BUSY, True)
            self.mb.set_coil(CO_TRIGGER_ACK, True)

            t0 = time.perf_counter()
            res = on_capture_and_process()  # { ok, elapsed_ms, results:[...] }
            elapsed_ms = (time.perf_counter() - t0)*1000.0
            self.mb.set_hr(HR_CYCLE_MS, int(elapsed_ms))

            ok = bool(res.get("ok", False))
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

            # Measures[0..] – prvých 10
            for i in range(10):
                self.mb.set_hr(HR_MEASURES_0 + i, 0)
            for i, r in enumerate(res.get("results", [])[:10]):
                try:
                    val = int(round(float(getattr(r, "measured", 0.0))))
                except:
                    val = 0
                self.mb.set_hr(HR_MEASURES_0 + i, val)

            # koniec cyklu
            self.mb.set_coil(CO_TRIGGER_ACK, False)
            self.mb.set_coil(CO_BUSY, False)
            self.mb.set_coil(CO_READY, True)

        self._last_trig = trig
