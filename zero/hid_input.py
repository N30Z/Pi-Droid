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

# Common consumer (media) usage IDs from the HID Usage Tables (Consumer Page)
# These are the standard usage IDs for multimedia keys. Many HID gadget setups
# expose a separate consumer control device (e.g. /dev/hidg1) which accepts a
# 2-byte report containing the usage ID. If your gadget uses a different report
# format or a different device path, adjust the `device` parameter accordingly.
VOLUME_UP_USAGE = 0xE9
VOLUME_DOWN_USAGE = 0xEA
# Power key usage - this can vary; adjust if your gadget expects a different code.
POWER_USAGE = 0x30


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


def _send_raw_report(device: Path, data: bytes) -> None:
    """Send raw bytes to the HID device (no interpretation).

    Useful for consumer control reports which often have different report
    lengths than the keyboard (e.g. 2 bytes). This function will write the
    bytes and then write a release (zeros) if the length is >0.
    """
    dev = Path(device)
    if not dev.exists():
        raise FileNotFoundError(f"{dev} not found. Gadget not set up or not bound?")
    with open(str(dev), "wb+", buffering=0) as fd:
        fd.write(data)
        fd.flush()
        time.sleep(0.02)
        # release (send zeros of same length)
        fd.write(b"\x00" * len(data))
        fd.flush()
        time.sleep(0.02)


def send_consumer_usage(device: Path, usage: int) -> None:
    """Send a Consumer Page usage ID to the given device.

    By convention many setups expose a consumer control HID at /dev/hidg1 which
    accepts a 2-byte report containing the usage ID (low byte first). This
    helper packs the usage into 2 bytes and sends it as a press+release.
    """
    if usage < 0 or usage > 0xFFFF:
        raise ValueError("usage must be a 0..0xFFFF integer")
    lo = usage & 0xFF
    hi = (usage >> 8) & 0xFF
    _send_raw_report(device, bytes([lo, hi]))


def send_volume_up(device: Path = Path("/dev/hidg1")) -> None:
    """Send a Volume Up consumer control event to the device."""
    send_consumer_usage(device, VOLUME_UP_USAGE)


def send_volume_down(device: Path = Path("/dev/hidg1")) -> None:
    """Send a Volume Down consumer control event to the device."""
    send_consumer_usage(device, VOLUME_DOWN_USAGE)


def send_power(device: Path = Path("/dev/hidg1")) -> None:
    """Send a Power button event. Usage ID may vary by platform/gadget.

    If this doesn't perform the expected action, check your HID report
    descriptor and adjust POWER_USAGE or the target device path.
    """
    send_consumer_usage(device, POWER_USAGE)


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