# calibrate.py
import cv2 as cv
import json, os, time

CAMERA_INDEX = 0
WIDTH, HEIGHT = 1280, 720
TEMPLATE_DIR = "templates"
CONFIG_PATH = "config.json"

os.makedirs(TEMPLATE_DIR, exist_ok=True)

# Auswahlrechteck per Maus
sel = None
dragging = False
pt1 = None

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {
        "OCR_ROI": [900, 630, 340, 60],
        "THRESH_A": 0.85,
        "THRESH_B": 0.85,
        "STABLE_FRAMES": 3,
        # named regions that will be used by the OCR script later
        # keys: Info_text, Swipe, Code, Home -> each value is [x,y,w,h]
        "REGIONS": {}
    }

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    print("[OK] config.json gespeichert.")

def on_mouse(event, x, y, flags, param):
    global sel, dragging, pt1
    if event == cv.EVENT_LBUTTONDOWN:
        dragging = True
        pt1 = (x, y)
        sel = None
    elif event == cv.EVENT_MOUSEMOVE and dragging:
        sel = (min(pt1[0], x), min(pt1[1], y), abs(x-pt1[0]), abs(y-pt1[1]))
    elif event == cv.EVENT_LBUTTONUP:
        dragging = False
        if pt1 is not None:
            sel = (min(pt1[0], x), min(pt1[1], y), abs(x-pt1[0]), abs(y-pt1[1]))

def crop(frame, r):
    x,y,w,h = r
    return frame[y:y+h, x:x+w]

def main():
    cfg = load_config()

    cap = cv.VideoCapture(CAMERA_INDEX)
    cap.set(cv.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv.CAP_PROP_FRAME_HEIGHT, HEIGHT)

    if not cap.isOpened():
        raise RuntimeError("Kamera nicht gefunden.")

    # show key mapping for named regions
    win = (
        "Kalibrierung (Ziehen = Auswahl; 1/2=Template; o=OCR-ROI; "
        "i=Info_text; w=Swipe; c=Code; h=Home; s=Screenshot; q=Quit)"
    )
    cv.namedWindow(win)
    cv.setMouseCallback(win, on_mouse)

    # mapping from key to region name
    region_keys = {
        'i': 'Info_text',
        'w': 'Swipe',
        'c': 'Code',
        'h': 'Home'
    }

    print("Bereit. Ziehe eine Box über den relevanten Bereich.")
    while True:
        ok, frame = cap.read()
        if not ok: break

        disp = frame.copy()
        if sel:
            x,y,w,h = sel
            cv.rectangle(disp, (x,y), (x+w, y+h), (0,255,0), 2)
            cv.putText(disp, f"{w}x{h}", (x, max(0,y-8)), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)

        # aktuelle OCR-ROI anzeigen
        rx, ry, rw, rh = cfg["OCR_ROI"]
        cv.rectangle(disp, (rx,ry), (rx+rw, ry+rh), (255,0,0), 2)
        cv.putText(disp, "OCR_ROI", (rx, max(0,ry-8)), cv.FONT_HERSHEY_SIMPLEX, 0.5, (255,0,0), 1)

        # draw named regions saved in config
        # use consistent colors per region name (fallback color if unknown)
        color_map = {
            "Info_text": (0,165,255),  # orange
            "Swipe": (0,255,255),      # yellow
            "Code": (0,255,0),         # green
            "Home": (255,0,255)        # magenta
        }
        for name, rect in cfg.get("REGIONS", {}).items():
            try:
                rx, ry, rw, rh = rect
            except Exception:
                continue
            col = color_map.get(name, (200,200,200))
            cv.rectangle(disp, (rx,ry), (rx+rw, ry+rh), col, 2)
            cv.putText(disp, name, (rx, max(0,ry-8)), cv.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)

        cv.imshow(win, disp)
        k = cv.waitKey(10) & 0xFF
        if k == ord('q'):
            break
        elif k == ord('1') and sel:
            path = os.path.join(TEMPLATE_DIR, "state_a.png")
            cv.imwrite(path, crop(frame, sel))
            print(f"[OK] Template A gespeichert: {path}")
        elif k == ord('2') and sel:
            path = os.path.join(TEMPLATE_DIR, "state_b.png")
            cv.imwrite(path, crop(frame, sel))
            print(f"[OK] Template B gespeichert: {path}")
        elif k == ord('o') and sel:
            cfg["OCR_ROI"] = list(sel)
            save_config(cfg)
        elif k in (ord('i'), ord('w'), ord('c'), ord('h')) and sel:
            # save named region for OCR later
            name = region_keys.get(chr(k))
            if name:
                cfg.setdefault("REGIONS", {})[name] = list(sel)
                path = os.path.join(TEMPLATE_DIR, f"region_{name}.png")
                cv.imwrite(path, crop(frame, sel))
                save_config(cfg)
                print(f"[OK] Region '{name}' gespeichert: {path}")
        elif k == ord('s'):
            fn = f"screenshot_{int(time.time())}.png"
            cv.imwrite(fn, frame)
            print(f"[OK] Screenshot: {fn}")

    cap.release()
    cv.destroyAllWindows()

if __name__ == "__main__":
    main()