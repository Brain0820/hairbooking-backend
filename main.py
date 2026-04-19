from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import psycopg2
import os

app = FastAPI()

# ===== CORS =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://brain0820.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== PostgreSQL =====
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)

# ===== 初始化資料表 =====
def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            pay_code TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

if DATABASE_URL:
    init_db()

# ===== Models =====
class Reservation(BaseModel):
    name: str
    phone: str
    paycode: str
    date: str
    time: str

# ===== Debug =====
@app.get("/_debug/db")
def debug_db():
    return {
        "DATABASE_URL_EXISTS": DATABASE_URL is not None,
        "DATABASE_URL_PREFIX": DATABASE_URL[:20] if DATABASE_URL else None,
        "DB_TYPE": "postgresql" if DATABASE_URL else "sqlite"
    }

# ======================================================
# ✅ 預約規則設定（你指定的）
# ======================================================

AVAILABLE_DATES = [
    "2026-04-24", "2026-04-26", "2026-04-29",
    "2026-05-01", "2026-05-02", "2026-05-06",
    "2026-05-08", "2026-05-09", "2026-05-10",
    "2026-05-13", "2026-05-15", "2026-05-16",
    "2026-05-17", "2026-05-20", "2026-05-22",
    "2026-05-23", "2026-05-24", "2026-05-27",
    "2026-05-29", "2026-05-30"
]

SPECIAL_TIME_RULES = {
    "2026-04-24": ("14:00", "18:00"),
    "2026-05-02": ("13:00", "17:00"),
    "2026-05-16": ("13:00", "17:00"),
    "2026-05-30": ("13:00", "17:00"),
}

DEFAULT_START = "13:00"
DEFAULT_END = "18:00"

WEEKDAY_MAP = ["一", "二", "三", "四", "五", "六", "日"]

# ======================================================
# ✅ 共用工具函式
# ======================================================

def get_reservation_count_by_date(date_str: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT time, COUNT(*)
        FROM reservations
        WHERE date = %s
        GROUP BY time
    """, (date_str,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {time: count for time, count in rows}

def generate_times(start_str, end_str):
    start = datetime.strptime(start_str, "%H:%M")
    end = datetime.strptime(end_str, "%H:%M")
    times = []
    current = start
    while current < end:
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=20)
    return times

def format_date_label(date_str: str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    md = f"{d.month}月{d.day}日"
    md_padded = md.ljust(6, "　")  # 全形空白對齊
    weekday = WEEKDAY_MAP[d.weekday()]
    return f"{md_padded}（{weekday}）"

# ======================================================
# ✅ API：取得可預約日期
# ======================================================

@app.get("/available-dates")
def available_dates():
    results = []

    for d in AVAILABLE_DATES:
        start, end = SPECIAL_TIME_RULES.get(d, (DEFAULT_START, DEFAULT_END))
        all_times = generate_times(start, end)
        counts = get_reservation_count_by_date(d)

        if all(counts.get(t, 0) >= 2 for t in all_times):
            continue  # 整天滿，不回傳

        results.append({
            "value": d,
            "label": format_date_label(d)
        })

    return results

# ======================================================
# ✅ API：取得某日可預約時間
# ======================================================

@app.get("/available-times")
def available_times(date: str):
    start, end = SPECIAL_TIME_RULES.get(date, (DEFAULT_START, DEFAULT_END))
    all_times = generate_times(start, end)
    counts = get_reservation_count_by_date(date)

    return [t for t in all_times if counts.get(t, 0) < 2]

# ======================================================
# ✅ 新增預約
# ======================================================

@app.post("/reserve")
def reserve(r: Reservation):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) FROM reservations WHERE date=%s AND time=%s",
        (r.date, r.time)
    )
    count = cur.fetchone()[0]

    if count >= 2:
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="此時段已滿")

    cur.execute("""
        INSERT INTO reservations (name, phone, pay_code, date, time, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (r.name, r.phone, r.paycode, r.date, r.time, datetime.now()))

    conn.commit()
    cur.close()
    conn.close()

    return {"message": "預約成功"}

# ======================================================
# ✅ 後台
# ======================================================

@app.get("/admin", response_class=HTMLResponse)
def admin():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT date, time, name, phone, pay_code
        FROM reservations
        ORDER BY date, time, created_at
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    data = {}
    for date, time, name, phone, code in rows:
        data.setdefault((date, time), []).append((name, phone, code))

    html = """
    <html><head><meta charset="utf-8">
    <title>預約後台</title>
    <style>
    body { font-family: Arial; padding: 30px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #000; padding: 8px; vertical-align: top; }
    th { background-color: #f0f0f0; }
    </style></head><body>
    <h2>預約狀態</h2><table>
    <tr><th>日期</th><th>時間</th><th>人數</th><th>名單</th></tr>
    """

    for (date, time), people in data.items():
        html += f"<tr><td>{date}</td><td>{time}</td>"
        html += f"<td>{len(people)} / 2</td><td>"
        for i, (n, p, c) in enumerate(people, 1):
            html += f"{i}. {n}｜{p}｜{c}<br>"
        html += "</td></tr>"

    html += "</table></body></html>"
    return html
