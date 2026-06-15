import json
import subprocess
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

def fetch_tn_orders(since_ts, until_ts):
    url = (
        f"https://api.tiendanube.com/v1/{TN_USER_ID}/orders"
        f"?payment_status=paid&created_at_min={since_ts}&created_at_max={until_ts}"
        f"&per_page=200&fields=id,total,created_at"
    )
    cmd = ["curl", "-s", "-m", "30", "-H", f"Authentication: bearer {TN_TOKEN}",
           "-H", "User-Agent: Salitrada/1.0", url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
    except Exception:
        return []
    if isinstance(data, list):
        return data
    return []

def fetch_meta_spend(date_str):
    url = (
        f"https://graph.facebook.com/v20.0/act_{META_ACCOUNT}/insights"
        f"?fields=spend&time_range={{\"since\":\"{date_str}\",\"until\":\"{date_str}\"}}"
        f"&access_token={META_TOKEN}"
    )
    cmd = ["curl", "-s", "-m", "30", url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
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

    # Today: midnight ART = 03:00 UTC
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
    return "<h1>Salitrada API</h1><p><a href='/api/ventas'>/api/ventas</a></p>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
