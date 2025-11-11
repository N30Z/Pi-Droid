
import relais as rpi
rpi.UP()    # perform a press on the UP servo
rpi.DOWN()  # perform a press on the DOWN servo
rpi.PWR()   # perform a press on the PWR servo
rpi.cleanup()

def reboot_to_recovery():
    """Reboot the device into recovery mode."""
    rpi.UP()
    rpi.PWR()



def clear_cache():