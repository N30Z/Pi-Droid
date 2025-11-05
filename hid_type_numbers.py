#!/usr/bin/env python3
"""
hid_type_numbers.py

Nimmt ein einziges Argument (nur Ziffern). Tippt die Ziffern nacheinander
und sendet abschließend Enter. Nur Ziffern erlaubt; sonst Fehler.

Aufruf: sudo ./hid_type_numbers.py 12345
"""
import sys
import time
from pathlib import Path

HID_DEV = Path("/dev/hidg0")

# HID keycodes (usage IDs) für Zahlen über das Hauptlayout (nicht Numpad)
NUM_KEYCODES = {
    '1': 0x1E, '2': 0x1F, '3': 0x20, '4': 0x21, '5': 0x22,
    '6': 0x23, '7': 0x24, '8': 0x25, '9': 0x26, '0': 0x27
}
ENTER_KEYCODE = 0x28

def send_report(fd, modifier, keycodes):
    # Report: [modifier, reserved, k1..k6] length = 8
    report = bytes([modifier, 0x00] + keycodes + [0x00] * (6 - len(keycodes)))
    fd.write(report)
    fd.flush()

def press_key(fd, keycode, modifier=0):
    send_report(fd, modifier, [keycode])
    time.sleep(0.02)
    # release
    send_report(fd, 0x00, [])
    time.sleep(0.02)

def type_numbers(s):
    if not HID_DEV.exists():
        print(f"{HID_DEV} nicht gefunden. Gadget nicht eingerichtet oder nicht gebunden?")
        sys.exit(2)

    # nur Ziffern erlauben
    if not s.isdigit():
        print("Fehler: Nur Ziffern (0-9) als Argument erlaubt.")
        sys.exit(3)

    # open als binär write
    with open(str(HID_DEV), "wb+", buffering=0) as fd:
        for ch in s:
            keycode = NUM_KEYCODES[ch]
            press_key(fd, keycode)
            # kleine Pause zwischen den Tasten — anpassbar
            time.sleep(0.03)
        # abschließend Enter
        press_key(fd, ENTER_KEYCODE)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: sudo hid_type_numbers.py <numbers>")
        sys.exit(1)
    numbers = sys.argv[1]
    print("Sende:", numbers, "-> mit Enter am Ende")
    type_numbers(numbers)
    print("Fertig.")