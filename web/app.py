"""Flask web UI для генератора курсових v2.0."""
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser

from flask import Flask, Response, jsonify, render_template, request, send_file
from flask_cors import CORS

# Корінь репозиторію для імпортів
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Global state -----------------------------------------------------------
log_queue: queue.Queue = queue.Queue()
generation_active: bool = False
last_generated_file: str | None = None  # шлях до останнього успішно згенерованого .docx
# Persistent generator instance — щоб last_state виживав між запитами
# (для /api/regenerate_section)
shared_generator = None

# --- Logging --------------------------------------------------------------
class QueueHandler(logging.Handler):
    """Дублює всі логи у SSE-чергу."""
    def emit(self, record):
        try:
            log_queue.put(self.format(record))
        except Exception:
            pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

queue_handler = QueueHandler()
queue_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logging.getLogger().addHandler(queue_handler)

# --- App setup -------------------------------------------------------------
from main import CourseworkGenerator, load_config
from core.toc_parser import parse_lines

app = Flask(__name__)
CORS(app)
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml"
)
config = load_config(CONFIG_PATH)


# --- Config endpoints ------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config", methods=["GET"])
def get_config():
    global config
    config = load_config(CONFIG_PATH)
    # Не повертаємо api_key назовні
    safe = {
        "active_provider": config.get("active_provider"),
        "model": config.get("providers", {}).get(config.get("active_provider"), {}).get("model"),
        "project_settings": {
            "topic": config.get("project_settings", {}).get("topic", ""),
            "methodology_summary": config.get("project_settings", {}).get("methodology_summary", ""),
            "work_type": config.get("project_settings", {}).get("work_type", "coursework"),
        },
    }
    return jsonify(safe)


@app.route("/api/config", methods=["POST"])
def save_config():
    data = request.json or {}
    global config

    if "model" in data and config.get("active_provider"):
        provider = config["active_provider"]
        config["providers"].setdefault(provider, {})["model"] = data["model"]

    if "project_settings" in data:
        config.setdefault("project_settings", {}).update(data["project_settings"])

    return jsonify({"status": "ok"})


# --- TOC & methodology ------------------------------------------------------
@app.route("/api/parse_toc", methods=["POST"])
def parse_toc_route():
    text = (request.json or {}).get("text", "")
    lines = [l for l in text.splitlines() if l.strip()]
    try:
        return jsonify({"items": parse_lines(lines)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/upload_methodology", methods=["POST"])
def upload_methodology():
    """Парсить .txt/.docx/.pdf і повертає текст для вставки у textarea."""
    if "file" not in request.files:
        return jsonify({"error": "Файл не передано"}), 400

    file = request.files["file"]
    name = (file.filename or "").lower()
    if not name:
        return jsonify({"error": "Порожня назва файлу"}), 400

    try:
        if name.endswith(".txt") or name.endswith(".md"):
            content = file.read().decode("utf-8", errors="replace")
        elif name.endswith(".docx"):
            import io
            import docx
            doc = docx.Document(io.BytesIO(file.read()))
            content = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        elif name.endswith(".pdf"):
            try:
                import io
                import PyPDF2
            except ImportError:
                return jsonify({"error": "Встановіть PyPDF2: pip install PyPDF2"}), 500
            reader = PyPDF2.PdfReader(io.BytesIO(file.read()))
            content = "\n".join((p.extract_text() or "") for p in reader.pages)
        else:
            return jsonify({"error": "Формат: .txt, .md, .docx, .pdf"}), 400

        logger.info(f"Завантажено методичку: {file.filename} ({len(content)} символів)")
        return jsonify({"text": content, "filename": file.filename})
    except Exception as e:
        logger.error(f"Помилка читання методички: {e}")
        return jsonify({"error": str(e)}), 500


# --- Logs (SSE) ------------------------------------------------------------
@app.route("/api/logs")
def stream_logs():
    def generate():
        while True:
            try:
                msg = log_queue.get(timeout=1)
                yield f"data: {msg}\n\n"
            except queue.Empty:
                yield ": keepalive\n\n"
            time.sleep(0.05)
    return Response(generate(), mimetype="text/event-stream")


# --- Generation ------------------------------------------------------------
def run_generation_thread(topic, toc_text, work_type, methodology_text, section_types, volume, preset):
    global generation_active, last_generated_file, shared_generator
    generation_active = True
    last_generated_file = None
    try:
        logger.info(f"=== START | тема={topic!r} | тип={work_type} | volume={volume} | preset={preset} ===")
        shared_generator = CourseworkGenerator(config, log_callback=None)
        path = shared_generator.run(
            topic=topic,
            toc_text=toc_text,
            work_type=work_type,
            methodology_text=methodology_text,
            section_types=section_types,
            volume=volume,
            preset=preset,
        )
        last_generated_file = path
        log_queue.put(f"SUCCESS - DONE | {path}")
        log_queue.put(f"FILE_READY - {path}")
    except Exception as e:
        log_queue.put(f"ERROR - {e}")
        logger.exception("Генерація провалилась")
    finally:
        generation_active = False


def run_regenerate_thread(section_number, volume):
    global generation_active, last_generated_file, shared_generator
    generation_active = True
    try:
        logger.info(f"=== REGEN section {section_number!r} | volume={volume} ===")
        if not shared_generator:
            raise RuntimeError("Немає попередньої генерації")
        path = shared_generator.regenerate_section(section_number, volume=volume)
        last_generated_file = path
        log_queue.put(f"SUCCESS - REGEN OK | section={section_number}")
        log_queue.put(f"FILE_READY - {path}")
    except Exception as e:
        log_queue.put(f"ERROR - {e}")
        logger.exception("Регенерація провалилась")
    finally:
        generation_active = False


@app.route("/api/generate", methods=["POST"])
def start_generation():
    global generation_active
    if generation_active:
        return jsonify({"error": "Генерація вже виконується"}), 409

    data = request.json or {}
    topic = (data.get("topic") or "").strip()
    toc_text = (data.get("toc_text") or "").strip()
    work_type = data.get("work_type", "coursework")
    methodology_text = data.get("methodology_text", "")
    section_types = data.get("section_types") or []
    volume = data.get("volume", "standard")
    if volume not in ("short", "standard", "detailed"):
        volume = "standard"
    preset = data.get("preset", "standard")
    if preset not in ("economy", "standard", "quality"):
        preset = "standard"

    if not topic or not toc_text:
        return jsonify({"error": "Потрібні тема й зміст"}), 400

    threading.Thread(
        target=run_generation_thread,
        args=(topic, toc_text, work_type, methodology_text, section_types, volume, preset),
        daemon=True,
    ).start()
    return jsonify({"status": "started"})


@app.route("/api/regenerate_section", methods=["POST"])
def regenerate_section_route():
    global generation_active
    if generation_active:
        return jsonify({"error": "Генерація вже виконується"}), 409
    if not shared_generator or not shared_generator.last_state:
        return jsonify({"error": "Немає попередньої генерації — запустіть повну спершу"}), 400

    data = request.json or {}
    section_number = (data.get("section_number") or "").strip()
    volume = data.get("volume") or None  # None → використати volume з plan

    if not section_number:
        return jsonify({"error": "Потрібен section_number"}), 400

    threading.Thread(
        target=run_regenerate_thread,
        args=(section_number, volume),
        daemon=True,
    ).start()
    return jsonify({"status": "started"})


@app.route("/api/last_state")
def get_last_state():
    """Повертає номери секцій + рецензію ШІ (для UI кнопок та картки огляду)."""
    if not shared_generator or not shared_generator.last_state:
        return jsonify({"available": False})
    state = shared_generator.last_state
    review = None
    if state.review:
        review = {
            "score": state.review.score,
            "verdict": state.review.verdict,
            "strengths": state.review.strengths,
            "issues": [
                {"section": i.section, "problem": i.problem, "severity": i.severity}
                for i in state.review.issues
            ],
            "regenerate_recommended": state.review.regenerate_recommended,
        }
    return jsonify({
        "available": True,
        "topic": state.plan.topic,
        "sections": [
            {
                "number": s.number,
                "full_title": s.full_title,
                "type": s.type.value,
                "skip": s.skip_generation,
            }
            for s in state.plan.sections
        ],
        "review": review,
    })


# --- File access ------------------------------------------------------------
@app.route("/api/download")
def download_file():
    """Віддає останній згенерований .docx як файл."""
    global last_generated_file
    if not last_generated_file or not os.path.exists(last_generated_file):
        return jsonify({"error": "Файл не знайдено. Згенеруй щось спочатку."}), 404
    return send_file(
        last_generated_file,
        as_attachment=True,
        download_name=os.path.basename(last_generated_file),
    )


@app.route("/api/open_folder", methods=["POST"])
def open_folder():
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output"
    )
    os.makedirs(output_dir, exist_ok=True)
    try:
        if sys.platform == "win32":
            os.startfile(output_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", output_dir])
        else:
            subprocess.Popen(["xdg-open", output_dir])
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")


if __name__ == "__main__":
    threading.Timer(1.5, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
