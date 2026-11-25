import os, re, time, random, threading, logging, json
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nyx")

state = {"running": False, "room_url": "", "room_id": "", "msg": "", "interval": 0.3, "threads": 1, "accounts": []}
lock = threading.Lock()
stop_flag = threading.Event()
workers = []

UA_WEB = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1")

def resolve_url(url):
    """Fetch HTML and extract room_id directly from TikTok's __UNIVERSAL_DATA_FOR_REHYDRATION__"""
    if not url:
        return None, None, False, "empty url"
    
    url = url.strip()
    if url.isdigit():
        return None, url, True, None

    if not url.startswith("http"):
        url = "https://" + url

    session = requests.Session()
    session.headers.update({
        "User-Agent": UA_WEB,
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.tiktok.com/",
    })

    try:
        r = session.get(url, timeout=15, allow_redirects=True)
    except Exception as e:
        return None, None, False, "fetch failed: " + str(e)

    final_url = r.url or url
    m = re.search(r"@([^/?#]+)", final_url)
    unique_id = m.group(1) if m else None

    # Extract from hidden JSON
    match = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            scope = data.get("__DEFAULT_SCOPE__", {})
            
            # Look for live room details
            room_info = scope.get("webapp.room-detail", {})
            if room_info:
                room = room_info.get("roomInfo", {}).get("room", {})
                room_id = room.get("id")
                status = room.get("status")
                if room_id and str(status) == "2":
                    return unique_id, str(room_id), True, None
                elif room_id and str(status) != "2":
                    return unique_id, str(room_id), False, "stream status is not live (ended or offline)"
            
            # If room_info not found, it means user is not live
            if "webapp.user-detail" in scope:
                return unique_id, None, False, "user is not currently live"

        except Exception as e:
            return unique_id, None, False, "json parse error: " + str(e)

    return unique_id, None, False, "room id not found in HTML (maybe a private live or video)"

def send_once(acc, room_id, msg):
    body = {"room_id": room_id, "msg": msg, "csrf_token": acc.get("csrf", ""), "request_id": str(int(time.time()*1000))}
    hdrs = {
        "User-Agent": UA_MOBILE,
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": acc["cookie"],
        "Referer": "https://www.tiktok.com/live",
        "Origin": "https://www.tiktok.com",
        "Accept": "application/json, text/plain, */*"
    }
    try:
        r = requests.post("https://webcast.tiktok.com/webcast/room/chat/", data=body, headers=hdrs, timeout=10)
        acc["sent"] += 1
        
        if r.status_code == 200:
            try:
                j = r.json()
                code = j.get("status_code")
                if code == 0:
                    acc["ok"] += 1
                    acc["last_err"] = ""
                else:
                    acc["err"] += 1
                    acc["last_err"] = f"TikTok refused: {code} - {j.get('data', {})}"
            except:
                acc["err"] += 1
                acc["last_err"] = "200 OK but not JSON (likely blocked)"
        else:
            acc["err"] += 1
            acc["last_err"] = f"HTTP {r.status_code} - X-Bogus signature required"
            
    except Exception as e:
        acc["sent"] += 1
        acc["err"] += 1
        acc["last_err"] = "Exception: " + str(e)

def worker(acc, room_id, msg, interval):
    while not stop_flag.is_set():
        send_once(acc, room_id, msg)
        time.sleep(max(0.05, interval + random.uniform(-0.05, 0.05)))

def stop_workers():
    stop_flag.set()
    state["running"] = False
    time.sleep(0.2)

def launch(payload):
    stop_workers()
    stop_flag.clear()
    workers.clear()

    room_input = str(payload.get("room", "")).strip()
    msg = str(payload.get("msg", "")).strip()
    interval = float(payload.get("interval", 0.3))
    threads = int(payload.get("threads", 1))
    raw = payload.get("accounts", [])

    if not room_input or not msg or not raw:
        return {"ok": False, "error": "missing data"}

    unique_id, room_id, is_live, err = resolve_url(room_input)
    if err or not is_live:
        return {"ok": False, "error": "not live or room id failed: " + str(err)}

    accounts = []
    for a in raw:
        c = (a.get("cookie") or "").strip()
        if not c: continue
        accounts.append({"cookie": c, "csrf": (a.get("csrf") or "").strip(), "sent": 0, "ok": 0, "err": 0, "last_err": ""})
    
    if not accounts:
        return {"ok": False, "error": "no valid accounts"}

    state.update(room_url=room_input, room_id=room_id, msg=msg, interval=interval, threads=threads, accounts=accounts)

    for acc in accounts:
        for _ in range(threads):
            t = threading.Thread(target=worker, args=(acc, room_id, msg, interval), daemon=True)
            t.start()
            workers.append(t)

    state["running"] = True
    return {"ok": True, "workers": len(workers), "accounts": len(accounts), "room_id": room_id, "unique_id": unique_id}

@app.route("/check", methods=["POST"])
def api_check():
    data = request.get_json(force=True, silent=True) or {}
    url = str(data.get("room", "")).strip()
    if not url: return jsonify({"ok": False, "error": "empty"})
    
    unique_id, room_id, is_live, err = resolve_url(url)
    if err or not is_live:
        return jsonify({"ok": False, "error": err or "not live", "room_id": room_id, "unique_id": unique_id})
    
    return jsonify({"ok": True, "room_id": room_id, "unique_id": unique_id, "title": "Live Stream"})

@app.route("/")
def health():
    try:
        with open("index.html", "r", encoding="utf-8") as f: return f.read()
    except: return "nyx alive"

@app.route("/status")
def status():
    with lock:
        return jsonify({
            "running": state["running"], "room_id": state["room_id"], "room_url": state["room_url"],
            "accounts": [{"cookie": a["cookie"][:10] + "...", "sent": a["sent"], "ok": a["ok"], "err": a["err"], "last_err": a.get("last_err", "")} for a in state["accounts"]],
            "totals": {"sent": sum(a["sent"] for a in state["accounts"]), "ok": sum(a["ok"] for a in state["accounts"]), "err": sum(a["err"] for a in state["accounts"])}
        })

@app.route("/run", methods=["POST"])
def api_run(): return jsonify(launch(request.get_json(force=True, silent=True) or {}))

@app.route("/stop", methods=["POST"])
def api_stop():
    stop_workers()
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))