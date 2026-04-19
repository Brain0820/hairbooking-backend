from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
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
# ✅ 後台：刪除單筆預約（作法 1）
# ======================================================
@app.post("/admin/delete/{reservation_id}")
def delete_reservation(reservation_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM reservations WHERE id = %s", (reservation_id,))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)

# ======================================================
# ✅ 後台（先日期 → 再時間 → 正序）
# ======================================================
@app.get("/admin", response_class=HTMLResponse)
def admin():
    conn = get_db()
    cur = conn.cursor()

    # ✅ 含 id + 正確排序
    cur.execute("""
        SELECT id, date, time, name, phone, pay_code
        FROM reservations
        ORDER BY date ASC, time ASC, created_at ASC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # 按 (date, time) 分組
    data = {}
    for rid, date, time, name, phone, code in rows:
        data.setdefault((date, time), []).append(
            {"id": rid, "name": name, "phone": phone, "code": code}
        )

    html = """
    <html><head><meta charset="utf-8">
    <title>預約後台</title>
    <style>
    body { font-family: Arial; padding: 30px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #000; padding: 8px; vertical-align: top; }
    th { background-color: #f0f0f0; }
    form { display:inline; }
    button { margin-left: 8px; }
    </style></head><body>
    <h2>預約狀態</h2>
    <table>
      <tr>
        <th>日期</th>
        <th>時間</th>
        <th>人數</th>
        <th>名單</th>
      </tr>
    """

    for (date, time), people in data.items():
        html += f"<tr><td>{date}</td><td>{time}</td>"
        html += f"<td>{len(people)} / 2</td><td>"

        for idx, p in enumerate(people, 1):
            html += f"""
            {idx}. {p['name']}｜{p['phone']}｜{p['code']}
            <form method="post" action="/admin/delete/{p['id']}"
                  onsubmit="return confirm('確定要刪除這筆預約嗎？');">
                <button type="submit">刪除</button>
            </form>
            <br>
            """

        html += "</td></tr>"

    html += "</table></body></html>"
    return html
