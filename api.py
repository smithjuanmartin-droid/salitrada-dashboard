import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

TN_TOKEN = "ce764d8e438a6b2519d26e21cb9c11dd7eedef5e"
TN_USER_ID = "6747288"
META_TOKEN = "EAASVCHqe8NABRibSS3Q6uTZCLrhCU5AvGaAQp8iBIKG8gTZC19DekTrGsT6rKDLoC54nVuZBiXXUm5pkPZA8oSLoSbMBVNR7mu5Ovn551g8TNxZCHGdj3X7ZCkx2mCjsazB8ubxnJWz2dLxEivWRZB0KKAFNHWcyc8yZCakrhak3CC3mrtyXIepn54Ws8ZAQGGAZDZD"
META_ACCOUNT = "25788023964160178"

ART = timezone(timedelta(hours=-3))

def http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def fetch_tn_orders(since_ts, until_ts):
    url = (
        f"https://api.tiendanube.com/v1/{TN_USER_ID}/orders"
        f"?payment_status=paid&created_at_min={since_ts}&created_at_max={until_ts}"
        f"&per_page=200&fields=id,total,created_at"
    )
    try:
        data = http_get(url, {
            "Authentication": f"bearer {TN_TOKEN}",
            "User-Agent": "Salitrada/1.0"
        })
        return data if isinstance(data, list) else []
    except Exception:
        return []

def fetch_meta_spend(date_str):
    params = urllib.parse.urlencode({
        "fields": "spend",
        "time_range": json.dumps({"since": date_str, "until": date_str}),
        "access_token": META_TOKEN
    })
    url = f"https://graph.facebook.com/v20.0/act_{META_ACCOUNT}/insights?{params}"
    try:
        data = http_get(url)
        items = data.get("data", [])
        if items:
            return float(items[0].get("spend", 0))
    except Exception:
        pass
    return 0.0

@app.route("/api/ventas")
def ventas():
    now_art = datetime.now(ART)
    today_str = now_art.strftime("%Y-%m-%d")

    day_start_utc = datetime(now_art.year, now_art.month, now_art.day,
                             tzinfo=ART).astimezone(timezone.utc)
    since_ts = day_start_utc.strftime("%Y-%m-%dT%H:%M:%S")
    until_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    orders = fetch_tn_orders(since_ts, until_ts)
    total = sum(float(o.get("total", 0)) for o in orders)
    count = len(orders)

    meta_spend = fetch_meta_spend(today_str)
    roas = round(total / meta_spend, 2) if meta_spend > 0 else None

    return jsonify({
        "fecha": today_str,
        "hora": now_art.strftime("%H:%M"),
        "ventas": round(total),
        "ordenes": count,
        "ticket_prom": round(total / count) if count > 0 else 0,
        "meta_gasto": round(meta_spend),
        "roas": roas,
        "actualizado": now_art.strftime("%H:%M ART")
    })

@app.route("/")
def index():
    return """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>SALITRADA</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#0a0a0a; color:#fff; font-family:-apple-system,sans-serif; min-height:100vh; display:flex; align-items:center; justify-content:center; }
.container { width:100%; max-width:400px; padding:24px; }
h1 { font-size:13px; letter-spacing:4px; color:#555; text-transform:uppercase; margin-bottom:32px; text-align:center; }
.card { background:#111; border-radius:16px; padding:24px; margin-bottom:16px; }
.label { font-size:11px; color:#555; letter-spacing:2px; text-transform:uppercase; margin-bottom:6px; }
.value { font-size:36px; font-weight:700; color:#fff; }
.value.green { color:#00e676; }
.value.yellow { color:#ffd600; }
.small { font-size:13px; color:#888; margin-top:4px; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.updated { text-align:center; font-size:11px; color:#333; margin-top:24px; }
</style>
</head>
<body>
<div class="container">
  <h1>Salitrada</h1>
  <div id="data">Cargando...</div>
  <div class="updated" id="ts"></div>
</div>
<script>
fetch('/api/ventas').then(r=>r.json()).then(d=>{
  document.getElementById('ts').textContent = 'Actualizado ' + d.actualizado;
  document.getElementById('data').innerHTML = `
    <div class="card">
      <div class="label">Ventas hoy</div>
      <div class="value green">$${d.ventas.toLocaleString('es-AR')}</div>
      <div class="small">${d.ordenes} órdenes · ticket $${d.ticket_prom.toLocaleString('es-AR')}</div>
    </div>
    <div class="grid">
      <div class="card">
        <div class="label">Meta gasto</div>
        <div class="value yellow" style="font-size:24px">$${d.meta_gasto.toLocaleString('es-AR')}</div>
      </div>
      <div class="card">
        <div class="label">ROAS</div>
        <div class="value yellow" style="font-size:24px">${d.roas ? d.roas+'x' : '-'}</div>
      </div>
    </div>`;
}).catch(()=>{ document.getElementById('data').textContent = 'Error al cargar'; });
</script>
</body>
</html>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
