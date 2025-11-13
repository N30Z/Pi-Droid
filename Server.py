from flask import Flask, render_template, Response, jsonify, request
import threading
import cv2
import time
import calibrate

app = Flask(__name__, template_folder="templates")

# ---------------------------
# Shared camera capture
# ---------------------------
class CameraThread:
    def __init__(self, index=0):
        self.cap = cv2.VideoCapture(index)
        self.lock = threading.Lock()
        self.running = True
        self.frame = None
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def _reader(self):
        while self.running:
            ok, frame = self.cap.read()
            if ok:
                with self.lock:
                    self.frame = frame
            else:
                time.sleep(0.1)

    def get_frame(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def stop(self):
        self.running = False
        try:
            self.cap.release()
        except Exception:
            pass

cam = CameraThread()

# ---------------------------
# Helper to interop w/ calibrate module
# ---------------------------
def _list_regions_safe():
    for fname in ("list_regions", "get_saved_regions", "get_regions"):
        fn = getattr(calibrate, fname, None)
        if callable(fn):
            try:
                res = fn()
                if isinstance(res, dict):
                    return res
                if isinstance(res, (list, tuple)):
                    out = {}
                    for item in res:
                        if isinstance(item, dict) and "name" in item and "rect" in item:
                            out[item["name"]] = item["rect"]
                    return out
            except Exception:
                pass
    for attr in ("REGIONS", "regions", "SAVED_REGIONS"):
        obj = getattr(calibrate, attr, None)
        if isinstance(obj, dict):
            return obj
    return {}

# ---------------------------
# process state
# ---------------------------
state = {
    "running": False,
    "paused": False,
    "current_digits": 0,
    "line_progress": 0,
    "num_lines": 0,
    "goal_msg": "",
}

# ---------------------------
# Pages
# ---------------------------
@app.route('/')
def index():
    return render_template("index.html")

@app.route('/calibrate')
def calibrate_page():
    # Fixed mapping in order of windows: UL, UR, LL, LR
    region_names = ["Info_text", "Swipe", "Home", "Code"]
    return render_template("calibrate.html", region_names=region_names)

# ---------------------------
# MJPEG feed
# ---------------------------
def gen_camera():
    while True:
        frame = cam.get_frame()
        if frame is None:
            time.sleep(0.05)
            continue
        try:
            disp = calibrate.get_annotated_frame(frame)
        except Exception:
            disp = frame
        ret, jpeg = cv2.imencode('.jpg', disp)
        if not ret:
            continue
        data = jpeg.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + data + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(gen_camera(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ---------------------------
# APIs - status & control
# ---------------------------
@app.route('/api/status')
def api_status():
    return jsonify(state)

@app.route('/api/start')
def api_start():
    state['running'] = True
    state['paused'] = False
    return jsonify(state)

@app.route('/api/stop')
def api_stop():
    state['running'] = False
    state['paused'] = False
    return jsonify(state)

@app.route('/api/pause')
def api_pause():
    state['paused'] = True
    return jsonify(state)

@app.route('/api/resume')
def api_resume():
    state['paused'] = False
    return jsonify(state)

# ---------------------------
# APIs - regions (list)
# ---------------------------
@app.route('/api/regions', methods=['GET'])
def api_regions():
    regions = _list_regions_safe()
    sane = {k: [int(v[0]), int(v[1]), int(v[2]), int(v[3])]
            for k, v in regions.items()
            if isinstance(v, (list, tuple)) and len(v) == 4}
    return jsonify({"regions": sane})

# ---------------------------
# Existing calibration APIs
# ---------------------------
@app.route('/api/calibrate_all')
def api_calibrate_all():
    frame = cam.get_frame()
    if frame is None:
        return jsonify({ 'error': 'no frame' }), 400
    try:
        res = calibrate.save_all_regions_from_frame(frame)
        return jsonify({'saved': res})
    except KeyError as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/calibrate_save', methods=['POST'])
def api_calibrate_save():
    data = request.get_json() or {}
    name = data.get('name')
    rect = data.get('rect')
    if not name or not rect:
        return jsonify({'error':'missing name or rect'}), 400
    frame = cam.get_frame()
    if frame is None:
        return jsonify({'error':'no frame available on server'}), 400
    try:
        path = calibrate.save_region_from_frame(name, rect, frame)
        return jsonify({'path': path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------------------
# Goal API
# ---------------------------
@app.route('/api/goal', methods=['POST'])
def api_goal():
    data = request.get_json() or {}
    val = data.get('value')
    if not val:
        return jsonify({'error':'missing value'}), 400
    msg = f"Found it: {val}!!"
    state['goal_msg'] = msg
    state['running'] = False
    return jsonify({'msg': msg})

# ---------------------------
# App runner
# ---------------------------
if __name__ == '__main__':
    import os
    print("Template path:", os.path.abspath(app.template_folder))
    hosts = [ ('0.0.0.0', 8888), ('127.0.0.1', 8080), ('0.0.0.0', 8080), ('127.0.0.1', 8000) ]
    started = False
    for h,p in hosts:
        try:
            print(f"Starting server on {h}:{p} ...")
            app.run(host=h, port=p, threaded=True)
            started = True
            break
        except OSError as e:
            print(f"Failed to bind {h}:{p} -> {e}")
            continue
    if not started:
        print("Could not start the web server on any fallback addresses.")
        print("Possible causes:")
        print(" - Another process is already using the port (use 'netstat -ano | findstr :8080' to check)")
        print(" - Firewall or OS restrictions prevent binding; try running with elevated permissions or choose a different port")
        print(" - On Windows, some ports or binding to 0.0.0.0 may be restricted by security software")
        print("You can also start the app programmatically with a different host/port or run behind nginx.")
