import cam 
import relais as rpi


wrong_code = "Falscher Code. Bitte erneut versuchen."
swipe_text = "Zum Entsperren wischen"

def clear_cache():
    # Trigger Reboot
    rpi.DOWN(seconds=5)
    rpi.PWR(seconds=5)
    rpi.switch_usb(mode="usb")  # switch to USB mode for recovery
    rpi.UP(seconds=5)
    rpi.PWR(seconds=5)
    for i in range(5):
        rpi.DOWN()
    rpi.PWR()
    rpi.DOWN()
    rpi.PWR()
    rpi.switch_usb(mode="otg")  # switch back to OTG mode
    rpi.cleanup()

def get_timeout():
    text = cam.get_text('Info_text')  # uses default timeout internally
    text = ''.join(ch for ch in (text or '') if ch.isdigit())    # keep only numeric digits
    if text:
        return int(text)
    
def wrong_code_detected():
    if cam.get_text('Info_text') == wrong_code:
        return True
    else:
        return False
    
def check_swipe():
    if cam.check('Swipe', threshold=0.8) == swipe_text:
        return True
    else:
        return False

def next_digit(count, line=0):
    try:
        with open(f"digits/{count}digit.txt", "r", encoding="utf-8") as f:
            total_lines = len(f.readlines()) - 1  # account for header/offset used elsewhere
    except FileNotFoundError:
        return False

    if line == total_lines:
        return "done"
    
    with open(f"digits/{count}digit.txt") as f:
        digit = f.readlines()[line + 1].strip()
    return digit
        

