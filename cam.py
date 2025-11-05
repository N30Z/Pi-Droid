# main.py
import cv2 as cv
import numpy as np
import pytesseract
import time
from collections import deque

# ============ KONFIG ============
CAMERA_INDEX = 0            # 0.. je nach Grabber/Kamera
FRAME_WIDTH  = 1280         # kleiner = schneller
FRAME_HEIGHT = 720
FPS_LIMIT    = 10

TEMPLATE_A   = "templates/state_a.png"
TEMPLATE_B   = "templates/state_b.png"

# ROI für OCR (x, y, w, h) in Pixeln relativ zum skalierten Frame
OCR_ROI      = (900, 630, 340, 60)

# Schwellwerte 0..1 für matchTemplate(TM_CCOEFF_NORMED)
THRESH_A     = 0.85
THRESH_B     = 0.85

# Wie viele aufeinanderfolgende Frames müssen den Zustand bestätigen?
STABLE_FRAMES = 3

# Optional: MQTT für Meldungen (Broker/Topic anpassen)
MQTT_ENABLE = False
MQTT_BROKER = "127.0.0.1"
MQTT_TOPIC  = "screen/alerts"

# ============ HILFSFUNKTIONEN ============
def preprocess_gray(img):
    g = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
    g = cv.GaussianBlur(g, (3,3), 0)
    return g

def multi_scale_match(gray_frame, gray_tpl, scales=(1.0, 0.95, 0.9, 1.05)):
    """Einfaches Multi-Scale Matching für kleine Skalierungsfehler."""
    best_val, best_loc, best_scale = -1, None, 1.0
    for s in scales:
        th, tw = int(gray_tpl.shape[0]*s), int(gray_tpl.shape[1]*s)
        if th < 10 or tw < 10: 
            continue
        tpl_resized = cv.resize(gray_tpl, (tw, th), interpolation=cv.INTER_AREA)
        res = cv.matchTemplate(gray_frame, tpl_resized, cv.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv.minMaxLoc(res)
        if max_val > best_val:
            best_val, best_loc, best_scale = max_val, max_loc, s
    return best_val, best_loc, best_scale

def ocr_text(img_roi):
    roi = cv.cvtColor(img_roi, cv.COLOR_BGR2GRAY)
    roi = cv.threshold(roi, 0, 255, cv.THRESH_BINARY+cv.THRESH_OTSU)[1]
    # PSM 7: einzelne Textzeile; Sprache deutsch (deu) + englisch (eng) falls nötig
    cfg = r'--oem 3 --psm 7 -l deu+eng'
    txt = pytesseract.image_to_string(roi, config=cfg)
    return txt.strip()

# Optional: MQTT
client = None
if MQTT_ENABLE:
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client()
        client.connect(MQTT_BROKER, 1883, 60)
    except Exception as e:
        print("MQTT deaktiviert (Fehler):", e)
        client = None

def notify(event, payload=None):
    msg = {"event": event, "payload": payload or {}}
    print(f"[ALERT] {msg}")
    if client:
        import json
        client.publish(MQTT_TOPIC, json.dumps(msg), qos=1, retain=False)

# ============ HAUPTLOGIK ============
def main():
    # Videoquelle
    cap = cv.VideoCapture(CAMERA_INDEX)
    cap.set(cv.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    if not cap.isOpened():
        raise RuntimeError("Kamera/Grabber nicht gefunden.")

    # Templates laden (grau vorverarbeiten)
    tpl_a = preprocess_gray(cv.imread(TEMPLATE_A, cv.IMREAD_COLOR))
    tpl_b = preprocess_gray(cv.imread(TEMPLATE_B, cv.IMREAD_COLOR))
    if tpl_a is None or tpl_b is None:
        raise RuntimeError("Template-Bilder nicht gefunden. Pfade prüfen.")

    state_history = deque(maxlen=STABLE_FRAMES)
    last_stable_state = None
    last_ocr_text = ""

    t_last = 0
    print("Starte Überwachung … (q zum Beenden)")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Frame konnte nicht gelesen werden.")
            break

        # optional framerate drosseln
        now = time.time()
        if now - t_last < 1.0 / FPS_LIMIT:
            # kleine Wartezeit
            time.sleep(max(0, (1.0 / FPS_LIMIT) - (now - t_last)))
        t_last = time.time()

        gray = preprocess_gray(frame)

        # Template-Matching
        val_a, loc_a, sc_a = multi_scale_match(gray, tpl_a)
        val_b, loc_b, sc_b = multi_scale_match(gray, tpl_b)

        # Aktuellen Frame-Zustand bestimmen
        if val_a >= THRESH_A and val_a >= val_b:
            cur_state = "STATE_A"
            score = float(val_a)
        elif val_b >= THRESH_B and val_b >= val_a:
            cur_state = "STATE_B"
            score = float(val_b)
        else:
            cur_state = "ANOMALY"
            score = float(max(val_a, val_b))

        state_history.append(cur_state)

        # Stabilen Zustand erkennen (Entprellung)
        if len(state_history) == STABLE_FRAMES and all(s == state_history[0] for s in state_history):
            stable = state_history[0]
            if stable != last_stable_state:
                last_stable_state = stable
                notify("state_change", {"state": stable, "score": score})

        # OCR auf definierter ROI
        x, y, w, h = OCR_ROI
        roi = frame[y:y+h, x:x+w].copy()
        text = ocr_text(roi)
        if text and text != last_ocr_text:
            last_ocr_text = text
            notify("ocr_update", {"text": text})

        # Debug-Overlay (kommentierbar)
        debug = frame.copy()
        cv.rectangle(debug, (OCR_ROI[0], OCR_ROI[1]), (OCR_ROI[0]+OCR_ROI[2], OCR_ROI[1]+OCR_ROI[3]), (0,255,0), 2)
        cv.putText(debug, f"A:{val_a:.2f}  B:{val_b:.2f}  cur:{cur_state}", (20, 40), cv.FONT_HERSHEY_SIMPLEX, 0.9, (0,0,255), 2)
        cv.putText(debug, f"OCR: {text}", (20, 80), cv.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2)

        cv.imshow("Monitor", debug)
        if cv.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv.destroyAllWindows()

if __name__ == "__main__":
    main()