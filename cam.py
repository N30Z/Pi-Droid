"""Camera helpers used by Pi-Droid.

Provides two main functions intended for importing and use by an OCR script:

- get_text(name, ocr_func=None, frame=None, camera_index=0)
  - name: 'swipe' or 'info_text' (case-insensitive)
  - ocr_func: optional callable taking a BGR image (numpy array) and returning text.
    If not provided, this will try to use pytesseract if available.
  - frame: optional BGR image to use instead of capturing from camera.

- check(name, threshold=0.85, frame=None, camera_index=0)
  - name: 'code' or 'home' (case-insensitive)
  - returns True when the live region matches the template image saved by
    `calibrate.py` (templates/region_<Name>.png) above the given threshold.

The module reads region coordinates from `config.json` (same format as
`calibrate.py`) and uses `templates/` for stored region images.
"""

from typing import Callable, Optional, Tuple
import json
import os
import cv2 as cv
import numpy as np

CONFIG_PATH = "config.json"
TEMPLATE_DIR = "templates"


def _load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    raise FileNotFoundError(f"{CONFIG_PATH} not found. Run calibrate.py first.")


def _normalize_name(name: str) -> str:
    # accept both lowercase short names and the calibrated keys
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    n = name.strip().lower()
    mapping = {
        "info_text": "Info_text",
        "infotext": "Info_text",
        "info": "Info_text",
        "swipe": "Swipe",
        "code": "Code",
        "home": "Home",
    }
    return mapping.get(n, name)


def _get_region_coords(cfg: dict, name: str) -> Tuple[int, int, int, int]:
    regs = cfg.get("REGIONS", {})
    if name in regs:
        r = regs[name]
        if len(r) != 4:
            raise ValueError(f"Region '{name}' has invalid coords: {r}")
        return tuple(map(int, r))
    raise KeyError(f"Region '{name}' not found in config.json (REGIONS)")


def _capture_frame(camera_index: int = 0) -> np.ndarray:
    cap = cv.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Camera {camera_index} not available")
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError("Failed to capture frame from camera")
    return frame


def crop(frame: np.ndarray, rect: Tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = rect
    return frame[y : y + h, x : x + w]


def get_text(
    name: str,
    ocr_func: Optional[Callable[[np.ndarray], str]] = None,
    frame: Optional[np.ndarray] = None,
    camera_index: int = 0,
) -> str:
    """Return text from the named region.

    If ocr_func is provided it will be called with the cropped BGR image and
    should return a string. Otherwise the function will attempt to use
    pytesseract (if installed) and raise a helpful error if not available.
    """
    cfg = _load_config()
    name_key = _normalize_name(name)
    region = _get_region_coords(cfg, name_key)

    if frame is None:
        frame = _capture_frame(camera_index)

    img = crop(frame, region)

    if ocr_func is not None:
        return ocr_func(img)

    # try pytesseract if available
    try:
        import pytesseract
        from PIL import Image
    except Exception as e:
        raise RuntimeError(
            "No ocr_func provided and pytesseract not available. "
            "Install pytesseract or pass an ocr_func(image)->str."
        ) from e

    # convert BGR -> RGB -> PIL
    rgb = cv.cvtColor(img, cv.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    text = pytesseract.image_to_string(pil)
    return text.strip()


def check(
    name: str,
    threshold: float = 0.85,
    frame: Optional[np.ndarray] = None,
    camera_index: int = 0,
) -> bool:
    """Check if the current region matches the stored template image.

    Returns True if the normalized template matching score is >= threshold.
    """
    cfg = _load_config()
    name_key = _normalize_name(name)

    # we expect templates saved as templates/region_<Name>.png by calibrate.py
    tmpl_path = os.path.join(TEMPLATE_DIR, f"region_{name_key}.png")
    if not os.path.exists(tmpl_path):
        raise FileNotFoundError(f"Template not found: {tmpl_path}")

    template = cv.imread(tmpl_path, cv.IMREAD_COLOR)
    if template is None:
        raise RuntimeError(f"Failed to load template image: {tmpl_path}")

    region = _get_region_coords(cfg, name_key)

    if frame is None:
        frame = _capture_frame(camera_index)

    img = crop(frame, region)

    # If sizes differ, resize template to match captured region for direct comparison
    th, tw = template.shape[:2]
    ih, iw = img.shape[:2]
    tmpl = template
    if (th, tw) != (ih, iw):
        try:
            tmpl = cv.resize(template, (iw, ih), interpolation=cv.INTER_AREA)
        except Exception:
            tmpl = template

    # convert to gray for template matching
    g_img = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
    g_tmpl = cv.cvtColor(tmpl, cv.COLOR_BGR2GRAY)

    # perform normalized cross-correlation
    res = cv.matchTemplate(g_img, g_tmpl, cv.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv.minMaxLoc(res)
    return float(max_val) >= float(threshold)


__all__ = ["get_text", "check", "crop"]
