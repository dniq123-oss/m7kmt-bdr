import os, re, time, random, threading, logging
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nyx")

state = {"running": False, "room_url": "", "room_id": "", "msg": "",
         "interval": 0.3, "threads": 1, "accounts": []}
lock = threading.Lock()
stop_flag = threading.Event()
workers = []

UA_WEB = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/124.0.0.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) "
             "Version/17.4 Mobile/15E148 Safari/604.1")

ROOM_ID_PATTERNS = [
    r'"roomId":"(\d+)"',
    r'"room_id":"(\d+)"',
    r'roomId=(\d+)',
    r'"liveRoomId":"(\d+)"',
    r'webcast/room/(\d+)',
]

def extract_room_id(url):
    if not url:
        return None, "empty"
    if url.isdigit():
        return url, None
    if not url.startswith("http"):
        url = "https://" + url
    headers = {"User-Agent": UA_WEB,
               "Accept-Language": "en-US,en;q=0.9",
               "Referer": "https://www.tiktok.com/"}
    try:
        r = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
    except Exception as e:
        return None, "fetch: " + str(e)
    for pat in ROOM_ID_PATTERNS:
        m = re.search(pat, r.text or "")
        if m:
            return m.group(1), None
    try:
        h = re.search(r"@([^/]+)", url)
        if h:
            api = ("https://www.tiktok.com/api-live/user/room"
                   "?aid=1988&app_name=tiktok_web&uniqueId=" + h.group(1))
            j = requests.get(api, headers=headers, timeout=10).json()
            rid = j.get("data", {}).get("user", {}).get("roomId")
            if rid:
                return str(rid), None
    except Exception:
        pass
    return None, "room id not found (stream offline?)"

def send_once(acc, room_id, msg):
    body = {"room_id": room_id, "msg": msg,
            "csrf_token": acc.get("csrf", ""),
            "request_id": str(int(time.time()*1000)) + str(random.randint(100,999))}
    hdrs = {"User-Agent": UA_MOBILE,
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": acc["cookie"],
            "Referer": "https://www.tiktok.com/live",
            "Origin": "https://www.tiktok.com"}
    try:
        r = requests.post("https://webcast.tiktok.com/webcast/room/chat/",
                          data=body, headers=hdrs, timeout=8)
        acc["sent"] += 1
        if r.status_code == 200:
            res = r.json()
            if res.get("status_code") == 0:
                acc["ok"] += 1
                acc["last_err"] = ""
            else:
                acc["err"] += 1
                acc["last_err"] = str(res.get("data", {})) if res.get("data") else str(res)
        else:
            acc["err"] += 1
            acc["last_err"] = f"HTTP {r.status_code}"
    except Exception as e:
        acc["sent"] += 1
        acc["err"] += 1
        acc["last_err"] = str(e)

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
    msg        = str(payload.get("msg", "")).strip()
    interval   = float(payload.get("interval", 0.3))
    threads    = int(payload.get("threads", 1))
    raw        = payload.get("accounts", [])

    if not room_input or not msg or not raw:
        return {"ok": False, "error": "ناقص بيانات"}

    room_id, err = extract_room_id(room_input)
    if err:
        return {"ok": False, "error": err}

    accounts = []
    for a in raw:
        c = (a.get("cookie") or "").strip()
        if not c: continue
        accounts.append({"cookie": c, "csrf": (a.get("csrf") or "").strip(),
                         "sent": 0, "ok": 0, "err": 0})
    if not accounts:
        return {"ok": False, "error": "مافي حساب صالح"}

    state.update(room_url=room_input, room_id=room_id, msg=msg,
                 interval=interval, threads=threads, accounts=accounts)

    for acc in accounts:
        for _ in range(threads):
            t = threading.Thread(target=worker,
                                 args=(acc, room_id, msg, interval),
                                 daemon=True)
            t.start(); workers.append(t)

    state["running"] = True
    return {"ok": True, "workers": len(workers),
            "accounts": len(accounts), "room_id": room_id}

@app.route("/")
def health():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "nyx alive (index.html not found)"

@app.route("/status")
def status():
    with lock:
        return jsonify({
            "running": state["running"],
            "room_id": state["room_id"],
            "room_url": state["room_url"],
            "accounts": [{"cookie": a["cookie"][:10] + "...",
                          "sent": a["sent"], "ok": a["ok"], "err": a["err"]}
                         for a in state["accounts"]],
            "totals": {
                "sent": sum(a["sent"] for a in state["accounts"]),
                "ok":   sum(a["ok"]   for a in state["accounts"]),
                "err":  sum(a["err"]  for a in state["accounts"]),
            },
        })

@app.route("/run", methods=["POST"])
def api_run():
    return jsonify(launch(request.get_json(force=True, silent=True) or {}))

@app.route("/stop", methods=["POST"])
def api_stop():
    stop_workers()
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))