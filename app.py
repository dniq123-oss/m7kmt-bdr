import os, re, time, random, threading, logging, json
from urllib.parse import urlparse, unquote
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

# ---------- 1. resolve any URL to unique_id or room_id ----------
def resolve_url(url):
    """
    Accepts:
      - https://www.tiktok.com/@user/live
      - https://vt.tiktok.com/xxxxx/
      - https://vm.tiktok.com/xxxxx/
      - numeric room id
    Returns (unique_id, room_id, error)
    """
    if not url:
        return None, None, "empty url"

    url = url.strip()
    if url.isdigit():
        return None, url, None

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
        return None, None, "fetch failed: " + str(e)

    final_url = r.url or url

    # extract @username from final url
    m = re.search(r"@([^/?#]+)", final_url)
    unique_id = m.group(1) if m else None

    # try regex room_id from html
    patterns = [
        r'"roomId":"(\d+)"',
        r'"room_id":"(\d+)"',
        r'roomId=(\d+)',
        r'"liveRoomId":"(\d+)"',
        r'snssdk\d*://live\?room_id=(\d+)',
        r'webcast/room/(\d+)',
    ]
    for pat in patterns:
        mm = re.search(pat, r.text or "")
        if mm:
            return unique_id, mm.group(1), None

    # fallback: api-live/user/room
    if unique_id:
        try:
            api = ("https://www.tiktok.com/api-live/user/room"
                   "?aid=1988&app_name=tiktok_web&uniqueId=" + unique_id)
            j = session.get(api, timeout=10).json()
            status = j.get("statusCode")
            if status == 0:
                room_id = (j.get("data", {}).get("user", {}).get("roomId") or "")
                if room_id and room_id != "0":
                    return unique_id, str(room_id), None
            elif status == 19881007:
                return unique_id, None, "user not found"
        except Exception:
            pass

    return unique_id, None, "room id not found (not a live stream?)"


# ---------- 2. check if live using webcast room info ----------
def check_live(room_id):
    """
    Calls webcast room info and returns (is_live, detail, error).
    """
    url = ("https://webcast.tiktok.com/webcast/room/info/"
           "?aid=1988&app_name=tiktok_web&device_platform=web_pc"
           "&room_id=" + str(room_id))
    headers = {
        "User-Agent": UA_WEB,
        "Referer": "https://www.tiktok.com/",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
    except Exception as e:
        return False, None, "check failed: " + str(e)

    if r.status_code != 200:
        return False, None, f"room info HTTP {r.status_code}"

    try:
        j = r.json()
    except Exception:
        return False, None, "room info not json"

    status = j.get("statusCode")
    if status != 0:
        return False, None, f"room info statusCode={status}"

    data = j.get("data", {})
    room = data.get("room", {})
    live_status = room.get("status")  # 2 = live, 4 = ended
    if live_status == 2:
        return True, data, None
    return False, data, f"stream status={live_status} (not live)"


# ---------- 3. send chat with detailed error ----------
def send_once(acc, room_id, msg):
    body = {
        "room_id": room_id,
        "msg": msg,
        "csrf_token": acc.get("csrf", ""),
        "request_id": str(int(time.time() * 1000)) + str(random.randint(100, 999)),
    }
    headers = {
        "User-Agent": UA_MOBILE,
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": acc["cookie"],
        "Referer": "https://www.tiktok.com/live",
        "Origin": "https://www.tiktok.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        r = requests.post(
            "https://webcast.tiktok.com/webcast/room/chat/",
            data=body, headers=headers, timeout=10)
        acc["sent"] += 1

        # HTTP 403 → signature required, not a cookie problem
        if r.status_code == 403:
            acc["err"] += 1
            acc["last_err"] = "HTTP 403 — X-Bogus signature required by TikTok"
            return 403

        if r.status_code != 200:
            acc["err"] += 1
            acc["last_err"] = f"HTTP {r.status_code}"
            return r.status_code

        # try parse json
        try:
            j = r.json()
        except Exception:
            acc["err"] += 1
            acc["last_err"] = "200 but body not json (likely X-Bogus block)"
            return "nojson"

        code = j.get("status_code")
        if code == 0:
            acc["ok"] += 1
            acc["last_err"] = ""
            return 0

        # known codes
        acc["err"] += 1
        if code == 20003:
            acc["last_err"] = "20003 — User doesn't login (bad sessionid/csrf)"
        elif code == 20005:
            acc["last_err"] = "20005 — Invalid csrf_token"
        elif code == 20002:
            acc["last_err"] = "20002 — Rate limited / too fast"
        else:
            acc["last_err"] = f"status_code={code} {j.get('data', {})}"
        return code

    except Exception as e:
        acc["sent"] += 1
        acc["err"] += 1
        acc["last_err"] = "exception: " + str(e)
        return "exc"


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
        return {"ok": False, "error": "missing room / msg / accounts"}

    # resolve
    unique_id, room_id, err = resolve_url(room_input)
    if err:
        return {"ok": False, "error": "resolve: " + err}

    # check live
    is_live, room_data, check_err = check_live(room_id)
    if not is_live:
        return {"ok": False, "error": "not live: " + str(check_err),
                "room_id": room_id, "unique_id": unique_id}

    accounts = []
    for a in raw:
        c = (a.get("cookie") or "").strip()
        if not c:
            continue
        accounts.append({
            "cookie": c,
            "csrf": (a.get("csrf") or "").strip(),
            "sent": 0, "ok": 0, "err": 0,
            "last_err": "",
        })
    if not accounts:
        return {"ok": False, "error": "no valid accounts"}

    state.update(room_url=room_input, room_id=room_id, msg=msg,
                 interval=interval, threads=threads, accounts=accounts)

    for acc in accounts:
        for _ in range(threads):
            t = threading.Thread(target=worker,
                                 args=(acc, room_id, msg, interval),
                                 daemon=True)
            t.start()
            workers.append(t)

    state["running"] = True
    return {"ok": True, "workers": len(workers),
            "accounts": len(accounts), "room_id": room_id,
            "unique_id": unique_id}


# ---------- check endpoint (frontend uses this) ----------
@app.route("/check", methods=["POST"])
def api_check():
    data = request.get_json(force=True, silent=True) or {}
    url = str(data.get("room", "")).strip()
    if not url:
        return jsonify({"ok": False, "error": "empty"})
    unique_id, room_id, err = resolve_url(url)
    if err:
        return jsonify({"ok": False, "error": err,
                        "unique_id": unique_id})
    is_live, room_data, check_err = check_live(room_id)
    if not is_live:
        return jsonify({"ok": False, "error": str(check_err),
                        "room_id": room_id, "unique_id": unique_id})
    room = room_data.get("room", {}) if room_data else {}
    return jsonify({
        "ok": True,
        "room_id": room_id,
        "unique_id": unique_id,
        "title": room.get("title", ""),
        "viewer_count": room.get("liveRoom", {}).get("liveRoomUserInfo", {}).get("user", {}).get("followInfo", {}).get("followerCount", 0),
        "status": room.get("status"),
    })


@app.route("/")
def health():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "nyx alive (index.html missing)"


@app.route("/status")
def status():
    with lock:
        return jsonify({
            "running": state["running"],
            "room_id": state["room_id"],
            "room_url": state["room_url"],
            "accounts": [{
                "cookie": a["cookie"][:10] + "...",
                "sent": a["sent"], "ok": a["ok"], "err": a["err"],
                "last_err": a.get("last_err", "")
            } for a in state["accounts"]],
            "totals": {
                "sent": sum(a["sent"] for a in state["accounts"]),
                "ok": sum(a["ok"] for a in state["accounts"]),
                "err": sum(a["err"] for a in state["accounts"]),
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