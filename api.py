import json
import threading
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

TN_TOKEN = "ce764d8e438a6b2519d26e21cb9c11dd7eedef5e"
TN_USER_ID = "6747288"
META_TOKEN = "EAASVCHqe8NABRibSS3Q6uTZCLrhCU5AvGaAQp8iBIKG8gTZC19DekTrGsT6rKDLoC54nVuZBiXXUm5pkPZA8oSLoSbMBVNR7mu5Ovn551g8TNxZCHGdj3X7ZCkx2mCjsazB8ubxnJWz2dLxEivWRZB0KKAFNHWcyc8yZCakrhak3CC3mrtyXIepn54Ws8ZAQGGAZDZD"
META_ACCOUNT = "25788023964160178"

ART = timezone(timedelta(hours=-3))
REFRESH_SECONDS = 300  # refresh every 5 minutes

_cached_response = None
_cache_lock = threading.Lock()

def http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode())

def parse_dt(s):
    s = s.replace("+0000", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.now(timezone.utc)

def fetch_tn_orders_full_day(date_art):
    day_start = datetime(date_art.year, date_art.month, date_art.day, tzinfo=ART)
    day_end = datetime(date_art.year, date_art.month, date_art.day, 23, 59, 59, tzinfo=ART)
    since_ts = day_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    until_ts = day_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    all_orders = []
    page = 1
    while True:
        url = (
            f"https://api.tiendanube.com/v1/{TN_USER_ID}/orders"
            f"?created_at_min={since_ts}&created_at_max={until_ts}"
            f"&per_page=200&page={page}&fields=id,total,created_at"
        )
        try:
            data = http_get(url, {
                "Authentication": f"bearer {TN_TOKEN}",
                "User-Agent": "Salitrada/1.0"
            })
            if not isinstance(data, list) or not data:
                break
            all_orders.extend(data)
            if len(data) < 200:
                break
            page += 1
        except Exception:
            break
    return all_orders

def fetch_meta_spend_batch(date_strs):
    time_ranges = json.dumps([{"since": d, "until": d} for d in date_strs])
    params = urllib.parse.urlencode({
        "fields": "spend,date_start",
        "time_ranges": time_ranges,
        "access_token": META_TOKEN
    })
    url = f"https://graph.facebook.com/v20.0/act_{META_ACCOUNT}/insights?{params}"
    try:
        data = http_get(url)
        return {item["date_start"]: float(item.get("spend", 0)) for item in data.get("data", [])}
    except Exception:
        return {}

def build_response():
    now_art = datetime.now(ART)
    today_str = now_art.strftime("%Y-%m-%d")
    past_dates = [now_art - timedelta(days=i) for i in range(1, 15)]
    past_date_strs = [d.strftime("%Y-%m-%d") for d in past_dates]

    def fetch_today():
        return fetch_tn_orders_full_day(now_art)

    def fetch_meta():
        return fetch_meta_spend_batch([today_str] + past_date_strs)

    past_orders = {}

    def fetch_past(d):
        return d, fetch_tn_orders_full_day(d)

    with ThreadPoolExecutor(max_workers=9) as executor:
        f_today = executor.submit(fetch_today)
        f_meta = executor.submit(fetch_meta)
        f_past_futures = {executor.submit(fetch_past, d): d for d in past_dates}

        today_orders_full = f_today.result()
        meta_batch = f_meta.result()
        for f in as_completed(f_past_futures):
            d, orders = f.result()
            past_orders[d] = orders

    cutoff_utc = now_art.astimezone(timezone.utc)
    today_orders = [o for o in today_orders_full if parse_dt(o["created_at"]) <= cutoff_utc]
    total = sum(float(o.get("total", 0)) for o in today_orders)
    count = len(today_orders)
    meta_spend = meta_batch.get(today_str, 0.0)
    roas = round(total / meta_spend, 2) if meta_spend > 0 else None

    comparacion = []
    for past_date in past_dates:
        date_str = past_date.strftime("%Y-%m-%d")
        orders = past_orders.get(past_date, [])
        cutoff = datetime(past_date.year, past_date.month, past_date.day,
                          now_art.hour, now_art.minute, now_art.second, tzinfo=ART)
        cutoff_utc_d = cutoff.astimezone(timezone.utc)
        partial = [o for o in orders if parse_dt(o["created_at"]) <= cutoff_utc_d]
        ventas_full = round(sum(float(o.get("total", 0)) for o in orders))
        meta = meta_batch.get(date_str, 0.0)
        roas_final = round(ventas_full / meta, 2) if meta > 0 else None
        comparacion.append({
            "label": past_date.strftime("%a %d/%m"),
            "ventas": round(sum(float(o.get("total", 0)) for o in partial)),
            "ordenes": len(partial),
            "meta_gasto": round(meta),
            "roas_final": roas_final
        })

    return {
        "fecha": today_str,
        "hora": now_art.strftime("%H:%M"),
        "ventas": round(total),
        "ordenes": count,
        "ticket_prom": round(total / count) if count > 0 else 0,
        "meta_gasto": round(meta_spend),
        "roas": roas,
        "actualizado": now_art.strftime("%H:%M ART"),
        "comparacion": comparacion
    }

def refresh_loop():
    global _cached_response
    while True:
        try:
            data = build_response()
            with _cache_lock:
                _cached_response = data
        except Exception:
            pass
        threading.Event().wait(REFRESH_SECONDS)

# Start background refresh on startup
threading.Thread(target=refresh_loop, daemon=True).start()

@app.route("/api/ventas")
def ventas():
    with _cache_lock:
        data = _cached_response
    if data is None:
        return jsonify({"error": "Cargando datos, intenta en 30 segundos..."}), 503
    return jsonify(data)

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
h1 { font-size:13px; letter-spacing:4px; color:#888; text-transform:uppercase; margin-bottom:28px; text-align:center; padding-top:16px; }
.card { background:#111; border-radius:16px; padding:20px; margin-bottom:12px; }
.label { font-size:10px; color:#bbb; letter-spacing:2px; text-transform:uppercase; margin-bottom:4px; }
.value { font-size:34px; font-weight:700; }
.green { color:#00e676; }
.yellow { color:#ffd600; }
.small { font-size:12px; color:#888; margin-top:4px; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:12px; }
.grid .card { margin-bottom:0; }
.grid .value { font-size:22px; }
.updated { text-align:center; font-size:11px; color:#333; margin:16px 0 8px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { color:#bbb; font-size:10px; letter-spacing:1px; text-transform:uppercase; padding:6px 8px; text-align:right; }
th:first-child { text-align:left; }
td { padding:8px 8px; border-top:1px solid #222; text-align:right; color:#ccc; }
td:first-child { text-align:left; color:#999; }
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
    if(d.error){ document.getElementById('ts').textContent = d.error; setTimeout(load, 5000); return; }
    document.getElementById('ts').textContent = 'Actualizado ' + d.actualizado;
    let rows = d.comparacion.map(c=>`
      <tr>
        <td>${c.label}</td>
        <td>${fmt(c.ventas)}</td>
        <td>${c.ordenes}</td>
        <td style="color:#ffd600">${c.meta_gasto ? fmt(c.meta_gasto) : '-'}</td>
        <td style="color:#ffd600">${c.roas_final ? c.roas_final+'x' : '-'}</td>
      </tr>`).join('');
    document.getElementById('data').innerHTML = `
      <div class="card">
        <div class="label">Ventas hoy · ${d.hora}</div>
        <div class="value green">${fmt(d.ventas)}</div>
        <div class="small">${d.ordenes} órdenes · ticket ${fmt(d.ticket_prom)}</div>
      </div>
      <div class="grid">
        <div class="card">
          <div class="label">Meta hoy (parcial)</div>
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
          <tr><th>Día</th><th>Ventas</th><th>Órd.</th><th>Meta</th><th>ROAS</th></tr>
          <tr class="hoy-row"><td>Hoy</td><td>${fmt(d.ventas)}</td><td>${d.ordenes}</td><td style="color:#ffd600">${fmt(d.meta_gasto)}</td><td style="color:#ffd600">${d.roas ? d.roas+'x' : '-'}</td></tr>
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
