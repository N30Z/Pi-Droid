"""relais.py

Importable servo controller for three servos named UP, DOWN and PWR.

Features:
- Non-blocking API: calling `UP()`, `DOWN()` or `PWR()` starts the action in a
  background thread and returns immediately with the Thread object (or
  ``False`` if the servo is not configured).
- Per-servo locking prevents overlapping movements on the same servo.
- Safe dummy GPIO implementation for development on non-RPi systems.

Typical usage:
    import relais
    relais.setup(up_pin=17, down_pin=27, pwr_pin=22)
    t = relais.UP(seconds=0.3)
    # do other work while servo moves; optionally wait for completion
    if t:
        t.join()
    relais.cleanup()

The module defaults use BCM pin numbering. See function docstrings for details.
"""

import time
import threading
from typing import Optional, Set


# Try to import RPi.GPIO, else provide a harmless dummy for testing on non-Pi systems
try:
    import RPi.GPIO as GPIO  # type: ignore
    _HAS_GPIO = True
except Exception:
    _HAS_GPIO = False

    class _DummyGPIO:
        # Use concrete integer values to better match RPi.GPIO constants and
        # keep static analysis tools happy. These are only used on non-Pi
        # systems where the real RPi.GPIO is unavailable.
        BOARD = 10
        BCM = 11
        OUT = 1

        def setwarnings(self, flag): pass
        def setmode(self, mode): pass
        def setup(self, pin, mode): pass
        def PWM(self, pin, freq):
            class _PWM:
                def __init__(self): pass
                def start(self, duty): pass
                def ChangeDutyCycle(self, duty): pass
                def stop(self): pass
            return _PWM()
        def cleanup(self): pass

    GPIO = _DummyGPIO()  # type: ignore

# Default pins (BCM numbering)
_DEFAULT_PINS = {"UP": 17, "DOWN": 27, "PWR": 22}

# PWM / servo calibration defaults (these usually work for many SG90-like servos)
_DEFAULT_FREQ = 50.0
_MIN_DUTY = 2.5    # corresponds approx to 0 degrees
_MAX_DUTY = 12.5   # corresponds approx to 180 degrees
_REST_ANGLE = 90   # neutral / idle position


class _Servo:
    def __init__(self, pin: int, freq: float = _DEFAULT_FREQ,
                 min_duty: float = _MIN_DUTY, max_duty: float = _MAX_DUTY):
        self.pin = pin
        self.freq = freq
        self.min_duty = min_duty
        self.max_duty = max_duty
        self._pwm = None
        if pin is not None:
            GPIO.setup(pin, GPIO.OUT)
            self._pwm = GPIO.PWM(pin, freq)
            self._pwm.start(0)
            # move to rest
            self.move_to_angle(_REST_ANGLE)

    def angle_to_duty(self, angle: float) -> float:
        # clamp
        if angle < 0: angle = 0
        if angle > 180: angle = 180
        return self.min_duty + (angle / 180.0) * (self.max_duty - self.min_duty)

    def move_to_angle(self, angle: float):
        if self._pwm is None:
            return
        duty = self.angle_to_duty(angle)
        self._pwm.ChangeDutyCycle(duty)
        # short settle; caller should sleep as needed

    def stop(self):
        if self._pwm is not None:
            self._pwm.stop()


# Module-level state
_gpio_initialized = False
_servos = {"UP": None, "DOWN": None, "PWR": None}
_pins = _DEFAULT_PINS.copy()

# per-servo locks to avoid overlapping movements on the same servo
_locks = {"UP": threading.Lock(), "DOWN": threading.Lock(), "PWR": threading.Lock()}

# track active worker threads so cleanup can wait for them if needed
_active_threads = set()


def setup(up_pin: Optional[int] = None, down_pin: Optional[int] = None, pwr_pin: Optional[int] = None,
          freq: float = _DEFAULT_FREQ, min_duty: float = _MIN_DUTY, max_duty: float = _MAX_DUTY) -> None:
    """
    Initialize GPIO and servos. Pins use BCM numbering.
    If a pin is None, that servo won't be initialized.
    """
    global _gpio_initialized, _servos, _pins
    if _gpio_initialized:
        return
    if up_pin is not None: _pins["UP"] = up_pin
    if down_pin is not None: _pins["DOWN"] = down_pin
    if pwr_pin is not None: _pins["PWR"] = pwr_pin

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    _servos = {
        "UP": _Servo(_pins["UP"], freq, min_duty, max_duty) if _pins.get("UP") is not None else None,
        "DOWN": _Servo(_pins["DOWN"], freq, min_duty, max_duty) if _pins.get("DOWN") is not None else None,
        "PWR": _Servo(_pins["PWR"], freq, min_duty, max_duty) if _pins.get("PWR") is not None else None,
    }
    _gpio_initialized = True


def _press_blocking(servo_key: str, press_angle: int = 60, hold: float = 0.25, rest_angle: int = _REST_ANGLE):
    """Blocking worker that actually moves the servo. Intended to run in a thread.

    This function acquires a per-servo lock so concurrent presses on the same
    servo are serialized.
    """
    if not _gpio_initialized:
        setup()  # initialize with defaults
    servo = _servos.get(servo_key)
    if servo is None:
        return False

    lock = _locks.get(servo_key)
    if lock is None:
        # fallback: no lock available
        lock = threading.Lock()

    with lock:
        servo.move_to_angle(press_angle)
        time.sleep(hold)
        servo.move_to_angle(rest_angle)
        time.sleep(0.05)
        servo.move_to_angle(0)  # optionally a short pulse or leave at rest; remove if undesired
        time.sleep(0.02)
        servo.move_to_angle(rest_angle)
    return True


def _start_press_thread(servo_key: str, press_angle: int = 60, hold: float = 0.25, rest_angle: int = _REST_ANGLE):
    """Start a background thread to run _press_blocking and return the Thread.

    Returns the Thread object on success, or False if the servo is not configured.
    """
    if not _gpio_initialized:
        setup()
    if _servos.get(servo_key) is None:
        return False

    def worker():
        try:
            _press_blocking(servo_key, press_angle=press_angle, hold=hold, rest_angle=rest_angle)
        finally:
            # remove thread from active set
            try:
                _active_threads.discard(threading.current_thread())
            except Exception:
                pass

    t = threading.Thread(target=worker)
    # non-daemon so cleanup can (optionally) join; but caller won't be blocked
    _active_threads.add(t)
    t.start()
    return t


# Exported functions named UP, DOWN, PWR per request
def UP(seconds: float = 0.25, press_angle: int = 60):
    """
    Trigger the UP servo (volume up).

    seconds: how long to hold the pressed position before returning to rest.
    press_angle: angle (degrees) to move to for the press.

    Returns a Thread object when the press was started, or False if the servo
    isn't configured.
    """
    return _start_press_thread("UP", press_angle=press_angle, hold=float(seconds))


def DOWN(seconds: float = 0.25, press_angle: int = 120):
    """
    Trigger the DOWN servo (volume down).

    seconds: how long to hold the pressed position before returning to rest.
    press_angle: angle (degrees) to move to for the press (default opposite to UP).

    Returns a Thread object when the press was started, or False if the servo
    isn't configured.
    """
    return _start_press_thread("DOWN", press_angle=press_angle, hold=float(seconds))


def PWR(seconds: float = 0.5, press_angle: int = 60):
    """
    Trigger the PWR servo (power button).

    seconds: how long to hold the pressed position before returning to rest.
    press_angle: angle (degrees) to move to for the press.

    Returns a Thread object when the press was started, or False if the servo
    isn't configured.
    """
    return _start_press_thread("PWR", press_angle=press_angle, hold=float(seconds))


__all__ = ["setup", "UP", "DOWN", "PWR", "set_rest_angle", "cleanup", "cleanup_and_wait"]


def set_rest_angle(angle: int):
    """
    Set rest angle for all servos (applies on next movements).
    """
    global _REST_ANGLE
    _REST_ANGLE = max(0, min(180, int(angle)))


def cleanup():
    """
    Stop PWM and cleanup GPIO. Call on program exit.
    """
    global _gpio_initialized, _servos
    for s in _servos.values():
        if s is not None:
            s.stop()
    # Optionally wait for background worker threads to finish. By default we
    # do not block; callers may pass wait=True to join threads before cleanup.
    GPIO.cleanup()
    _gpio_initialized = False


def cleanup_and_wait(timeout: Optional[float] = None) -> None:
    """Stop PWM, wait for active worker threads, and cleanup GPIO.

    timeout: maximum time to wait for all active threads (None = wait forever).
    """
    # join active threads
    threads = list(_active_threads)
    for t in threads:
        try:
            t.join(timeout=timeout)
        except Exception:
            pass
    # then stop PWM and cleanup
    for s in _servos.values():
        if s is not None:
            s.stop()
    GPIO.cleanup()
    global _gpio_initialized
    _gpio_initialized = False