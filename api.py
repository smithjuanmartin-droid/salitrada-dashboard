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

def day_sales_until_hour(date_art, until_hour_art):
    day_start = datetime(date_art.year, date_art.month, date_art.day, tzinfo=ART)
    day_end = datetime(date_art.year, date_art.month, date_art.day,
                       until_hour_art.hour, until_hour_art.minute, until_hour_art.second, tzinfo=ART)
    since_ts = day_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    until_ts = day_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    orders = fetch_tn_orders(since_ts, until_ts)
    total = sum(float(o.get("total", 0)) for o in orders)
    return round(total), len(orders)

@app.route("/api/ventas")
def ventas():
    now_art = datetime.now(ART)
    today_str = now_art.strftime("%Y-%m-%d")

    day_start_utc = datetime(now_art.year, now_art.month, now_art.day, tzinfo=ART).astimezone(timezone.utc)
    since_ts = day_start_utc.strftime("%Y-%m-%dT%H:%M:%S")
    until_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    orders = fetch_tn_orders(since_ts, until_ts)
    total = sum(float(o.get("total", 0)) for o in orders)
    count = len(orders)

    meta_spend = fetch_meta_spend(today_str)
    roas = round(total / meta_spend, 2) if meta_spend > 0 else None

    # Last 14 days comparison (same hour)
    comparacion = []
    for i in range(1, 15):
        past_date = now_art - timedelta(days=i)
        venta, ordenes = day_sales_until_hour(past_date, now_art)
        comparacion.append({
            "label": past_date.strftime("%a %d/%m"),
            "ventas": venta,
            "ordenes": ordenes
        })

    return jsonify({
        "fecha": today_str,
        "hora": now_art.strftime("%H:%M"),
        "ventas": round(total),
        "ordenes": count,
        "ticket_prom": round(total / count) if count > 0 else 0,
        "meta_gasto": round(meta_spend),
        "roas": roas,
        "actualizado": now_art.strftime("%H:%M ART"),
        "comparacion": comparacion
    })

@app.route("/")
def index():
    return """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SALITRADA</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#0a0a0a; color:#fff; font-family:-apple-system,sans-serif; }
.container { width:100%; max-width:420px; margin:0 auto; padding:24px; }
h1 { font-size:13px; letter-spacing:4px; color:#555; text-transform:uppercase; margin-bottom:28px; text-align:center; padding-top:16px; }
.card { background:#111; border-radius:16px; padding:20px; margin-bottom:12px; }
.label { font-size:10px; color:#555; letter-spacing:2px; text-transform:uppercase; margin-bottom:4px; }
.value { font-size:34px; font-weight:700; }
.green { color:#00e676; }
.yellow { color:#ffd600; }
.small { font-size:12px; color:#888; margin-top:4px; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:12px; }
.grid .card { margin-bottom:0; }
.grid .value { font-size:22px; }
.updated { text-align:center; font-size:11px; color:#333; margin:16px 0 8px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { color:#555; font-size:10px; letter-spacing:1px; text-transform:uppercase; padding:6px 8px; text-align:right; }
th:first-child { text-align:left; }
td { padding:8px 8px; border-top:1px solid #1a1a1a; text-align:right; color:#aaa; }
td:first-child { text-align:left; color:#666; }
.hoy-row td { color:#fff; font-weight:600; }
.hoy-row td:nth-child(2) { color:#00e676; }
.refresh-btn { display:block; width:100%; background:#1a1a1a; color:#555; border:none; border-radius:12px; padding:12px; font-size:12px; letter-spacing:2px; text-transform:uppercase; cursor:pointer; margin-top:16px; }
</style>
</head>
<body>
<div class="container">
  <h1>Salitrada</h1>
  <div id="data">Cargando...</div>
  <div class="updated" id="ts"></div>
  <button class="refresh-btn" onclick="load()">Actualizar</button>
</div>
<script>
function fmt(n){ return '$'+n.toLocaleString('es-AR'); }
function load(){
  document.getElementById('ts').textContent = 'Actualizando...';
  fetch('/api/ventas?t='+Date.now()).then(r=>r.json()).then(d=>{
    document.getElementById('ts').textContent = 'Actualizado ' + d.actualizado;
    let rows = d.comparacion.map(c=>`
      <tr>
        <td>${c.label}</td>
        <td>${fmt(c.ventas)}</td>
        <td>${c.ordenes}</td>
      </tr>`).join('');
    document.getElementById('data').innerHTML = `
      <div class="card">
        <div class="label">Ventas hoy · ${d.hora}</div>
        <div class="value green">${fmt(d.ventas)}</div>
        <div class="small">${d.ordenes} órdenes · ticket ${fmt(d.ticket_prom)}</div>
      </div>
      <div class="grid">
        <div class="card">
          <div class="label">Meta gasto</div>
          <div class="value yellow">${fmt(d.meta_gasto)}</div>
        </div>
        <div class="card">
          <div class="label">ROAS</div>
          <div class="value yellow">${d.roas ? d.roas+'x' : '-'}</div>
        </div>
      </div>
      <div class="card">
        <div class="label">Últimas 2 semanas · misma hora</div>
        <table>
          <tr><th>Día</th><th>Ventas</th><th>Órd.</th></tr>
          <tr class="hoy-row"><td>Hoy</td><td>${fmt(d.ventas)}</td><td>${d.ordenes}</td></tr>
          ${rows}
        </table>
      </div>`;
  }).catch(()=>{ document.getElementById('ts').textContent = 'Error al cargar'; });
}
load();
</script>
</body>
</html>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
