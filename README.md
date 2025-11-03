# GMC geigercounter to MQTT

## Architecture
Der GMC geigercounter to MQTT soll per USB tty einen Geigerzähler von GMC auslesen.
Mindestens mit dem GMC-800 v1.10 MUSS es funktionieren, mit anderen neueren GMC Geräten
SOLL es funktionieren.
Das Protokoll ist in @GQ-RFC1801.txt spezifiziert.
Der ausgelesene CPS Wert soll per MQTT publiziert werden.
Empfänger ist im ersten Schritt ein Homeassistant Server, aber ggf. kommen später noch andere
Consumer hinzu.
Wenn möglich soll der Sensor in Homeassistant automatisch discovered werden wie man es z.B.
von zigbee2mqtt in zusammenhang mit Homeassistant kennt.

Das tty Gerät, sowie MQTT broker (host, port, user, password) sollen in einer config.yaml Datei
gespeichert werden.

## minimal code example
```python
import serial
s = serial.Serial('/dev/ttyUSB0', 115200, timeout=2, write_timeout=2,
                  rtscts=False, dsrdtr=False, xonxoff=False)
# DTR/RTS aktivieren (manche CH340 brauchen High)
s.setDTR(True); s.setRTS(True)
s.reset_input_buffer()
s.write(b"<GETVER>>")
print("Reply:", s.read(64))
```
Reply: b'GMC-800Re1.10'
