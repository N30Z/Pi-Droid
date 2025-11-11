#!/bin/bash
set -euo pipefail

GADGET_DIR=/sys/kernel/config/usb_gadget/hidg1

if [ "$(id -u)" -ne 0 ]; then
  echo "Bitte als root ausführen (sudo)."
  exit 1
fi

modprobe libcomposite

# falls schon vorhanden -> entfernen (sauber neu erstellen)
if [ -d "$GADGET_DIR" ]; then
  echo "Vorhandenes Gadget wird entfernt..."
  if [ -f "$GADGET_DIR/UDC" ]; then
    echo "" > "$GADGET_DIR/UDC" || true
  fi
  rm -rf "$GADGET_DIR"
fi

mkdir -p "$GADGET_DIR"
cd "$GADGET_DIR"

# IDs (Linux Foundation vendor ID als konservativer default)
echo 0x1d6b > idVendor
echo 0x0104 > idProduct
echo 0x0100 > bcdDevice
echo 0x0200 > bcdUSB

mkdir -p strings/0x409
echo "Raspberry Pi" > strings/0x409/manufacturer
echo "Pi HID Keyboard" > strings/0x409/product
echo "0001" > strings/0x409/serialnumber

mkdir -p configs/c.1
mkdir -p configs/c.1/strings/0x409
echo "Config 1" > configs/c.1/strings/0x409/configuration
echo 250 > configs/c.1/MaxPower

# Standard Keyboard Report Descriptor (HID)
# Modifier, Reserved, 6 Keycodes
# Wir schreiben binär mit echo -ne
mkdir -p functions/hid.usb0
echo 1 > functions/hid.usb0/protocol
echo 1 > functions/hid.usb0/subclass
echo 8 > functions/hid.usb0/report_length

# report descriptor bytes
echo -ne '\x05\x01\x09\x06\xa1\x01\x05\x07\x19\xe0\x29\xe7\x15\x00\x25\x01\x75\x01\x95\x08\x81\x02\x95\x01\x75\x08\x81\x03\x95\x06\x75\x08\x15\x00\x25\x65\x05\x07\x19\x00\x29\x65\x81\x00\xc0' > functions/hid.usb0/report_desc

# verknüpfen und aktivieren
ln -s functions/hid.usb0 configs/c.1/
UDC=$(ls /sys/class/udc | head -n1)
if [ -z "$UDC" ]; then
  echo "Keine UDC gefunden. Prüfe, ob dein Pi OTG unterstützt und das dwc2 overlay aktiv ist."
  exit 1
fi

echo "$UDC" > UDC

echo "HID gadget erstellt und an UDC $UDC gebunden."
echo "/dev/hidg0 sollte nun vorhanden sein (auf dem Pi)."
