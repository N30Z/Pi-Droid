#!/usr/bin/env python3
from flask import Flask, request, jsonify
from pathlib import Path
from hid_input import type_numbers_on_device

app = Flask(__name__)

@app.get("/number")
def number():
    numbers = request.args.get("value") or request.args.get("n") or request.args.get("num")
    if not numbers:
        return jsonify({"error": "missing parameter: value"}), 400

    try:
        type_numbers_on_device(Path("/dev/hidg0"), numbers)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok", "typed": numbers})


if __name__ == "__main__":
    # Falls du direkt startest
    app.run(host="0.0.0.0", port=8080)
