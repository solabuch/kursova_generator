import os
import sys
import subprocess
import threading
import queue
import logging
import time
import webbrowser
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS

# Add parent directory to path to import main modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Global State - must be before QueueHandler
log_queue = queue.Queue()
generation_active = False

from main import load_config, CourseworkGenerator
from core.toc_parser import parse_lines

# Setup logging
class QueueHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            log_queue.put(msg)
        except Exception:
            pass  # Silently ignore logging errors

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Attach QueueHandler to root logger to capture all module logs (including Orchestrator)
root_logger = logging.getLogger()
queue_handler = QueueHandler()
queue_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
root_logger.addHandler(queue_handler)

app = Flask(__name__)
CORS(app)

# Load config after app init
config = load_config()

def log_callback(msg):
    log_queue.put(msg)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    # Reload config to ensure freshness
    global config
    config = load_config()
    return jsonify(config)

@app.route('/api/config', methods=['POST'])
def save_config():
    data = request.json
    global config
    # Update internal config state (in-memory mostly, unless we save to file)
    # The original GUI saved to memory and passed to generator.
    # main.py loads from file.
    # To persist, we might need to write to config.yaml if desired.
    # For now, let's update the global config object which is passed to generator.
    
    # Merge updates
    if 'providers' in data:
        for p, vals in data['providers'].items():
            if p not in config['providers']: config['providers'][p] = {}
            config['providers'][p].update(vals)
            
    if 'active_provider' in data:
        config['active_provider'] = data['active_provider']
        
    if 'project_settings' in data:
        if 'project_settings' not in config: config['project_settings'] = {}
        config['project_settings'].update(data['project_settings'])

    return jsonify({"status": "ok", "message": "Config updated in memory"})

@app.route('/api/parse_toc', methods=['POST'])
def parse_toc_route():
    text = request.json.get('text', '')
    lines = [l for l in text.splitlines() if l.strip()]
    try:
        parsed = parse_lines(lines)
        return jsonify({"items": parsed})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/logs')
def stream_logs():
    def generate():
        while True:
            try:
                # Non-blocking get
                msg = log_queue.get(timeout=1)
                yield f"data: {msg}\n\n"
            except queue.Empty:
                # Keep alive
                yield ": keepalive\n\n"
            time.sleep(0.1)
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/open_folder', methods=['POST'])
def open_folder():
    # Відкриваємо папку output (або ту, яку повертає генератор, але поки хардкод папки проекту)
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    try:
        if sys.platform == 'win32':
            os.startfile(output_dir)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', output_dir])
        else:
            subprocess.Popen(['xdg-open', output_dir])
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_generation_thread(topic, toc_text, overrides):
    global generation_active
    generation_active = True
    try:
        logger.info(f"INFO - === STARTING GENERATION: {topic} ===") # Use logger
        # Pass None as log_callback to avoid duplicates, since we catch logs via QueueHandler
        generator = CourseworkGenerator(config, log_callback=None)
        path = generator.run(topic=topic, toc_text=toc_text, overrides=overrides)
        log_queue.put(f"SUCCESS - DONE! File saved: {path}")
        log_queue.put(f"FILE_READY - {path}") # Special signal
    except Exception as e:
        log_queue.put(f"ERROR - {str(e)}")
        logger.exception("Generation failed")
    finally:
        generation_active = False

@app.route('/api/generate', methods=['POST'])
def start_generation():
    global generation_active
    if generation_active:
        return jsonify({"error": "Generation already in progress"}), 409
        
    data = request.json
    topic = data.get('topic')
    toc_text = data.get('toc_text')
    overrides = data.get('overrides', {})
    
    if not topic or not toc_text:
        return jsonify({"error": "Missing topic or TOC"}), 400
        
    thread = threading.Thread(target=run_generation_thread, args=(topic, toc_text, overrides))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")

if __name__ == '__main__':
    # Open browser after short delay
    threading.Timer(1.5, open_browser).start()
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False)
