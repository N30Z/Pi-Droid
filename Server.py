from flask import Flask, render_template_string, Response, jsonify, request
import threading
import cv2
import time
import calibrate

app = Flask(__name__)

# Shared camera capture
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

# process state
state = {
    "running": False,
    "paused": False,
    "current_digits": 0,
    "line_progress": 0,
    "num_lines": 0,
    "goal_msg": "",
}

PAGE = """
<!doctype html>
<html>
  <head>
    <title>Pi-Droid Control</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 0; }
      .container { display:flex; height: 100vh; }
      .left { width: 320px; padding: 16px; box-sizing: border-box; background:#eee; }
      .right { flex:1; display:flex; align-items:center; justify-content:center; }
      button { display:block; width:100%; margin:8px 0; padding:12px; font-size:16px; }
      .progress { position: absolute; bottom:0; left:0; right:0; background:#ddd; padding:8px; }
      .bar { width:100%; background:#ccc; height:28px; position:relative; }
      .bar-inner { background:#4caf50; height:100%; width:30%; display:flex; align-items:center; justify-content:center; color:white; }
    </style>
  </head>
  <body>
    <div class="container">
      <div class="left">
        <button onclick="api('/api/start')">Start</button>
        <button onclick="api('/api/stop')">Stop</button>
        <button onclick="api('/api/pause')">Pause</button>
        <button onclick="api('/api/resume')">Resume</button>
        <hr>
        <button onclick="api('/api/calibrate_all')">Run all camera calibrations</button>
        <div id="goal" style="margin-top:16px;color:darkred;font-weight:bold;"></div>
      </div>
      <div class="right">
        <img id="video" src="/video_feed" style="max-width:100%; max-height:100%;"/>
      </div>
    </div>
    <div class="progress">
      <div>Digits: <span id="digits">0</span> &nbsp; Line: <span id="line">0</span>/<span id="lines">0</span></div>
      <div class="bar"><div class="bar-inner" id="barinner">0%</div></div>
    </div>

    <script>
      function api(path){ fetch(path).then(r=>r.json()).then(d=>updateStatus(d)) }
      function updateStatus(d){
        document.getElementById('digits').textContent = d.current_digits || 0;
        document.getElementById('line').textContent = d.line_progress || 0;
        document.getElementById('lines').textContent = d.num_lines || 0;
        var pct = d.num_lines ? Math.round((d.line_progress/d.num_lines)*100) : 0;
        document.getElementById('barinner').style.width = pct + '%';
        document.getElementById('barinner').textContent = pct + '%';
        if(d.goal_msg){ document.getElementById('goal').textContent = d.goal_msg }
      }
      // poll status
      setInterval(function(){ fetch('/api/status').then(r=>r.json()).then(updateStatus) }, 1000);
    </script>
  </body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(PAGE)


def gen_camera():
    while True:
        frame = cam.get_frame()
        if frame is None:
            time.sleep(0.05)
            continue
        # annotate via calibrate helper
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


@app.route('/api/goal', methods=['POST'])
def api_goal():
    data = request.get_json() or {}
    val = data.get('value')
    if not val:
        return jsonify({'error':'missing value'}), 400
    msg = f"Found it: {val}!!"
    state['goal_msg'] = msg
    # automatically stop
    state['running'] = False
    return jsonify({'msg': msg})


if __name__ == '__main__':
    # Try to start server on a few sensible fallbacks and give clear messages
    import socket
    hosts = [ ('0.0.0.0', 8888), ('127.0.0.1', 8080), ('0.0.0.0', 8080), ('127.0.0.1', 8000) ]
    started = False
    for h,p in hosts:
        try:
            print(f"Starting server on {h}:{p} ...")
            app.run(host=h, port=p, threaded=True)
            started = True
            break
        except OSError as e:
            # Common on Windows: permission / port-in-use errors
            print(f"Failed to bind {h}:{p} -> {e}")
            continue
    if not started:
        print("Could not start the web server on any fallback addresses.")
        print("Possible causes:")
        print(" - Another process is already using the port (use 'netstat -ano | findstr :8080' to check)")
        print(" - Firewall or OS restrictions prevent binding; try running with elevated permissions or choose a different port")
        print(" - On Windows, some ports or binding to 0.0.0.0 may be restricted by security software")
        print("You can also start the app programmatically with a different host/port or run behind nginx.")
