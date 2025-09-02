# config/plc_map.py
# Modbus map (zero-based addressing, ako v našom serveri)

# Coils (co)
CO_READY       = 0
CO_BUSY        = 1
CO_TRIGGER_ACK = 2
CO_RESULT_OK   = 3
CO_RESULT_NOK  = 4
CO_ERROR       = 5
CO_HEARTBEAT   = 6

# Holding registers (hr)
HR_RECIPE_ID   = 0
HR_CYCLE_MS    = 1
HR_LAST_ERR    = 2
HR_OK_COUNT    = 10
HR_NOK_COUNT   = 11
HR_RESULT_CODE = 60
HR_MEASURES_0  = 20   # 20..39 vyhradených pre merania
