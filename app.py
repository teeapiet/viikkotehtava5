"""Flask-chat, Ollama ja keskusteluhistoria."""

import json
import os
import re
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

import db

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b")
SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    "You are a friendly Linux tutor. Always reply in English. Keep answers short.",
)
HISTORY_LIMIT = int(os.environ.get("HISTORY_LIMIT", "10"))
MAX_MESSAGE_LEN = 2000
SESSION_RE = re.compile(r"[A-Za-z0-9-]{8,64}")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 65536
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_prefix=1)


def ndjson(value):
    return json.dumps(value, ensure_ascii=False) + "\n"


@app.get("/")
def index():
    return render_template("index.html", model=OLLAMA_MODEL)


@app.get("/health")
def health():
    revision_file = Path(__file__).with_name("REVISION")
    revision = (
        revision_file.read_text(encoding="utf-8").strip()
        if revision_file.is_file()
        else "local"
    )

    if request.args.get("details") != "1":
        return revision + "\n", 200, {"Cache-Control": "no-store"}

    database_ok = False
    ollama_ok = False
    try:
        db.check_connection()
        database_ok = True
    except db.DatabaseError:
        app.logger.exception("Tietokannan terveystarkistus epäonnistui")

    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=(2, 3))
        response.raise_for_status()
        models = response.json().get("models", [])
        ollama_ok = any(item.get("name") == OLLAMA_MODEL for item in models)
    except (requests.RequestException, ValueError, AttributeError, TypeError):
        app.logger.exception("Ollaman terveystarkistus epäonnistui")

    status = 200 if database_ok and ollama_ok else 503
    return jsonify(
        revision=revision,
        database=database_ok,
        ollama=ollama_ok,
    ), status


@app.route("/api/history/<session_id>", methods=["GET", "DELETE"])
def history(session_id):
    if not SESSION_RE.fullmatch(session_id):
        return jsonify(error="Invalid conversation ID"), 400

    try:
        if request.method == "DELETE":
            db.delete_history(session_id)
            return jsonify(ok=True)
        return jsonify(db.get_history(session_id, limit=50))
    except db.DatabaseError:
        app.logger.exception("Database error")
        return jsonify(error="Database error"), 503


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send the message as a JSON object"), 400

    session_id = data.get("session_id")
    message = data.get("message")

    if not isinstance(session_id, str) or not SESSION_RE.fullmatch(session_id):
        return jsonify(error="Invalid conversation ID"), 400
    if not isinstance(message, str) or not message.strip():
        return jsonify(error="Please enter a message"), 400

    message = message.strip()
    if len(message) > MAX_MESSAGE_LEN:
        return jsonify(error="Your message must be no longer than 2000 characters"), 400

    try:
        past = db.get_history(session_id, limit=HISTORY_LIMIT)
        db.save_message(session_id, "user", message)
    except db.DatabaseError:
        app.logger.exception("Viestin tallennus epäonnistui")
        return jsonify(error="Could not save your message"), 503

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + past
        + [{"role": "user", "content": message}]
    )

    def generate():
        parts = []
        finished = False
        try:
            with requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": messages,
                    "stream": True,
                },
                stream=True,
                timeout=(5, 300),
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if not isinstance(chunk, dict) or chunk.get("error"):
                        raise ValueError("Ollama palautti virheen")
                    token = chunk.get("message", {}).get("content", "")
                    if not isinstance(token, str):
                        raise ValueError("Virheellinen vastaus")
                    if token:
                        parts.append(token)
                        yield ndjson({"token": token})
                    if chunk.get("done"):
                        finished = True
                        break
                if not finished:
                    raise ValueError("Ollaman vastaus katkesi")
        except (requests.RequestException, ValueError, AttributeError, TypeError):
            app.logger.exception("Ollama-kutsu epäonnistui")
            yield ndjson({"error": "The model could not complete its response. Please try again."})
            return

        reply = "".join(parts)
        try:
            if reply:
                db.save_message(session_id, "assistant", reply)
        except db.DatabaseError:
            app.logger.exception("Vastauksen tallennus epäonnistui")
            yield ndjson({"error": "The response was received but could not be saved."})
            return
        yield ndjson({"done": True})

    return Response(
        generate(),
        mimetype="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
