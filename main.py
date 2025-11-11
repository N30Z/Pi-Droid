import sys
import subprocess
from pathlib import Path

#!/usr/bin/env python3
"""
Ensure pytesseract is installed, and then install requirements from py_requirements.txt.
Designed for Linux; uses the running Python interpreter's pip.
"""

import importlib.util
import shutil
from pathlib import Path

def is_installed(package_name: str) -> bool:
    return importlib.util.find_spec(package_name) is not None

def pip_install(args):
    cmd = [sys.executable, "-m", "pip", "install"] + args
    print("Running:", " ".join(cmd))
    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise SystemExit(f"pip install failed with exit code {res.returncode}")

def main():
    # Check pytesseract
    if not is_installed("pytesseract"):
        print("pytesseract not found. Installing pytesseract...")
        pip_install(["pytesseract"])
    else:
        print("pytesseract is already installed.")

    # Install from requirements file
    req = Path("py_requirements.txt")
    if not req.exists():
        print("py_requirements.txt not found in current directory:", Path.cwd())
        return

    print(f"Installing packages from {req} ...")
    pip_install(["-r", str(req)])
    print("Done.")

    # After installing packages, attempt to run setup_hid_gadget.sh if present.
    script = Path("setup_hid_gadget.sh")
    if script.exists():
        print(f"Found setup script: {script}. Attempting to run it...")
        # Prefer system 'bash' if available
        bash = shutil.which("bash")
        if bash:
            try:
                # Run the script with bash. Use check=True to raise on failure.
                res = subprocess.run([bash, str(script)], check=True)
                print(f"setup_hid_gadget.sh completed with return code {res.returncode}")
            except subprocess.CalledProcessError as e:
                print(f"ERROR: setup_hid_gadget.sh failed with exit code {e.returncode}")
        else:
            print("WARNING: 'bash' not found in PATH. Cannot run setup_hid_gadget.sh automatically.")
            print(f"You can run it manually on a Linux system: bash {script}")
    else:
        print("No setup_hid_gadget.sh found; skipping HID gadget setup.")

if __name__ == "__main__":
    main()