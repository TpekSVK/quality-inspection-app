# config/plc_map.py
# ELI5: mapovanie Modbus adries pre PLC handshake
CO_READY       = 1
CO_BUSY        = 2
CO_TRIGGER_ACK = 3
CO_RESULT_OK   = 4
CO_RESULT_NOK  = 5
CO_ERROR       = 6
CO_HEARTBEAT   = 7

HR_RECIPE_ID   = 10
HR_RESULT_CODE = 11
HR_CYCLE_MS    = 12
HR_OK_COUNT    = 13
HR_NOK_COUNT   = 14
HR_MEASURES_0  = 100  # prvých 10 meraní: 100..109
