#!/usr/bin/env python3
"""
hid_type_numbers.py

This module provides a small HID typer for digits. It's intended to be
imported and used from a main script. The module exposes a HIDTyper class
and a convenience function `type_numbers_on_device`.

Example usage:
    from hid_type_numbers import HIDTyper
    typer = HIDTyper(Path('/dev/hidg0'))
    typer.type_numbers('12345')

The module raises exceptions on errors (FileNotFoundError, ValueError) so
callers can handle them. A minimal CLI is provided for convenience.
"""

from pathlib import Path
import time
from typing import Iterable

# HID keycodes (usage IDs) für Zahlen über das Hauptlayout (nicht Numpad)
NUM_KEYCODES = {
    '1': 0x1E, '2': 0x1F, '3': 0x20, '4': 0x21, '5': 0x22,
    '6': 0x23, '7': 0x24, '8': 0x25, '9': 0x26, '0': 0x27
}
ENTER_KEYCODE = 0x28


class HIDTyper:
    """Type digits to a HID gadget device (e.g. /dev/hidg0).

    Methods raise exceptions instead of calling sys.exit so this file can be
    imported and used from other scripts.
    """

    def __init__(self, device: Path = Path('/dev/hidg0')):
        self.device = Path(device)

    def _send_report(self, fd, modifier: int, keycodes: Iterable[int]):
        # Report: [modifier, reserved, k1..k6] length = 8
        report = bytes([modifier, 0x00] + list(keycodes) + [0x00] * (6 - len(list(keycodes))))
        fd.write(report)
        fd.flush()

    def _press_key(self, fd, keycode: int, modifier: int = 0) -> None:
        self._send_report(fd, modifier, [keycode])
        time.sleep(0.02)
        # release
        self._send_report(fd, 0x00, [])
        time.sleep(0.02)

    def type_numbers(self, s: str, delay: float = 0.03, press_enter: bool = True) -> None:
        """Type the digits in `s` to the HID device.

        Raises:
            FileNotFoundError: if the device path does not exist.
            ValueError: if `s` contains non-digit characters.
        """
        if not self.device.exists():
            raise FileNotFoundError(f"{self.device} not found. Gadget not set up or not bound?")

        if not s.isdigit():
            raise ValueError("Only digits (0-9) are allowed in the input string")

        # open as binary write, unbuffered
        with open(str(self.device), "wb+", buffering=0) as fd:
            for ch in s:
                keycode = NUM_KEYCODES[ch]
                self._press_key(fd, keycode)
                time.sleep(delay)
            if press_enter:
                self._press_key(fd, ENTER_KEYCODE)


def type_numbers_on_device(device: Path, numbers: str, delay: float = 0.03) -> None:
    """Convenience wrapper: create a HIDTyper and send numbers."""
    typer = HIDTyper(device)
    typer.type_numbers(numbers, delay=delay)


if __name__ == "__main__":
    # Minimal CLI kept for convenience when running the module directly.
    import argparse
    parser = argparse.ArgumentParser(description="Type digits to a HID gadget device and press Enter.")
    parser.add_argument('numbers', help='Digits to type (0-9)')
    parser.add_argument('--device', '-d', default='/dev/hidg0', help='HID device path')
    parser.add_argument('--no-enter', action='store_true', help="Don't append Enter at the end")
    args = parser.parse_args()
    typer = HIDTyper(Path(args.device))
    print("Sende:", args.numbers, "-> mit Enter am Ende" if not args.no_enter else "(kein Enter)")
    try:
        typer.type_numbers(args.numbers, press_enter=not args.no_enter)
    except Exception as e:
        # Print error and exit with non-zero status for CLI usage
        print("Fehler:", e)
        raise SystemExit(1)
    print("Fertig.")