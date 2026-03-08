from flask import Flask, render_template_string, request, redirect, url_for, session, abort, jsonify, Response
import sqlite3
import requests
import urllib.parse
import re
import csv
import io
from datetime import datetime, timedelta

# ==========================================
# ⚙️ Configuration
# ==========================================
APP_SECRET = "conchit_secret_key_999"
CLIENT_ID = "1464889370120159304"
CLIENT_SECRET = "TvfqxXUvb5onKb83yLUtgQ-zhbNDNchN"
REDIRECT_URI ="https://factual-bessie-murkily.ngrok-free.dev/callback"
DB_NAME = "scammers.db"
ADMIN_IDS = ["1188722703222452247", "775362563655073793", "1417060878045679710"]
READONLY_ADMIN_ID = "1417060878045679710"  # 담늘 - 조회만 가능, 제어 불가
LOGIN_PASSWORD = "0106"
LOGO_URL = "https://media.discordapp.net/attachments/1426914854731517982/1478766498179846154/ae722e7e8eb25739.gif?ex=69ace3df&is=69ab925f&hm=970dce11be44f553a3afae349016a5f414e4166b469e162e5a68ad49dbe5502d&="

ADMIN_WEBHOOK_URL = "https://discord.com/api/webhooks/1477300631948492881/X-9N5wEYUdwmk6jSlu1ybKdxUeXLdKBn8WAOyqvN9qFGmzRRgErK5OpEJfjw8GmfAuFX"
SUPPORT_SERVER_URL = "https://discord.gg/cKhHyGNytk"

app = Flask(__name__)
app.secret_key = APP_SECRET

# ==========================================
# 🗄️ Database
# ==========================================
def get_conn():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS scammers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unique_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        amount_display TEXT NOT NULL,
        amount_int INTEGER DEFAULT 0,
        reporter_id INTEGER NOT NULL,
        category TEXT DEFAULT '주사위',
        evidence_url TEXT,
        reason TEXT DEFAULT '',
        date TEXT NOT NULL,
        admin_memo TEXT DEFAULT '',
        victim_id TEXT DEFAULT '',
        victim_name TEXT DEFAULT ''
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_unique_id INTEGER NOT NULL,
        target_name TEXT NOT NULL,
        amount_display TEXT NOT NULL,
        amount_int INTEGER DEFAULT 0,
        category TEXT DEFAULT '주사위',
        reason TEXT,
        evidence_url TEXT,
        reporter_id TEXT NOT NULL,
        reporter_name TEXT NOT NULL,
        status TEXT DEFAULT '대기중',
        admin_reply TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id TEXT NOT NULL,
        action TEXT NOT NULL,
        target_info TEXT,
        timestamp TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        notice_type TEXT DEFAULT '공지',
        created_at TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS appeals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unique_id INTEGER NOT NULL,
        reason TEXT NOT NULL,
        contact TEXT NOT NULL,
        status TEXT DEFAULT '대기중',
        admin_reply TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS reporter_blacklist (
        user_id TEXT PRIMARY KEY,
        reason TEXT,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS hall_of_fame (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        badge TEXT DEFAULT '',
        amount TEXT DEFAULT '',
        amount_int INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""")
    # 스키마 업데이트
    try:
        scammer_cols = [r["name"] for r in cur.execute("PRAGMA table_info(scammers)").fetchall()]
        if "category" not in scammer_cols: cur.execute("ALTER TABLE scammers ADD COLUMN category TEXT DEFAULT '주사위'")
        if "evidence_url" not in scammer_cols: cur.execute("ALTER TABLE scammers ADD COLUMN evidence_url TEXT")
        if "admin_memo" not in scammer_cols: cur.execute("ALTER TABLE scammers ADD COLUMN admin_memo TEXT DEFAULT ''")
        if "reason" not in scammer_cols: cur.execute("ALTER TABLE scammers ADD COLUMN reason TEXT DEFAULT ''")
        if "victim_id" not in scammer_cols: cur.execute("ALTER TABLE scammers ADD COLUMN victim_id TEXT DEFAULT ''")
        if "victim_name" not in scammer_cols: cur.execute("ALTER TABLE scammers ADD COLUMN victim_name TEXT DEFAULT ''")
        if "item_name" not in scammer_cols: cur.execute("ALTER TABLE scammers ADD COLUMN item_name TEXT DEFAULT ''")

        report_cols = [r["name"] for r in cur.execute("PRAGMA table_info(reports)").fetchall()]
        if "category" not in report_cols: cur.execute("ALTER TABLE reports ADD COLUMN category TEXT DEFAULT '주사위'")
        if "evidence_url" not in report_cols: cur.execute("ALTER TABLE reports ADD COLUMN evidence_url TEXT")
        if "admin_reply" not in report_cols: cur.execute("ALTER TABLE reports ADD COLUMN admin_reply TEXT DEFAULT ''")

        notice_cols = [r["name"] for r in cur.execute("PRAGMA table_info(notices)").fetchall()]
        if "notice_type" not in notice_cols: cur.execute("ALTER TABLE notices ADD COLUMN notice_type TEXT DEFAULT '공지'")
        hof_cols = [r["name"] for r in cur.execute("PRAGMA table_info(hall_of_fame)").fetchall()]
        if "amount_int" not in hof_cols: cur.execute("ALTER TABLE hall_of_fame ADD COLUMN amount_int INTEGER DEFAULT 0")
    except Exception as e:
        pass

    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🛠️ Utilities
# ==========================================
def korean_amount(n):
    try:
        n = int(n)
    except:
        return "0원"
    if n <= 0: return "0원"
    if n < 10000:
        return f"{n:,}원"
    jo  = n // 1000000000000
    uk  = (n % 1000000000000) // 100000000
    man = (n % 100000000) // 10000
    chun = (n % 10000) // 1000
    baek = (n % 1000) // 100
    parts = []
    if jo:  parts.append(f"{jo}조")
    if uk:  parts.append(f"{uk}억")
    if man: parts.append(f"{man}만")
    if chun: parts.append(f"{chun}천")
    if baek: parts.append(f"{baek}백")
    return "".join(parts) + "원" if parts else f"{n}원"

def parse_amount(raw: str):
    if not raw: return 0, "0원"
    digits = re.sub(r"[^\d]", "", str(raw))
    if not digits: return 0, "0원"
    n = int(digits)
    return n, f"{n:,}원"

def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def format_amount_int(v):
    try: return f"{int(v):,}원"
    except: return "0원"

def korean_amount_hof(raw):
    """후원의 전당용 - '1만원', '100만원', '1억원' 형태"""
    if not raw: return ""
    digits = re.sub(r"[^\d]", "", str(raw))
    if not digits: return str(raw)
    n = int(digits)
    if n <= 0: return "0원"
    jo  = n // 1000000000000
    uk  = (n % 1000000000000) // 100000000
    man = (n % 100000000) // 10000
    rem = n % 10000
    parts = []
    if jo:  parts.append(f"{jo}조")
    if uk:  parts.append(f"{uk}억")
    if man: parts.append(f"{man}만")
    if rem: parts.append(f"{rem:,}")
    return "".join(parts) + "원" if parts else f"{n:,}원"

def get_login_password():
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key='login_password'").fetchone()
    conn.close()
    return row["value"] if row else LOGIN_PASSWORD

def set_login_password(new_pw):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('login_password', ?)", (new_pw,))
    conn.commit()
    conn.close()

def is_admin(u):
    return bool(u and str(u.get("id")) in ADMIN_IDS)

def is_readonly_admin(u):
    """담늘 - 관리자 패널 접근은 가능하지만 제어(추가/수정/삭제)는 불가"""
    return bool(u and str(u.get("id")) == READONLY_ADMIN_ID)

def is_blacklisted(conn, user_id):
    row = conn.execute("SELECT user_id FROM reporter_blacklist WHERE user_id = ?", (str(user_id),)).fetchone()
    return bool(row)

def discord_auth_url():
    p = {"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code", "scope": "identify"}
    return f"https://discord.com/api/oauth2/authorize?{urllib.parse.urlencode(p)}"

def get_stats(conn):
    total_cases = conn.execute("SELECT COUNT(DISTINCT unique_id) as c FROM scammers").fetchone()["c"]
    total_amount_row = conn.execute("SELECT COALESCE(SUM(amount_int),0) as s FROM scammers").fetchone()
    recent_24 = conn.execute("SELECT COUNT(*) as c FROM scammers WHERE date >= ?",
        ((datetime.utcnow()-timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),)).fetchone()["c"]
    last7 = conn.execute("SELECT COUNT(*) as c FROM scammers WHERE date >= ?",
        ((datetime.utcnow()-timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),)).fetchone()["c"]
    trend_data = conn.execute("""
        SELECT substr(date, 1, 10) as day, COUNT(*) as cnt
        FROM scammers WHERE date >= ? GROUP BY day ORDER BY day ASC
    """, ((datetime.utcnow()-timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),)).fetchall()
    labels = [r["day"] for r in trend_data]
    counts = [r["cnt"] for r in trend_data]
    s = total_amount_row["s"]
    return {
        "total_cases": total_cases,
        "total_amount": format_amount_int(s),
        "total_amount_korean": korean_amount(s),
        "recent_24": recent_24,
        "last7": last7,
        "labels": labels,
        "counts": counts
    }

def log_admin_action(conn, admin_id, action, target_info):
    conn.execute("INSERT INTO audit_logs (admin_id, action, target_info, timestamp) VALUES (?, ?, ?, ?)",
                 (admin_id, action, target_info, now_iso()))

# ==========================================
# 🎨 BASE STYLE
# ==========================================
BASE_STYLE = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
:root {
    --bg-base: #13162a;
    --bg-surface: #1a1e35;
    --bg-elevated: #22273f;
    --border-color: #333a5a;
    --primary: #6db3ff;
    --primary-hover: #5aa3f5;
    --primary-glow: rgba(109, 179, 255, 0.28);
    --accent: #b79fff;
    --accent-glow: rgba(183, 159, 255, 0.22);
    --text-main: #edf0f8;
    --text-muted: #8e9bbf;
    --danger: #ff6b8a;
    --danger-glow: rgba(255, 107, 138, 0.22);
    --success: #22f0b5;
    --success-glow: rgba(34, 240, 181, 0.22);
    --warning: #ffd166;
    --warning-glow: rgba(255, 209, 102, 0.22);
    --card-shadow: 0 4px 24px rgba(0, 0, 0, 0.35), 0 1px 4px rgba(0,0,0,0.25);
    --card-shadow-hover: 0 8px 40px rgba(0, 0, 0, 0.45), 0 2px 8px rgba(109,179,255,0.12);
    --glow-blue: 0 0 20px rgba(109, 179, 255, 0.18);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    background-color: var(--bg-base);
    background-image: radial-gradient(ellipse at 20% 10%, rgba(109,179,255,0.08) 0%, transparent 50%),
                      radial-gradient(ellipse at 80% 90%, rgba(183,159,255,0.07) 0%, transparent 50%);
    color: var(--text-main);
    font-family: 'Pretendard', system-ui, sans-serif;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    line-height: 1.6;
}
input, textarea, select, button { font-family: 'Pretendard', system-ui, sans-serif; }
input::placeholder, textarea::placeholder { font-family: 'Pretendard', system-ui, sans-serif; color: var(--text-muted); }
a { color: var(--primary); text-decoration: none; transition: 0.2s; }
a:hover { color: var(--primary-hover); }
h1, h2, h3, h4 { font-weight: 700; color: #ffffff; }
.hint { color: var(--text-muted); font-size: 13.5px; }
.input, select.input, textarea.input {
    width: 100%; padding: 14px 16px; border-radius: 10px;
    border: 1px solid var(--border-color); background: rgba(34,39,63,0.9);
    color: #ffffff; outline: none; transition: border-color 0.2s, box-shadow 0.2s;
    font-size: 15px; backdrop-filter: blur(4px);
    font-family: 'Pretendard', system-ui, sans-serif;
}
.input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-glow); }
textarea.input { resize: vertical; min-height: 100px; }
.btn {
    background: linear-gradient(135deg, var(--primary), #4a8ef0);
    color: #fff; padding: 12px 22px; border-radius: 10px; border: none;
    font-weight: 700; cursor: pointer; transition: all 0.2s;
    font-size: 15px; display: inline-flex; align-items: center;
    justify-content: center; gap: 8px; text-decoration: none;
    box-shadow: 0 4px 14px rgba(91,159,255,0.3);
}
.btn:hover {
    background: linear-gradient(135deg, #4a8ef0, #3a7de0);
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(91,159,255,0.45);
    color: #fff;
}
.btn:active { transform: translateY(0); }
.btn-danger { background: linear-gradient(135deg, var(--danger), #e04060); box-shadow: 0 4px 14px var(--danger-glow); }
.btn-danger:hover { background: linear-gradient(135deg, #e04060, #c0304a); box-shadow: 0 6px 20px rgba(255,94,122,0.4); }
.btn-success { background: linear-gradient(135deg, var(--success), #0cba85); box-shadow: 0 4px 14px var(--success-glow); color: #0d0f17; }
.btn-success:hover { box-shadow: 0 6px 20px rgba(16,230,166,0.4); }
.btn-outline {
    background: transparent; border: 1px solid var(--border-color);
    color: var(--text-main); box-shadow: none;
}
.btn-outline:hover { background: var(--bg-elevated); border-color: var(--primary); color: #fff; box-shadow: 0 4px 14px var(--primary-glow); }
.smallbtn {
    padding: 6px 12px; border-radius: 7px; border: none; color: #fff;
    cursor: pointer; font-weight: 600; font-size: 13px; transition: all 0.2s;
    text-decoration: none; display: inline-block;
}
.smallbtn:hover { filter: brightness(1.15); transform: translateY(-1px); }
.container { max-width: 1100px; margin: 0 auto; padding: 32px 20px; width: 100%; flex: 1; }
.card {
    background: var(--bg-surface);
    padding: 28px;
    border-radius: 16px;
    border: 1px solid var(--border-color);
    box-shadow: var(--card-shadow);
    margin-bottom: 24px;
    transition: box-shadow 0.3s, transform 0.2s;
    position: relative;
    overflow: hidden;
}
.card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(91,159,255,0.2), transparent);
}
.card:hover { box-shadow: var(--card-shadow-hover); }
.grid3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px; margin-bottom: 24px; }
.stat {
    background: var(--bg-elevated);
    padding: 24px;
    border-radius: 14px;
    border: 1px solid var(--border-color);
    text-align: center;
    transition: all 0.3s;
    box-shadow: 0 2px 12px rgba(0,0,0,0.3);
}
.stat:hover { transform: translateY(-3px); box-shadow: 0 8px 30px rgba(0,0,0,0.4), var(--glow-blue); border-color: rgba(91,159,255,0.3); }
.table-wrapper { overflow-x: auto; border-radius: 10px; }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { padding: 14px 16px; text-align: left; border-bottom: 1px solid var(--border-color); }
.table th { color: var(--text-muted); font-size: 13px; background: var(--bg-elevated); text-transform: uppercase; letter-spacing: 0.5px; }
.table tr:hover td { background: rgba(91,159,255,0.04); }
.badge { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 700; background: #252b40; border: 1px solid #3a4060; color: var(--text-muted); }
.badge.status-승인됨 { color: #0d0f17; background: var(--success); border-color: var(--success); box-shadow: 0 2px 8px var(--success-glow); }
.badge.status-거절됨 { color: #fff; background: var(--danger); border-color: var(--danger); box-shadow: 0 2px 8px var(--danger-glow); }
.badge.status-대기중 { color: #0d0f17; background: var(--warning); border-color: var(--warning); box-shadow: 0 2px 8px var(--warning-glow); }
.marquee-container {
    background: linear-gradient(90deg, #0d0f17, #161926, #0d0f17);
    border-bottom: 1px solid var(--border-color);
    padding: 0; font-size: 14px; display: flex; align-items: stretch; overflow: hidden; height: 38px;
}
.marquee-label { padding: 0 16px; font-weight: 700; color: var(--danger); white-space: nowrap; flex-shrink: 0; display: flex; align-items: center; gap: 6px; border-right: 1px solid var(--border-color); background: rgba(255,94,122,0.06); }
.marquee-track { flex: 1; overflow: hidden; position: relative; display: flex; align-items: center; }
.marquee-inner { display: flex; gap: 0; white-space: nowrap; animation: marqueeSlide 40s linear infinite; will-change: transform; }
.marquee-inner:hover { animation-play-state: paused; }
.marquee-item { display: inline-flex; align-items: center; gap: 6px; padding: 0 28px 0 0; }
@keyframes marqueeSlide { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
.pagination { display: flex; gap: 8px; justify-content: center; margin-top: 24px; flex-wrap: wrap; }
.pagination a {
    padding: 8px 16px; background: var(--bg-elevated); border: 1px solid var(--border-color);
    border-radius: 8px; color: var(--text-main); font-size: 14px; transition: all 0.2s;
}
.pagination a:hover { border-color: var(--primary); background: rgba(91,159,255,0.1); color: #fff; }
.pagination a.active { background: linear-gradient(135deg, var(--primary), #4a8ef0); color: #fff; border-color: var(--primary); font-weight: bold; box-shadow: 0 4px 14px var(--primary-glow); }
@media (max-width: 600px) {
    .container { padding: 20px 14px; }
    .card { padding: 18px; border-radius: 12px; }
    .grid3 { grid-template-columns: 1fr; }
    .btn { padding: 11px 16px; font-size: 14px; }
    .table th, .table td { padding: 10px 10px; font-size: 13px; }
}
@media (max-width: 900px) {
    .home-grid { grid-template-columns: 1fr !important; }
}
@keyframes heartbeat { 0%,100%{transform:scale(1);} 50%{transform:scale(1.18);} }
@keyframes floatHeart { 0%{transform:translateY(0) scale(1);opacity:0.8;} 100%{transform:translateY(-120px) scale(0.5);opacity:0;} }
</style>
"""


# ==========================================
# 🚫 ERROR PAGE TEMPLATE
# ==========================================
ERROR_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FREEDOM - 오류</title>
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet"/>
""" + BASE_STYLE + """
<style>
html, body { height:100%; }
.err-wrap { min-height:100vh; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:40px 20px; text-align:center; }
.err-icon { font-size:72px; margin-bottom:24px; }
.err-code { font-size:96px; font-weight:900; background:linear-gradient(135deg,var(--danger),#e04060); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; line-height:1; margin-bottom:8px; letter-spacing:-4px; }
.err-title { font-size:24px; font-weight:800; color:#fff; margin-bottom:12px; }
.err-desc { font-size:15px; color:var(--text-muted); max-width:400px; line-height:1.8; margin-bottom:36px; }
.err-btn { display:inline-flex; align-items:center; gap:9px; padding:14px 28px; border-radius:12px; background:linear-gradient(135deg,var(--primary),#4a8ef0); color:#fff; font-weight:700; font-size:15px; text-decoration:none; box-shadow:0 6px 24px var(--primary-glow); transition:all 0.25s; }
.err-btn:hover { transform:translateY(-2px); box-shadow:0 10px 32px rgba(91,159,255,0.5); color:#fff; }
</style>
</head><body>
<div class="err-wrap">
  <div class="err-icon">🚫</div>
  <div class="err-code">{{ code }}</div>
  <div class="err-title">{{ title }}</div>
  <div class="err-desc">{{ desc }}</div>
  <a href="{{ back_url }}" class="err-btn"><i class="fas fa-arrow-left"></i> {{ back_text }}</a>
</div>
</body></html>"""

# ==========================================
# 🔐 LOGIN TEMPLATE (비밀번호 방식)
# ==========================================
LOGIN_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FREEDOM - 블랙리스트 조회</title>
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet"/>
""" + BASE_STYLE + """
<style>
html, body { height: 100%; overflow: hidden; }
body { display: flex; flex-direction: row; min-height: 100vh; }

.login-left {
    flex: 1; position: relative;
    background: linear-gradient(145deg, #0d0f17 0%, #0f1630 40%, #0d0f17 100%);
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 60px 48px;
    overflow: hidden;
}
.login-left::before {
    content: '';
    position: absolute; inset: 0;
    background:
        radial-gradient(ellipse at 30% 20%, rgba(91,159,255,0.18) 0%, transparent 55%),
        radial-gradient(ellipse at 75% 80%, rgba(167,139,250,0.14) 0%, transparent 50%);
}
.login-left-content { position: relative; z-index: 1; width: 100%; max-width: 460px; }
.big-logo {
    width: 88px; height: 88px;
    border-radius: 22px;
    overflow: hidden;
    margin-bottom: 32px;
    box-shadow: 0 12px 40px rgba(91,159,255,0.35);
    border: 2px solid rgba(91,159,255,0.3);
}
.big-logo img { width: 100%; height: 100%; object-fit: cover; }
.login-title { font-size: clamp(36px,4vw,52px); font-weight: 900; color: #fff; line-height: 1.1; letter-spacing: -2px; margin-bottom: 16px; }
.login-title span { background: linear-gradient(135deg,var(--primary),var(--accent)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
.login-desc { font-size: 16px; color: var(--text-muted); line-height: 1.8; margin-bottom: 48px; }
.feature-list { display: flex; flex-direction: column; gap: 14px; }
.feature-item {
    display: flex; align-items: center; gap: 14px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px; padding: 14px 18px;
    backdrop-filter: blur(4px);
}
.feature-icon {
    width: 38px; height: 38px; border-radius: 10px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center; font-size: 16px;
}
.feature-item .fi-text { font-size: 14px; color: var(--text-main); font-weight: 500; }
.feature-item .fi-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }

.login-right {
    width: 460px; flex-shrink: 0; position: relative;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    background: var(--bg-surface);
    border-left: 1px solid var(--border-color);
    padding: 60px 48px;
}
.login-form-area { width: 100%; max-width: 340px; }
.login-form-logo {
    width: 60px; height: 60px;
    border-radius: 14px;
    overflow: hidden;
    margin-bottom: 28px;
    box-shadow: 0 6px 20px rgba(91,159,255,0.3);
    border: 2px solid rgba(91,159,255,0.3);
}
.login-form-logo img { width: 100%; height: 100%; object-fit: cover; }
.login-form-title { font-size: 26px; font-weight: 800; color: #fff; margin-bottom: 8px; letter-spacing: -0.5px; }
.login-form-sub { font-size: 14px; color: var(--text-muted); margin-bottom: 32px; line-height: 1.6; }
.divider { border: none; border-top: 1px solid var(--border-color); margin: 24px 0; position: relative; }
.divider::after { content: 'OR'; position: absolute; top: -10px; left: 50%; transform: translateX(-50%); background: rgba(22,25,38,0.9); padding: 0 12px; font-size: 11px; color: var(--text-muted); font-weight: 700; letter-spacing: 1px; }
.btn-discord-big {
    background: linear-gradient(135deg, #5865F2, #4a56e0);
    width: 100%; font-size: 15px; padding: 15px;
    border-radius: 12px; display: flex; align-items: center; justify-content: center;
    gap: 10px; color: #fff; border: none; font-weight: 700; cursor: pointer;
    box-shadow: 0 6px 24px rgba(88,101,242,0.35);
    transition: all 0.25s; text-decoration: none; letter-spacing: 0.3px;
}
.btn-discord-big:hover {
    background: linear-gradient(135deg, #4752C4, #3a41b0);
    transform: translateY(-2px);
    box-shadow: 0 10px 32px rgba(88,101,242,0.5); color: #fff;
}
.login-notice {
    margin-top: 20px; padding: 14px 16px;
    background: rgba(255,255,255,0.03);
    border: 1px solid var(--border-color);
    border-radius: 10px; font-size: 12px;
    color: var(--text-muted); text-align: center; line-height: 1.6;
}
.pw-btn {
    width: 100%; padding: 16px; border-radius: 12px; border: none; cursor: pointer;
    background: linear-gradient(135deg, var(--primary), #4a8ef0);
    color: #fff; font-weight: 800; font-size: 16px;
    box-shadow: 0 6px 24px rgba(91,159,255,0.4);
    transition: all 0.25s; font-family: inherit;
    display: flex; align-items: center; justify-content: center; gap: 10px;
}
.pw-btn:hover { transform: translateY(-2px); box-shadow: 0 10px 32px rgba(91,159,255,0.55); }
.error-msg { background: rgba(255,94,122,0.1); border: 1px solid rgba(255,94,122,0.3); border-radius: 10px; padding: 12px 16px; font-size: 13px; color: var(--danger); text-align: center; margin-bottom: 16px; }
@media (max-width: 800px) {
    html, body { overflow: auto; }
    body { flex-direction: column; }
    .login-left { padding: 48px 28px 36px; flex: none; min-height: 50vh; }
    .login-right { width: 100%; border-left: none; border-top: 1px solid rgba(255,255,255,0.08); padding: 40px 28px 48px; }
    .feature-list { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
}
@media (max-width: 480px) {
    .login-left { padding: 36px 20px 28px; }
    .login-right { padding: 32px 20px 40px; }
    .feature-list { grid-template-columns: 1fr; }
    .login-title { font-size: 32px; }
}
</style>
</head>
<body>

<!-- 왼쪽: 비주얼 -->
<div class="login-left">
    <div class="login-left-content">
        <div class="big-logo"><img src="{{ logo_url }}" alt="FREEDOM"/></div>
        <div class="login-title"><span>FREEDOM</span></div>
        <p class="login-desc">상대방의 주사위 블랙리스트 이력을<br>즉시 확인하실 수 있습니다.</p>
        <div class="feature-list">
            <div class="feature-item">
                <div class="feature-icon" style="background:rgba(255,94,122,0.15);"><i class="fas fa-search" style="color:var(--danger);"></i></div>
                <div><div class="fi-text">즉시 조회</div><div class="fi-sub">고유번호 · 닉네임 검색</div></div>
            </div>
            <div class="feature-item">
                <div class="feature-icon" style="background:rgba(91,159,255,0.15);"><i class="fas fa-shield-alt" style="color:var(--primary);"></i></div>
                <div><div class="fi-text">안전 거래</div><div class="fi-sub">커뮤니티 보호 시스템</div></div>
            </div>
            <div class="feature-item">
                <div class="feature-icon" style="background:rgba(16,230,166,0.15);"><i class="fas fa-database" style="color:var(--success);"></i></div>
                <div><div class="fi-text">블랙리스트 DB</div><div class="fi-sub">검증된 블랙리스트</div></div>
            </div>
            <div class="feature-item">
                <div class="feature-icon" style="background:rgba(167,139,250,0.15);"><i class="fas fa-heart" style="color:var(--accent);"></i></div>
                <div><div class="fi-text">후원의 전당</div><div class="fi-sub">커뮤니티 서포터</div></div>
            </div>
        </div>
    </div>
</div>

<!-- 오른쪽: 로그인 폼 -->
<div class="login-right">
    <div class="login-form-area">
        <div class="login-form-logo"><img src="{{ logo_url }}" alt="FREEDOM"/></div>
        <div class="login-form-title">주사위 전<br>필수 확인</div>
        <div class="login-form-sub">입장코드를 입력하여<br>블랙리스트 조회 시스템에 접속하세요.</div>

        {% if error %}
        <div class="error-msg"><i class="fas fa-exclamation-circle"></i> {{ error }}</div>
        {% endif %}

        <form method="POST" action="{{ url_for('login') }}" style="display:flex; flex-direction:column; gap:12px;">
            <input type="password" name="password" class="input" placeholder="입장코드 입력" autocomplete="off" required
                style="text-align:center; letter-spacing:4px; font-size:15px;">
            <button class="pw-btn" type="submit">
                <i class="fas fa-unlock-alt"></i> 입장
            </button>
        </form>

        <div style="margin-top:16px;">
            <a href="https://discord.gg/9zMFBnvH77" target="_blank" style="
                display:flex; align-items:center; justify-content:center; gap:10px;
                width:100%; padding:13px; border-radius:12px;
                background:rgba(88,101,242,0.12);
                border:1px solid rgba(88,101,242,0.35);
                color:#7289DA; font-weight:700; font-size:14px;
                text-decoration:none; transition:all 0.2s;
            " onmouseover="this.style.background='rgba(88,101,242,0.22)';this.style.borderColor='rgba(88,101,242,0.6)'"
               onmouseout="this.style.background='rgba(88,101,242,0.12)';this.style.borderColor='rgba(88,101,242,0.35)'">
                <i class="fab fa-discord" style="font-size:18px;"></i>
                입장코드 받으러가기
            </a>
        </div>

        <hr class="divider">

        <a href="{{ auth_url }}" class="btn-discord-big">
            <i class="fab fa-discord" style="font-size:18px;"></i>
            관리자 로그인 (Discord)
        </a>
        <div class="login-notice">
            <i class="fas fa-lock" style="margin-right:5px; color:var(--text-muted);"></i>
            관리자는 Discord 로그인을 이용하세요.
        </div>
    </div>
</div>

</body></html>"""

# ==========================================
# 📱 APP TEMPLATE
# ==========================================
APP_TEMPLATE = """
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FREEDOM</title>
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet"/>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
""" + BASE_STYLE + """
<style>
.top-nav {
    background: rgba(22, 25, 38, 0.9);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border-color);
    position: sticky; top: 0; z-index: 100;
}
.nav-inner { max-width: 1100px; margin: 0 auto; padding: 0 20px; height: 64px; display: flex; align-items: center; justify-content: space-between; }
.brand { font-size: 20px; font-weight: 800; display: flex; align-items: center; gap: 10px; color: #fff; text-decoration: none; letter-spacing: -0.5px; }
.brand-icon { width: 32px; height: 32px; border-radius: 8px; overflow: hidden; border: 1px solid rgba(91,159,255,0.3); }
.brand-icon img { width: 100%; height: 100%; object-fit: cover; }
.nav-links { display: flex; gap: 2px; overflow-x: auto; scrollbar-width: none; }
.nav-links::-webkit-scrollbar { display: none; }
.nav-links a { color: var(--text-muted); padding: 8px 14px; border-radius: 8px; font-weight: 600; font-size: 14px; display: flex; align-items: center; gap: 6px; white-space: nowrap; transition: all 0.2s; }
.nav-links a:hover { color: #fff; background: rgba(255,255,255,0.07); }
.nav-links a.active { color: var(--primary); background: var(--primary-glow); }
.user-profile { display: flex; align-items: center; gap: 10px; }
.user-profile img { width: 34px; height: 34px; border-radius: 50%; border: 2px solid var(--border-color); transition: border-color 0.2s; }
.user-profile img:hover { border-color: var(--primary); }
@media(max-width: 800px) {
    .nav-inner { flex-direction: column; height: auto; padding: 12px 16px; gap: 10px; }
    .nav-links { width: 100%; justify-content: flex-start; }
    .nav-links a { padding: 7px 10px; font-size: 13px; }
}
@media(max-width: 480px) {
    .nav-links a span { display: none; }
}
</style>
<script>
function toKoreanUnit(n) {
    if (!n || isNaN(n)) return '';
    n = parseInt(n);
    if (n < 10000) return n.toLocaleString() + '원';
    let jo   = Math.floor(n / 1000000000000);
    let uk   = Math.floor((n % 1000000000000) / 100000000);
    let man  = Math.floor((n % 100000000) / 10000);
    let parts = [];
    if (jo)  parts.push(jo + '조');
    if (uk)  parts.push(uk + '억');
    if (man) parts.push(man + '만');
    return parts.join(' ') || n.toLocaleString() + '원';
}
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('클립보드에 복사되었습니다!', 'success');
    }).catch(() => {
        showToast('복사에 실패했습니다.', 'error');
    });
}
function showToast(msg, type) {
    const existing = document.getElementById('toastMsg');
    if (existing) existing.remove();
    const t = document.createElement('div');
    t.id = 'toastMsg';
    const bg = type === 'success' ? 'linear-gradient(135deg,#10e6a6,#0cba85)' : 'linear-gradient(135deg,#ff5e7a,#e04060)';
    t.style.cssText = `position:fixed;bottom:28px;left:50%;transform:translateX(-50%) translateY(20px);background:${bg};color:${type==='success'?'#0d0f17':'#fff'};padding:12px 24px;border-radius:30px;font-size:14px;font-weight:700;z-index:9999;opacity:0;transition:all 0.3s cubic-bezier(.34,1.4,.64,1);box-shadow:0 8px 24px rgba(0,0,0,0.4);white-space:nowrap;display:flex;align-items:center;gap:8px;`;
    t.innerHTML = `<i class="fas fa-${type==='success'?'check':'times'}"></i>${msg}`;
    document.body.appendChild(t);
    requestAnimationFrame(()=>{ requestAnimationFrame(()=>{ t.style.opacity='1'; t.style.transform='translateX(-50%) translateY(0)'; }); });
    setTimeout(()=>{ t.style.opacity='0'; t.style.transform='translateX(-50%) translateY(10px)'; setTimeout(()=>t.remove(),300); }, 2500);
}
// 금액 입력시 한글 미리보기
function updateAmountPreview(inputEl, previewId) {
    const val = inputEl.value.replace(/[^0-9]/g,'');
    const preview = document.getElementById(previewId);
    if (!preview) return;
    if (!val || parseInt(val) === 0) { preview.textContent = ''; return; }
    const n = parseInt(val);
    let jo   = Math.floor(n / 1000000000000);
    let uk   = Math.floor((n % 1000000000000) / 100000000);
    let man  = Math.floor((n % 100000000) / 10000);
    let chun = Math.floor((n % 10000) / 1000);
    let baek = Math.floor((n % 1000) / 100);
    let parts = [];
    if (jo)   parts.push(jo + '조');
    if (uk)   parts.push(uk + '억');
    if (man)  parts.push(man + '만');
    if (chun) parts.push(chun + '천');
    if (baek) parts.push(baek + '백');
    preview.textContent = '→ ' + n.toLocaleString() + '원 (' + (parts.join('') || n + '') + '원)';
}
</script>
</head>
<body>

{% if recent_scammers %}
<div class="marquee-container">
    <div class="marquee-label"><i class="fas fa-bolt"></i> 실시간 적발</div>
    <div class="marquee-track">
        <div class="marquee-inner">
            {% for s in recent_scammers %}<span class="marquee-item"><strong style="color:#fff;">{{ s.name }}</strong><span style="color:var(--primary);font-weight:700;margin-left:5px;">{{ s.unique_id }}번</span>{% if s.get('category') and '아이템' in s.get('category','') and s.get('item_name') and '돈' not in s.get('category','') %}<span style="color:#c4b5fd;font-weight:700;margin-left:8px;">{{ s.item_name }}</span>{% else %}<span style="color:var(--danger);font-weight:700;margin-left:8px;">{{ s.amount_display }}</span><span style="color:var(--text-muted);font-size:11px;margin-left:4px;">({{ korean_num(s.amount_int) }})</span>{% endif %}<span style="color:rgba(255,255,255,0.2);margin-left:16px;">|</span></span>{% endfor %}{% for s in recent_scammers %}<span class="marquee-item"><strong style="color:#fff;">{{ s.name }}</strong><span style="color:var(--primary);font-weight:700;margin-left:5px;">{{ s.unique_id }}번</span>{% if s.get('category') and '아이템' in s.get('category','') and s.get('item_name') and '돈' not in s.get('category','') %}<span style="color:#c4b5fd;font-weight:700;margin-left:8px;">{{ s.item_name }}</span>{% else %}<span style="color:var(--danger);font-weight:700;margin-left:8px;">{{ s.amount_display }}</span><span style="color:var(--text-muted);font-size:11px;margin-left:4px;">({{ korean_num(s.amount_int) }})</span>{% endif %}<span style="color:rgba(255,255,255,0.2);margin-left:16px;">|</span></span>{% endfor %}
        </div>
    </div>
</div>
{% endif %}

<header class="top-nav">
    <div class="nav-inner">
        <a href="{{ url_for('index') }}" class="brand">
            <div class="brand-icon"><img src="{{ logo_url }}" alt="F"/></div>
            FREEDOM
        </a>
        <nav class="nav-links">
            <a href="{{ url_for('index') }}" class="{% if page=='home' %}active{% endif %}">조회</a>
            <a href="{{ url_for('hall_of_fame') }}" class="{% if page=='hof' %}active{% endif %}">후원의 전당</a>
            {% if is_admin %}
            <a href="{{ url_for('admin_panel') }}" class="{% if page=='admin' %}active{% endif %}" style="color:var(--warning);">관리자</a>
            {% endif %}
        </nav>
        <div class="user-profile">
            <img src="{{ user.avatar_url }}"/>
            {% if is_admin %}
            <span style="font-size:11px; color:var(--warning); font-weight:700; background:rgba(255,202,94,0.1); padding:3px 8px; border-radius:6px; border:1px solid rgba(255,202,94,0.2);">ADMIN</span>
            {% endif %}
            <a href="{{ url_for('logout') }}" style="color:var(--text-muted); font-size:18px;" title="로그아웃"><i class="fas fa-sign-out-alt"></i></a>
        </div>
    </div>
</header>

<main class="container">

{% if is_real_admin is defined and is_real_admin and view_as_user is defined and view_as_user %}
<div style="position:fixed;top:50px;left:12px;z-index:9999;">
    <a href="{{ url_for('admin_view_as_admin') }}" style="display:inline-flex;align-items:center;gap:7px;padding:8px 14px;border-radius:10px;background:rgba(255,202,94,0.18);border:1.5px solid rgba(255,202,94,0.6);color:var(--warning);font-size:13px;font-weight:800;text-decoration:none;box-shadow:0 4px 16px rgba(255,202,94,0.25);backdrop-filter:blur(6px);transition:all 0.2s;" onmouseover="this.style.background='rgba(255,202,94,0.28)'" onmouseout="this.style.background='rgba(255,202,94,0.18)'">
        <i class="fas fa-user-shield"></i> 관리자로 돌아가기
    </a>
</div>
{% elif is_real_admin is defined and is_real_admin and (view_as_user is not defined or not view_as_user) and page != 'admin' %}
<div style="position:fixed;top:50px;left:12px;z-index:9999;">
    <a href="{{ url_for('admin_view_as_user') }}" style="display:inline-flex;align-items:center;gap:7px;padding:8px 14px;border-radius:10px;background:rgba(91,159,255,0.12);border:1.5px solid rgba(91,159,255,0.35);color:var(--primary);font-size:13px;font-weight:700;text-decoration:none;box-shadow:0 4px 14px rgba(91,159,255,0.15);backdrop-filter:blur(6px);transition:all 0.2s;" onmouseover="this.style.background='rgba(91,159,255,0.22)'" onmouseout="this.style.background='rgba(91,159,255,0.12)'">
        <i class="fas fa-eye"></i> 유저로 보기
    </a>
</div>
{% endif %}

{# ════════════════════ 홈 / 조회 ════════════════════ #}
{% if page=='home' %}

    <!-- 메인 레이아웃 -->
    <div class="home-grid" style="display:grid; grid-template-columns:1fr 280px; grid-template-rows:auto auto auto auto; gap:10px 20px; align-items:start; padding:20px 0 32px 0;">

        <!-- ① 타이틀 + 검색 (왼쪽 col1 row1) -->
        <div id="sec-search" class="drag-section" style="grid-column:1; grid-row:1; min-width:0;">
            <div style="margin-bottom:16px;">
                <h1 style="font-size:28px; margin-bottom:6px; line-height:1.2; letter-spacing:-0.5px;">
                    주사위 전 <span style="background:linear-gradient(135deg,var(--primary),var(--accent)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;">필수 확인</span>
                </h1>
                <p style="font-size:14px; color:var(--text-muted); margin-bottom:0; line-height:1.5;">상대방의 블랙리스트 이력을 즉시 확인하세요.</p>
            </div>
            <div style="margin-bottom:16px;">
                <div style="display:flex; gap:10px; align-items:stretch;">
                    <div style="position:relative; flex:1;">
                        <i class="fas fa-search" id="searchIcon" style="position:absolute;left:16px;top:50%;transform:translateY(-50%);color:var(--text-muted);font-size:15px;pointer-events:none;transition:color 0.2s;"></i>
                        <input id="searchInput" type="text" placeholder="고유번호 입력 (예: 33110)" autocomplete="off"
                            style="width:100%;padding:14px 14px 14px 46px;border-radius:12px;border:1.5px solid var(--border-color);background:var(--bg-elevated);color:#fff;font-size:15px;outline:none;transition:all 0.2s;font-family:inherit;"
                            onfocus="this.style.borderColor='var(--primary)';this.style.boxShadow='0 0 0 3px var(--primary-glow)';document.getElementById('searchIcon').style.color='var(--primary)';"
                            onblur="this.style.borderColor='var(--border-color)';this.style.boxShadow='none';document.getElementById('searchIcon').style.color='var(--text-muted)';"
                            onkeydown="if(event.key==='Enter') doSearch()"/>
                    </div>
                    <button onclick="doSearch()" id="searchBtn" style="padding:14px 28px;border-radius:12px;border:none;cursor:pointer;background:linear-gradient(135deg,var(--primary),#4a8ef0);color:#fff;font-weight:700;font-size:15px;box-shadow:0 4px 14px var(--primary-glow);transition:all 0.2s;white-space:nowrap;display:flex;align-items:center;gap:8px;font-family:inherit;" onmouseover="this.style.transform='translateY(-1px)'" onmouseout="this.style.transform=''">
                        <i class="fas fa-search"></i><span>검색</span>
                    </button>
                </div>
                <div style="margin-top:6px;">
                    <span style="font-size:12px;color:var(--text-muted);display:flex;align-items:center;gap:5px;">
                        <span style="display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--primary);"></span>고유번호(숫자)로만 검색 가능합니다
                    </span>
                </div>
                <div id="searchResultArea" style="display:none;margin-top:14px;"></div>
            </div>
        </div>

        <!-- ② 사이드바 row1 빈칸 (공간 맞춤) -->
        <div style="grid-column:2; grid-row:1;"></div>

        <!-- ③ 통계 3개 + 관리자 3명 한 줄 (col1 row2) -->
        <div id="sec-stats" class="drag-section" style="grid-column:1; grid-row:2; min-width:0; display:grid; grid-template-columns:repeat(3,1fr); gap:8px;">
            <!-- 통계 카드 3개 -->
            <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:12px;padding:12px 14px;display:flex;align-items:center;gap:10px;">
                <div style="width:34px;height:34px;border-radius:9px;background:rgba(255,94,122,0.15);display:flex;align-items:center;justify-content:center;flex-shrink:0;"><i class="fas fa-user-slash" style="color:var(--danger);font-size:13px;"></i></div>
                <div>
                    <div id="statTotal" style="font-size:18px;font-weight:800;color:var(--danger);line-height:1.1;">-</div>
                    <div style="font-size:10px;color:var(--text-muted);margin-top:2px;">총 블랙리스트</div>
                </div>
            </div>
            <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:12px;padding:12px 14px;display:flex;align-items:center;gap:10px;">
                <div style="width:34px;height:34px;border-radius:9px;background:rgba(255,202,94,0.15);display:flex;align-items:center;justify-content:center;flex-shrink:0;"><i class="fas fa-clock" style="color:var(--warning);font-size:13px;"></i></div>
                <div>
                    <div id="statRecent" style="font-size:18px;font-weight:800;color:var(--warning);line-height:1.1;">-</div>
                    <div style="font-size:10px;color:var(--text-muted);margin-top:2px;">최근 24시간</div>
                </div>
            </div>
            <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:12px;padding:12px 14px;display:flex;align-items:center;gap:10px;">
                <div style="width:34px;height:34px;border-radius:9px;background:rgba(16,230,166,0.15);display:flex;align-items:center;justify-content:center;flex-shrink:0;"><i class="fas fa-won-sign" style="color:var(--success);font-size:13px;"></i></div>
                <div style="min-width:0;">
                    <div id="statAmount" style="font-size:13px;font-weight:800;color:var(--success);line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">-</div>
                    <div id="statAmountKorean" style="display:none;"></div>
                    <div style="font-size:10px;color:var(--text-muted);margin-top:2px;">누적 피해</div>
                </div>
            </div>
        </div>

        <!-- ④ 사이드바 row2: 관리자 목록 -->
        <div style="grid-column:2; grid-row:2; display:flex; flex-direction:column; gap:6px;">
            <div style="background:var(--bg-elevated);border:1px solid rgba(255,215,0,0.25);border-radius:12px;padding:9px 12px;display:flex;align-items:center;gap:10px;">
                <span style="font-size:16px;">📦</span>
                <div style="flex:1;min-width:0;">
                    <div style="font-size:12px;font-weight:800;color:#fff;">무장</div>
                    <div style="font-size:10px;font-weight:700;color:#FFD700;margin-top:1px;">👑 서버 총 관리자</div>
                </div>
                <div style="font-size:11px;font-weight:800;color:#FFD700;background:rgba(255,215,0,0.15);border:1px solid rgba(255,215,0,0.4);border-radius:4px;padding:1px 7px;flex-shrink:0;">100번</div>
            </div>
            <div style="background:var(--bg-elevated);border:1px solid rgba(255,110,180,0.25);border-radius:12px;padding:9px 12px;display:flex;align-items:center;gap:10px;">
                <span style="font-size:16px;">💗</span>
                <div style="flex:1;min-width:0;">
                    <div style="font-size:12px;font-weight:800;color:#fff;">담늘잉</div>
                    <div style="font-size:10px;font-weight:700;color:#ff6eb4;margin-top:1px;">💗 서버 매니저</div>
                </div>
                <div style="font-size:11px;font-weight:800;color:#ff6eb4;background:rgba(255,110,180,0.15);border:1px solid rgba(255,110,180,0.4);border-radius:4px;padding:1px 7px;flex-shrink:0;">2662번</div>
            </div>
            <div style="background:var(--bg-elevated);border:1px solid rgba(16,230,166,0.2);border-radius:12px;padding:9px 12px;display:flex;align-items:center;gap:10px;">
                <span style="font-size:16px;">💊</span>
                <div style="flex:1;min-width:0;">
                    <div style="font-size:12px;font-weight:800;color:#fff;">진짜</div>
                    <div style="font-size:10px;font-weight:700;color:#10e6a6;margin-top:1px;">💻 서버 개발자</div>
                </div>
                <div style="font-size:11px;font-weight:800;color:#10e6a6;background:rgba(16,230,166,0.15);border:1px solid rgba(16,230,166,0.4);border-radius:4px;padding:1px 7px;flex-shrink:0;">33110번</div>
            </div>
        </div>

        <!-- ⑤ 최근 적발 위 5개 (col1 row3) -->
        {% if recent_scammers %}
        <div id="sec-recent" class="drag-section" style="grid-column:1; grid-row:3; min-width:0;">
            <div style="display:flex;align-items:center;gap:7px;margin-bottom:8px;">
                <div style="width:6px;height:6px;border-radius:50%;background:var(--danger);box-shadow:0 0 6px var(--danger);animation:pulse 1.5s infinite;"></div>
                <span style="font-size:12px;font-weight:700;color:var(--danger);">최근 적발</span>
            </div>
            <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:7px;height:100%;">
                {% for s in recent_scammers[:5] %}
                {% set item_only = s.get('category') and '아이템' in s.get('category','') and s.get('item_name') and '돈' not in s.get('category','') %}
                <div style="background:var(--bg-surface);border:1px solid rgba(255,94,122,0.2);border-radius:10px;padding:11px 10px;display:flex;flex-direction:column;gap:4px;min-width:0;">
                    <div style="font-size:13px;font-weight:800;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ s.name }}</div>
                    <div style="font-size:11px;font-weight:700;color:var(--primary);background:rgba(91,159,255,0.1);padding:1px 6px;border-radius:4px;display:inline-block;width:fit-content;">{{ s.unique_id }}번</div>
                    {% if item_only %}
                    <div style="font-size:11px;font-weight:700;color:#c4b5fd;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ s.item_name }}</div>
                    {% else %}
                    <div style="font-size:12px;font-weight:700;color:var(--danger);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ s.amount_display }}</div>
                    <div style="font-size:10px;color:var(--text-muted);">({{ korean_num(s.amount_int) }})</div>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
        </div>
        {% else %}
        <div style="grid-column:1; grid-row:3;"></div>
        {% endif %}

        <!-- ⑥ 공지사항 (col2 row3) -->
        <div id="sec-admins" class="drag-section" style="grid-column:2; grid-row:3;">
            <!-- 공지사항 팝업 모달 -->
            <div id="noticePopupModal" style="display:none;position:fixed;inset:0;z-index:9998;background:rgba(5,7,15,0.82);backdrop-filter:blur(7px);align-items:center;justify-content:center;padding:20px;">
                <div id="noticePopupBox" style="width:100%;max-width:520px;background:var(--bg-surface);border-radius:20px;border:1px solid var(--border-color);box-shadow:0 24px 80px rgba(0,0,0,0.7);overflow:hidden;transform:scale(0.92) translateY(20px);opacity:0;transition:transform 0.28s cubic-bezier(.34,1.4,.64,1),opacity 0.22s ease;">
                    <div id="noticePopupHeader" style="padding:20px 24px 16px;border-bottom:1px solid var(--border-color);display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
                        <div style="flex:1;min-width:0;">
                            <div id="noticePopupBadge" style="display:inline-flex;align-items:center;gap:5px;border-radius:20px;padding:4px 12px;font-size:11px;font-weight:700;margin-bottom:10px;"></div>
                            <div id="noticePopupTitle" style="font-size:18px;font-weight:800;color:#fff;line-height:1.3;"></div>
                            <div id="noticePopupDate" style="font-size:11px;color:var(--text-muted);margin-top:5px;"></div>
                        </div>
                        <button onclick="closeNoticePopup()" style="background:rgba(255,255,255,0.07);border:none;cursor:pointer;width:34px;height:34px;border-radius:50%;color:var(--text-muted);font-size:16px;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.14)';this.style.color='#fff'" onmouseout="this.style.background='rgba(255,255,255,0.07)';this.style.color='var(--text-muted)'"><i class="fas fa-times"></i></button>
                    </div>
                    <div id="noticePopupContent" style="padding:20px 24px 24px;font-size:14px;color:var(--text-main);line-height:1.8;white-space:pre-wrap;max-height:60vh;overflow-y:auto;"></div>
                </div>
            </div>
            <script>
            function openNoticePopupFromEl(el) {
                var title   = el.getAttribute('data-n-title');
                var content = el.getAttribute('data-n-content');
                var date    = el.getAttribute('data-n-date');
                var type    = el.getAttribute('data-n-type');
                var isNotice = (type === '공지');
                var badge = document.getElementById('noticePopupBadge');
                badge.innerHTML = isNotice ? '📢 공지사항' : '🔧 패치노트';
                badge.style.background = isNotice ? 'rgba(167,139,250,0.15)' : 'rgba(16,230,166,0.15)';
                badge.style.color = isNotice ? 'var(--accent)' : 'var(--success)';
                badge.style.border = isNotice ? '1px solid rgba(167,139,250,0.3)' : '1px solid rgba(16,230,166,0.3)';
                document.getElementById('noticePopupTitle').textContent = title;
                document.getElementById('noticePopupDate').textContent = date;
                document.getElementById('noticePopupContent').textContent = content;
                document.getElementById('noticePopupHeader').style.borderBottomColor = isNotice ? 'rgba(167,139,250,0.25)' : 'rgba(16,230,166,0.25)';
                var box = document.getElementById('noticePopupBox');
                box.style.borderColor = isNotice ? 'rgba(167,139,250,0.35)' : 'rgba(16,230,166,0.35)';
                box.style.transform = 'scale(0.92) translateY(20px)'; box.style.opacity = '0';
                var modal = document.getElementById('noticePopupModal');
                modal.style.display = 'flex';
                requestAnimationFrame(function(){ requestAnimationFrame(function(){
                    box.style.transform = 'scale(1) translateY(0)'; box.style.opacity = '1';
                }); });
            }
            function closeNoticePopup() {
                var box = document.getElementById('noticePopupBox');
                box.style.transform = 'scale(0.94) translateY(16px)'; box.style.opacity = '0';
                setTimeout(function(){ document.getElementById('noticePopupModal').style.display = 'none'; }, 220);
            }
            (function(){ var nm = document.getElementById('noticePopupModal'); if(nm) nm.addEventListener('click', function(e){ if(e.target===this) closeNoticePopup(); }); })();
            </script>
            <div style="background:var(--bg-surface); border:1px solid var(--border-color); border-radius:12px; padding:12px; height:100%; box-sizing:border-box;">
                <div style="display:flex; align-items:center; gap:6px; margin-bottom:8px; padding-bottom:8px; border-bottom:1px solid rgba(167,139,250,0.2);">
                    <div style="width:22px;height:22px;border-radius:6px;background:rgba(167,139,250,0.15);display:flex;align-items:center;justify-content:center;font-size:11px;">📢</div>
                    <span style="font-size:12px; font-weight:800; color:#fff;">공지사항</span>
                </div>
                <div style="display:flex; flex-direction:column; gap:5px;">
                    {% for n in notices_list if n.notice_type == '공지' %}
                    <div onclick="openNoticePopupFromEl(this)"
                         data-n-title="{{ n.title|e }}"
                         data-n-content="{{ n.content|e }}"
                         data-n-date="{{ n.created_at[:10] }}"
                         data-n-type="공지"
                         style="background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:8px;overflow:hidden;cursor:pointer;transition:border-color 0.2s;" onmouseover="this.style.borderColor='rgba(167,139,250,0.5)'" onmouseout="this.style.borderColor='var(--border-color)'">
                        <div style="padding:7px 10px;display:flex;justify-content:space-between;align-items:center;gap:6px;">
                            <div style="display:flex;align-items:center;gap:4px;min-width:0;">
                                <div style="width:4px;height:4px;border-radius:50%;background:var(--accent);flex-shrink:0;"></div>
                                <span style="font-size:12px;font-weight:700;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ n.title }}</span>
                            </div>
                            <div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">
                                <span style="font-size:10px;color:var(--text-muted);white-space:nowrap;">{{ n.created_at[:10] }}</span>
                                <span style="font-size:10px;color:var(--accent);font-weight:700;">자세히 →</span>
                            </div>
                        </div>
                        <div style="padding:0 10px 7px;font-size:11px;color:var(--text-muted);line-height:1.5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ n.content }}</div>
                    </div>
                    {% else %}
                    <div style="text-align:center;padding:12px 10px;color:var(--text-muted);font-size:11px;">
                        <div style="font-size:18px;margin-bottom:4px;">📢</div>등록된 공지가 없습니다.
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>

        <!-- ⑦ 최근 적발 아래 5개 (col1 row4) -->
        {% if recent_scammers|length > 5 %}
        <div id="sec-recent2" class="drag-section" style="grid-column:1; grid-row:4; min-width:0;">
            <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:7px;">
                {% for s in recent_scammers[5:] %}
                {% set item_only = s.get('category') and '아이템' in s.get('category','') and s.get('item_name') and '돈' not in s.get('category','') %}
                <div style="background:var(--bg-surface);border:1px solid rgba(255,94,122,0.2);border-radius:10px;padding:11px 10px;display:flex;flex-direction:column;gap:4px;min-width:0;">
                    <div style="font-size:13px;font-weight:800;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ s.name }}</div>
                    <div style="font-size:11px;font-weight:700;color:var(--primary);background:rgba(91,159,255,0.1);padding:1px 6px;border-radius:4px;display:inline-block;width:fit-content;">{{ s.unique_id }}번</div>
                    {% if item_only %}
                    <div style="font-size:11px;font-weight:700;color:#c4b5fd;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ s.item_name }}</div>
                    {% else %}
                    <div style="font-size:12px;font-weight:700;color:var(--danger);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ s.amount_display }}</div>
                    <div style="font-size:10px;color:var(--text-muted);">({{ korean_num(s.amount_int) }})</div>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
        </div>
        {% else %}
        <div style="grid-column:1; grid-row:4;"></div>
        {% endif %}
        <style>@keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:0.4;} }</style>

        <!-- ⑧ 패치노트 (col2 row4) -->
        <div id="sec-patches" class="drag-section" style="grid-column:2; grid-row:4;">
            <div style="background:var(--bg-surface); border:1px solid var(--border-color); border-radius:12px; padding:12px;">
                <div style="display:flex; align-items:center; gap:6px; margin-bottom:8px; padding-bottom:8px; border-bottom:1px solid rgba(16,230,166,0.2);">
                    <div style="width:22px;height:22px;border-radius:6px;background:rgba(16,230,166,0.15);display:flex;align-items:center;justify-content:center;font-size:11px;">🔧</div>
                    <span style="font-size:12px; font-weight:800; color:#fff;">패치노트</span>
                </div>
                <div style="display:flex; flex-direction:column; gap:5px;">
                    {% for n in notices_list if n.notice_type == '패치노트' %}
                    <div onclick="openNoticePopupFromEl(this)"
                         data-n-title="{{ n.title|e }}"
                         data-n-content="{{ n.content|e }}"
                         data-n-date="{{ n.created_at[:10] }}"
                         data-n-type="패치노트"
                         style="background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:8px;overflow:hidden;cursor:pointer;transition:border-color 0.2s;" onmouseover="this.style.borderColor='rgba(16,230,166,0.5)'" onmouseout="this.style.borderColor='var(--border-color)'">
                        <div style="padding:7px 10px;display:flex;justify-content:space-between;align-items:center;gap:6px;">
                            <div style="display:flex;align-items:center;gap:4px;min-width:0;">
                                <div style="width:4px;height:4px;border-radius:50%;background:var(--success);flex-shrink:0;"></div>
                                <span style="font-size:12px;font-weight:700;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ n.title }}</span>
                            </div>
                            <div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">
                                <span style="font-size:10px;color:var(--text-muted);white-space:nowrap;">{{ n.created_at[:10] }}</span>
                                <span style="font-size:10px;color:var(--success);font-weight:700;">자세히 →</span>
                            </div>
                        </div>
                        <div style="padding:0 10px 7px;font-size:11px;color:var(--text-muted);line-height:1.5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ n.content }}</div>
                    </div>
                    {% else %}
                    <div style="text-align:center;padding:12px 10px;color:var(--text-muted);font-size:11px;">
                        <div style="font-size:18px;margin-bottom:4px;">🔧</div>등록된 패치노트가 없습니다.
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>

    </div>{# end grid #}

    {% if is_admin %}
    <!-- ══════ 관리자 위치 조정 시스템 ══════ -->
    <style>
    #adminLayoutBtn {
        position: fixed; bottom: 28px; right: 28px; z-index: 9990;
        background: linear-gradient(135deg, #ffd166, #e6b800);
        color: #0d0f17; border: none; border-radius: 50px;
        padding: 10px 18px; font-size: 13px; font-weight: 800;
        cursor: pointer; box-shadow: 0 4px 20px rgba(255,209,102,0.45);
        display: flex; align-items: center; gap: 7px;
        transition: all 0.2s; font-family: inherit;
    }
    #adminLayoutBtn:hover { transform: translateY(-2px); box-shadow: 0 6px 28px rgba(255,209,102,0.6); }
    #adminLayoutBtn.active { background: linear-gradient(135deg,#ff6b8a,#e04060); color:#fff; box-shadow:0 4px 20px rgba(255,107,138,0.5); }

    .drag-section {
        position: relative; transition: box-shadow 0.2s;
    }
    .drag-section.edit-mode {
        outline: 2px dashed rgba(255,209,102,0.6);
        border-radius: 14px;
    }
    .drag-section.dragging {
        outline: 2px solid #ffd166;
        box-shadow: 0 12px 40px rgba(255,209,102,0.35) !important;
        opacity: 0.92; z-index: 9800;
    }
    .drag-handle {
        display: none; position: absolute; top: -14px; left: 50%;
        transform: translateX(-50%);
        background: linear-gradient(135deg,#ffd166,#e6b800);
        color: #0d0f17; font-size: 11px; font-weight: 800;
        padding: 3px 12px; border-radius: 20px; cursor: grab;
        white-space: nowrap; z-index: 9801;
        box-shadow: 0 2px 10px rgba(255,209,102,0.4);
        user-select: none;
    }
    .drag-handle:active { cursor: grabbing; }
    .drag-coords {
        display: none; position: absolute; top: -14px; right: 8px;
        background: rgba(13,15,23,0.92); color: #ffd166;
        font-size: 10px; font-weight: 700; padding: 3px 8px;
        border-radius: 6px; border: 1px solid rgba(255,209,102,0.3);
        font-family: monospace; z-index: 9802; white-space: nowrap;
    }
    .edit-mode .drag-handle,
    .edit-mode .drag-coords { display: block; }

    #coordToast {
        position: fixed; bottom: 80px; right: 28px; z-index: 9995;
        background: rgba(13,15,23,0.95); border: 1px solid rgba(255,209,102,0.4);
        color: #ffd166; font-size: 12px; font-weight: 700;
        padding: 10px 16px; border-radius: 10px; font-family: monospace;
        display: none; line-height: 1.7;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    }
    #layoutSaveBtn {
        position: fixed; bottom: 28px; right: 200px; z-index: 9990;
        background: linear-gradient(135deg,#22f0b5,#0cba85);
        color: #0d0f17; border: none; border-radius: 50px;
        padding: 10px 18px; font-size: 13px; font-weight: 800;
        cursor: pointer; box-shadow: 0 4px 20px rgba(34,240,181,0.4);
        display: none; align-items: center; gap: 7px;
        transition: all 0.2s; font-family: inherit;
    }
    #layoutSaveBtn:hover { transform: translateY(-2px); }
    #layoutResetBtn {
        position: fixed; bottom: 28px; right: 340px; z-index: 9990;
        background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15);
        color: #fff; border-radius: 50px;
        padding: 10px 18px; font-size: 13px; font-weight: 800;
        cursor: pointer; display: none; align-items: center; gap: 7px;
        transition: all 0.2s; font-family: inherit;
    }
    #layoutResetBtn:hover { background: rgba(255,255,255,0.14); }
    </style>

    <!-- 위치 조정 버튼 -->
    <button id="adminLayoutBtn" onclick="toggleLayoutEdit()">
        <i class="fas fa-arrows-alt"></i> 위치 조정
    </button>
    <button id="layoutSaveBtn" onclick="saveLayout()">
        <i class="fas fa-save"></i> 저장
    </button>
    <button id="layoutResetBtn" onclick="resetLayout()">
        <i class="fas fa-undo"></i> 초기화
    </button>
    <div id="coordToast"></div>

    <script>
    // 드래그 가능한 섹션 정의
    const SECTIONS = [
        { id: 'sec-search',   label: '🔍 검색' },
        { id: 'sec-stats',    label: '📊 통계' },
        { id: 'sec-recent',   label: '🚨 최근 적발 (1~5)' },
        { id: 'sec-recent2',  label: '🚨 최근 적발 (6~10)' },
        { id: 'sec-admins',   label: '📢 공지사항' },
        { id: 'sec-patches',  label: '🔧 패치노트' },
    ];

    let editMode = false;
    let dragging = null, startX = 0, startY = 0, origX = 0, origY = 0;

    function toggleLayoutEdit() {
        editMode = !editMode;
        const btn = document.getElementById('adminLayoutBtn');
        const saveBtn = document.getElementById('layoutSaveBtn');
        const resetBtn = document.getElementById('layoutResetBtn');

        if (editMode) {
            btn.classList.add('active');
            btn.innerHTML = '<i class="fas fa-times"></i> 편집 종료';
            saveBtn.style.display = 'flex';
            resetBtn.style.display = 'flex';
            SECTIONS.forEach(s => {
                const el = document.getElementById(s.id);
                if (!el) return;
                el.classList.add('edit-mode');
                el.style.position = el.style.position || 'relative';
            });
        } else {
            btn.classList.remove('active');
            btn.innerHTML = '<i class="fas fa-arrows-alt"></i> 위치 조정';
            saveBtn.style.display = 'none';
            resetBtn.style.display = 'none';
            document.getElementById('coordToast').style.display = 'none';
            SECTIONS.forEach(s => {
                const el = document.getElementById(s.id);
                if (!el) return;
                el.classList.remove('edit-mode');
            });
        }
    }

    function updateCoords(el, id) {
        const rect = el.getBoundingClientRect();
        const parentRect = el.offsetParent ? el.offsetParent.getBoundingClientRect() : {top:0,left:0};
        const x = Math.round(el.offsetLeft);
        const y = Math.round(el.offsetTop);
        const coordEl = el.querySelector('.drag-coords');
        if (coordEl) coordEl.textContent = `x:${x} y:${y}`;

        const toast = document.getElementById('coordToast');
        const sec = SECTIONS.find(s => s.id === id);
        toast.style.display = 'block';
        toast.innerHTML = `<div style="color:#fff;margin-bottom:4px;font-family:'Pretendard',sans-serif;">${sec ? sec.label : id}</div>` +
            `X: ${x}px &nbsp; Y: ${y}px<br>` +
            `W: ${Math.round(el.offsetWidth)}px &nbsp; H: ${Math.round(el.offsetHeight)}px`;
    }

    function initDrag(el, id) {
        const handle = el.querySelector('.drag-handle');
        if (!handle) return;

        handle.addEventListener('mousedown', function(e) {
            if (!editMode) return;
            e.preventDefault();
            dragging = el;
            dragging.classList.add('dragging');
            // make absolute if not already
            if (el.style.position !== 'absolute') {
                const x = el.offsetLeft;
                const y = el.offsetTop;
                el.style.position = 'absolute';
                el.style.left = x + 'px';
                el.style.top = y + 'px';
                el.style.width = el.offsetWidth + 'px';
                el.style.zIndex = 9800;
            }
            startX = e.clientX - el.offsetLeft;
            startY = e.clientY - el.offsetTop;
            updateCoords(el, id);
        });
    }

    document.addEventListener('mousemove', function(e) {
        if (!dragging) return;
        const newX = e.clientX - startX;
        const newY = e.clientY - startY;
        dragging.style.left = newX + 'px';
        dragging.style.top = newY + 'px';
        const id = dragging.id;
        updateCoords(dragging, id);
    });

    document.addEventListener('mouseup', function() {
        if (!dragging) return;
        dragging.classList.remove('dragging');
        dragging = null;
    });

    function saveLayout() {
        const layout = {};
        SECTIONS.forEach(s => {
            const el = document.getElementById(s.id);
            if (!el) return;
            layout[s.id] = {
                left: el.style.left || '',
                top: el.style.top || '',
                position: el.style.position || '',
                width: el.style.width || ''
            };
        });
        localStorage.setItem('freedom_layout', JSON.stringify(layout));
        showToast('레이아웃이 저장되었습니다!', 'success');
    }

    function resetLayout() {
        localStorage.removeItem('freedom_layout');
        SECTIONS.forEach(s => {
            const el = document.getElementById(s.id);
            if (!el) return;
            el.style.left = '';
            el.style.top = '';
            el.style.position = '';
            el.style.width = '';
            el.style.zIndex = '';
            const coordEl = el.querySelector('.drag-coords');
            if (coordEl) coordEl.textContent = '';
        });
        showToast('초기화 완료!', 'success');
    }

    function loadLayout() {
        const saved = localStorage.getItem('freedom_layout');
        if (!saved) return;
        try {
            const layout = JSON.parse(saved);
            SECTIONS.forEach(s => {
                const el = document.getElementById(s.id);
                if (!el || !layout[s.id]) return;
                const d = layout[s.id];
                if (d.position) el.style.position = d.position;
                if (d.left) el.style.left = d.left;
                if (d.top) el.style.top = d.top;
                if (d.width) el.style.width = d.width;
            });
        } catch(e) {}
    }

    // 섹션에 핸들/좌표 DOM 주입 + 드래그 초기화
    document.addEventListener('DOMContentLoaded', function() {
        SECTIONS.forEach(s => {
            const el = document.getElementById(s.id);
            if (!el) return;
            // 핸들
            const handle = document.createElement('div');
            handle.className = 'drag-handle';
            handle.innerHTML = '<i class="fas fa-grip-horizontal" style="margin-right:5px;"></i>' + s.label;
            el.insertBefore(handle, el.firstChild);
            // 좌표
            const coords = document.createElement('div');
            coords.className = 'drag-coords';
            coords.textContent = 'x:0 y:0';
            el.insertBefore(coords, el.firstChild);
            // 드래그
            initDrag(el, s.id);
        });
        loadLayout();
    });
    </script>
    <!-- ══════ end 관리자 위치 조정 ══════ -->
    {% endif %}

    <script>
    fetch('/api/stats').then(r=>r.json()).then(data=>{
        if(data.success){
            document.getElementById('statTotal').textContent = data.stats.total_cases.toLocaleString() + '명';
            document.getElementById('statRecent').textContent = data.stats.recent_24 + '건';
            document.getElementById('statAmount').textContent = data.stats.total_amount_korean;
            document.getElementById('statAmountKorean').textContent = '(' + data.stats.total_amount + ')';
        }
    }).catch(()=>{});

    function doSearch() {
        const input = document.getElementById('searchInput');
        const q = input.value.trim();
        if (!q) { input.focus(); input.style.borderColor='var(--danger)'; setTimeout(()=>input.style.borderColor='var(--border-color)',1200); return; }
        if (!/^\\d+$/.test(q)) {
            showToast('고유번호(숫자)로만 검색 가능합니다.', 'error');
            input.style.borderColor='var(--danger)';
            setTimeout(()=>input.style.borderColor='var(--border-color)',1200);
            return;
        }
        const btn = document.getElementById('searchBtn');
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>검색 중</span>';
        btn.disabled = true;
        fetch('/api/search?q=' + encodeURIComponent(q))
        .then(r => r.json())
        .then(data => {
            btn.innerHTML = '<i class="fas fa-search"></i><span>검색</span>';
            btn.disabled = false;
            showInlineResults(q, data.results || []);
        })
        .catch(() => {
            btn.innerHTML = '<i class="fas fa-search"></i><span>검색</span>';
            btn.disabled = false;
            showToast('검색 중 오류가 발생했습니다.', 'error');
        });
    }

    function showInlineResults(query, results) {
        const area = document.getElementById('searchResultArea');
        area.style.display = 'block';

        // VIP 처리
        const VIP = {
            '100':   { name:'무장', role:'서버 총 관리자', badge:'👑', color:'#FFD700', bg:'rgba(255,215,0,0.08)', border:'rgba(255,215,0,0.35)', glow:'rgba(255,215,0,0.15)', desc:'FREEDOM 서버를 이끄는 절대군주' },
            '2662':  { name:'담늘잉', role:'서버 매니저', badge:'💗', color:'#ff6eb4', bg:'rgba(255,110,180,0.10)', border:'rgba(255,110,180,0.40)', glow:'rgba(255,110,180,0.18)', desc:'서버 매니저로 커뮤니티를 지키는 핵심 관리자' },
            '33110': { name:'진짜', role:'서버 개발자', badge:'💻', color:'#10e6a6', bg:'rgba(16,230,166,0.08)', border:'rgba(16,230,166,0.35)', glow:'rgba(16,230,166,0.12)', desc:'FREEDOM 시스템을 설계하고 구축한 개발자' }
        };
        const trimQ = query.trim();
        if (VIP[trimQ]) {
            const v = VIP[trimQ];
            area.innerHTML = `<div style="position:relative;background:${v.bg};border:2px solid ${v.border};border-radius:16px;padding:24px;text-align:center;box-shadow:0 0 40px ${v.glow},0 0 80px ${v.glow};animation:vipGlow 2s ease-in-out infinite alternate;">
                <div style="font-size:52px;margin-bottom:12px;">${v.badge}</div>
                <div style="font-size:22px;font-weight:900;color:${v.color};margin-bottom:6px;">${v.name}</div>
                <div style="font-size:13px;font-weight:700;color:${v.color};opacity:0.85;margin-bottom:8px;">${v.role}</div>
                <div style="font-size:13px;color:var(--text-muted);">${v.desc}</div>
                <div style="margin-top:14px;display:inline-flex;align-items:center;gap:6px;background:${v.bg};border:1px solid ${v.border};border-radius:12px;padding:6px 16px;font-size:12px;font-weight:700;color:${v.color};">
                    <i class="fas fa-shield-alt"></i> FREEDOM 공식 멤버
                </div>
            </div>
            <style>@keyframes vipGlow { 0%{box-shadow:0 0 20px ${v.glow},0 0 40px ${v.glow};border-color:${v.border};} 100%{box-shadow:0 0 40px ${v.color},0 0 80px ${v.glow},0 0 120px ${v.glow};border-color:${v.color};} }</style>`;
            area.scrollIntoView({behavior:'smooth', block:'nearest'});
            return;
        }

        if (results.length > 0) {
            const r0 = results[0];
            const totalCases = results.length;

// ── 최상단 경고 배너 (2개) ──
            let html = `
            <div style="background:linear-gradient(135deg,rgba(255,94,122,0.28),rgba(255,94,122,0.14));border:2px solid rgba(255,94,122,0.7);border-radius:16px;padding:20px 24px;margin-bottom:10px;text-align:center;box-shadow:0 0 30px rgba(255,94,122,0.25);">
              <div style="font-size:26px;font-weight:900;color:var(--danger);letter-spacing:3px;margin-bottom:7px;">⚠️ 블랙리스트 ⚠️</div>
              <div style="font-size:15px;font-weight:700;color:rgba(255,94,122,0.9);margin-bottom:8px;">🚫 블랙리스트에 등록된 유저는 제보를 받지않습니다 🚫</div>
              <div style="display:inline-flex;align-items:center;gap:8px;background:rgba(0,0,0,0.2);border:1px solid rgba(255,215,0,0.4);border-radius:20px;padding:5px 16px;">
                <span style="font-size:14px;font-weight:900;color:#fff;">${trimQ}번</span>
                <span style="font-size:13px;color:rgba(255,255,255,0.7);">|</span>
                <span style="font-size:14px;font-weight:900;color:#FFD700;text-shadow: 0 0 8px rgba(255,215,0,0.5);">총 ${totalCases}건 적발</span>
              </div>
            </div>
            <div style="background:rgba(255,94,122,0.1);border:1.5px dashed rgba(255,94,122,0.5);border-radius:12px;padding:10px 16px;margin-bottom:12px;text-align:center;">
              <span style="font-size:13px;font-weight:700;color:var(--danger);">⛔ 주의 — 이 유저와의 거래를 중단하세요 ⛔</span>
            </div>`;

            // ── 각 사건 카드 (사건번호 #n 형식) ──
            results.forEach((r, idx) => {
                const hasItem = r.category && r.category.includes('아이템');
                const hasMoney = r.category && r.category.includes('돈');
                const itemOnly = hasItem && r.item_name && !hasMoney;
                const korAmt = r.amount_korean || '';

                html += `
                <div style="background:var(--bg-elevated);border:1.5px solid rgba(255,94,122,0.3);border-radius:16px;overflow:hidden;margin-bottom:12px;box-shadow:0 4px 20px rgba(255,94,122,0.1);">
                  <div style="padding:14px 20px;background:rgba(255,94,122,0.08);border-bottom:1px solid rgba(255,94,122,0.15);display:flex;align-items:center;justify-content:space-between;">
                    <div style="font-size:16px;font-weight:900;color:var(--primary);">사건번호 #${r.unique_id}</div>
                    <div style="display:flex;align-items:center;gap:8px;">
                      ${r.category ? `<span style="font-size:12px;color:#c4b5fd;background:rgba(167,139,250,0.14);padding:3px 10px;border-radius:6px;border:1px solid rgba(167,139,250,0.25);font-weight:700;">${r.category}</span>` : ''}
                      ${totalCases > 1 ? `<span style="font-size:12px;font-weight:800;color:#FFD700;background:rgba(0,0,0,0.3);border:1px solid rgba(255,215,0,0.5);padding:3px 10px;border-radius:20px;text-shadow: 0 0 5px rgba(255,215,0,0.3);">총 ${totalCases}건 적발</span>` : ''}
                    </div>
                  </div>
                  <div style="padding:18px 20px;display:flex;flex-direction:column;gap:12px;">
                    <!-- 날짜 -->
                    <div style="font-size:13px;color:var(--text-muted);display:flex;align-items:center;gap:7px;">
                      <i class="fas fa-calendar-alt" style="font-size:12px;"></i>
                      <span>날짜:</span>
                      <strong style="color:#fff;">${r.date ? r.date.slice(0,10) : '정보 없음'}</strong>
                    </div>
                    <!-- 가해자/피해자 정보 그리드 -->
                    <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;background:rgba(255,94,122,0.08);border:1.5px solid rgba(255,94,122,0.3);border-radius:12px;padding:14px 16px;">
                      <div>
                        <div style="font-size:11px;color:rgba(255,94,122,0.8);font-weight:700;margin-bottom:5px;display:flex;align-items:center;gap:4px;"><span>⚠️</span> 가해자 번호</div>
                        <div style="font-size:20px;font-weight:900;color:#A8D932;letter-spacing:1px;">${r.unique_id}</div>
                      </div>
                      <div>
                        <div style="font-size:11px;color:rgba(255,94,122,0.8);font-weight:700;margin-bottom:5px;display:flex;align-items:center;gap:4px;"><span>⚠️</span> 가해자 닉네임</div>
                        <div style="font-size:18px;font-weight:900;color:#A8D932;">${r.name}</div>
                      </div>
                      <div>
                        <div style="font-size:11px;color:var(--text-muted);font-weight:700;margin-bottom:5px;display:flex;align-items:center;gap:4px;"><i class="fas fa-user" style="font-size:10px;"></i> 피해자 번호</div>
                        <div style="font-size:20px;font-weight:900;color:#fff;">${r.victim_id || '-'}</div>
                      </div>
                      <div>
                        <div style="font-size:11px;color:var(--text-muted);font-weight:700;margin-bottom:5px;display:flex;align-items:center;gap:4px;"><i class="fas fa-user" style="font-size:10px;"></i> 피해자 닉네임</div>
                        <div style="font-size:20px;font-weight:900;color:#fff;">${r.victim_name || '-'}</div>
                      </div>
                    </div>
                    <!-- 금액 -->
                    ${!itemOnly ? `<div style="font-size:14px;color:var(--text-muted);display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                      <i class="fas fa-fire" style="color:var(--danger);font-size:13px;"></i>
                      <span>금액:</span>
                      <strong style="font-size:18px;font-weight:900;color:var(--primary);">${r.amount_display}</strong>
                      ${korAmt ? `<span style="font-size:13px;color:var(--text-muted);">(${korAmt})</span>` : ''}
                    </div>` : ''}
                    <!-- 아이템 -->
                    ${(hasItem && r.item_name) ? `<div style="font-size:14px;color:var(--text-muted);display:flex;align-items:center;gap:8px;">
                      <i class="fas fa-box" style="color:#a78bfa;font-size:13px;"></i>
                      <span>아이템:</span>
                      <strong style="font-size:16px;font-weight:900;color:#a78bfa;">${r.item_name}</strong>
                    </div>` : ''}
                    <!-- 사유 -->
                    ${r.reason ? `<div style="display:flex;flex-direction:column;gap:5px;padding:12px 14px;background:rgba(255,255,255,0.04);border-radius:9px;border:1px solid rgba(255,255,255,0.07);">
                      <div style="font-size:12px;color:var(--text-muted);display:flex;align-items:center;gap:6px;"><i class="fas fa-scroll" style="font-size:11px;"></i> 사유</div>
                      <div style="font-size:14px;color:rgba(255,255,255,0.85);line-height:1.6;">${r.reason}</div>
                    </div>` : ''}
                  </div>
                </div>`;
            });

            area.innerHTML = html;
        } else {
            area.innerHTML = `
            <div style="background:rgba(16,230,166,0.06);border:1px solid rgba(16,230,166,0.25);border-radius:16px;padding:28px 24px;text-align:center;">
                <div style="font-size:48px;margin-bottom:12px;">✅</div>
                <h3 style="font-weight:800;color:var(--success);margin-bottom:8px;font-size:18px;font-family:'Pretendard',system-ui,sans-serif;"><span style="color:var(--primary);">${trimQ}번</span> — 이력 없음</h3>
                <p style="color:var(--text-muted);font-size:14px;line-height:1.7;max-width:340px;margin:0 auto;font-family:'Pretendard',system-ui,sans-serif;">
                    현재 DB 기준으로 <strong style="color:#fff;">${trimQ}번</strong>의 블랙리스트 이력이 없습니다.<br>
                    <span style="font-size:12px;color:rgba(255,255,255,0.3);">신규 유저일 수 있으니 항상 주의하세요.</span>
                </p>
            </div>`;
        }
        area.scrollIntoView({behavior:'smooth', block:'nearest'});
    }

    const style = document.createElement('style');
    style.textContent = `@keyframes shake { 0%,100%{transform:rotate(0)} 20%{transform:rotate(-12deg)} 40%{transform:rotate(12deg)} 60%{transform:rotate(-8deg)} 80%{transform:rotate(6deg)} }`;
    document.head.appendChild(style);
    </script>

{# ════════════════════ 블랙리스트 목록 ════════════════════ #}
{% elif page=='list' %}
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:28px;flex-wrap:wrap;gap:12px;">
        <div>
            <div style="display:inline-flex;align-items:center;gap:7px;background:rgba(255,94,122,0.12);border:1px solid rgba(255,94,122,0.25);border-radius:20px;padding:5px 14px;font-size:12px;color:var(--danger);font-weight:700;margin-bottom:10px;">
                <i class="fas fa-exclamation-triangle"></i> BLACKLIST
            </div>
            <h2 style="font-size:24px;letter-spacing:-0.5px;">블랙리스트</h2>
            <p style="color:var(--text-muted);font-size:14px;margin-top:4px;">FREEDOM DB에 등록된 전체 블랙리스트 이력입니다.</p>
        </div>
        <a href="{{ url_for('index') }}" style="display:inline-flex;align-items:center;gap:8px;padding:10px 18px;border-radius:10px;background:var(--bg-elevated);border:1px solid var(--border-color);color:var(--text-muted);font-size:14px;font-weight:600;text-decoration:none;transition:all 0.2s;" onmouseover="this.style.borderColor='var(--primary)';this.style.color='#fff'" onmouseout="this.style.borderColor='var(--border-color)';this.style.color='var(--text-muted)'">
            <i class="fas fa-search" style="font-size:12px;"></i> 즉시 조회
        </a>
    </div>
    {% if scammers %}
    <div style="display:flex;flex-direction:column;gap:10px;margin-bottom:32px;">
        {% for r in scammers %}
        <a href="{{ url_for('scammer_detail', uid=r.unique_id) }}" style="display:flex;align-items:center;gap:0;background:var(--bg-surface);border:1px solid var(--border-color);border-radius:16px;overflow:hidden;text-decoration:none;transition:all 0.22s;position:relative;box-shadow:0 2px 8px rgba(0,0,0,0.2);"
          onmouseover="this.style.borderColor='rgba(255,94,122,0.45)';this.style.transform='translateX(4px)';this.style.boxShadow='0 6px 24px rgba(0,0,0,0.35),-4px 0 0 var(--danger)';"
          onmouseout="this.style.borderColor='var(--border-color)';this.style.transform='';this.style.boxShadow='0 2px 8px rgba(0,0,0,0.2)';">
          <div style="width:4px;min-height:72px;background:linear-gradient(180deg,var(--danger),rgba(255,94,122,0.4));flex-shrink:0;align-self:stretch;"></div>
          <div style="width:52px;text-align:center;flex-shrink:0;padding:0 4px;">
            <span style="font-size:13px;font-weight:800;color:var(--text-muted);font-family:'Pretendard',system-ui,sans-serif;">{{ loop.index + (current_page - 1) * 20 }}</span>
          </div>
          <div style="width:40px;height:40px;border-radius:10px;background:rgba(255,94,122,0.1);border:1px solid rgba(255,94,122,0.2);display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-right:16px;">
            <i class="fas fa-user-slash" style="color:var(--danger);font-size:14px;"></i>
          </div>
          <div style="flex:1;min-width:0;padding:16px 0;">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px;">
              <span style="font-size:15px;font-weight:800;color:#fff;font-family:'Pretendard',system-ui,sans-serif;">{{ r.name }}</span>
              <span style="font-size:13px;font-weight:900;color:var(--primary);font-family:'Pretendard',system-ui,sans-serif;background:rgba(91,159,255,0.12);padding:2px 8px;border-radius:6px;border:1px solid rgba(91,159,255,0.3);">{{ r.unique_id }}번</span>
              {% if r.victim_name or r.victim_id %}
              <span style="font-size:11px;color:var(--text-muted);">←</span>
              <span style="font-size:13px;font-weight:700;color:rgba(255,255,255,0.7);font-family:'Pretendard',system-ui,sans-serif;">{{ r.victim_name or '' }}</span>
              {% if r.victim_id %}<span style="font-size:12px;font-weight:700;color:var(--text-muted);font-family:'Pretendard',system-ui,sans-serif;background:rgba(255,255,255,0.05);padding:1px 6px;border-radius:5px;">{{ r.victim_id }}번</span>{% endif %}
              {% endif %}
            </div>
            <div style="display:flex;align-items:center;gap:6px;">
              <span style="font-size:11px;color:var(--text-muted);">{{ r.date[:10] }}</span>
              {% if r.category %}<span style="font-size:10px;color:var(--accent);background:rgba(167,139,250,0.1);padding:1px 6px;border-radius:4px;border:1px solid rgba(167,139,250,0.2);">{{ r.category }}</span>{% endif %}
            </div>
          </div>
          <div style="text-align:right;padding:0 20px;flex-shrink:0;">
            {% if r.category and '아이템' in r.category and r.item_name %}
            <div style="font-size:10px;color:var(--text-muted);margin-bottom:3px;font-weight:600;">먹튀 아이템</div>
            <div style="font-size:14px;font-weight:800;color:#a78bfa;white-space:nowrap;">{{ r.item_name }}</div>
            {% endif %}
            {% if not (r.category and '아이템' in r.category and r.item_name and '돈' not in r.category) %}
            <div style="font-size:10px;color:var(--text-muted);margin-bottom:2px;font-weight:600;letter-spacing:0.3px;">피해금액</div>
            <div style="font-size:16px;font-weight:900;color:var(--danger);white-space:nowrap;">{{ r.amount_display }}</div>
            {% endif %}
          </div>
          <div style="padding:0 20px 0 4px;flex-shrink:0;">
            <div style="width:30px;height:30px;border-radius:8px;background:rgba(91,159,255,0.1);border:1px solid rgba(91,159,255,0.2);display:flex;align-items:center;justify-content:center;">
              <i class="fas fa-chevron-right" style="color:var(--primary);font-size:11px;"></i>
            </div>
          </div>
        </a>
        {% endfor %}
    </div>
    {% else %}
    <div style="text-align:center;padding:80px 20px;background:var(--bg-surface);border-radius:20px;border:1px solid var(--border-color);">
        <div style="font-size:56px;margin-bottom:16px;">🎉</div>
        <h3 style="font-size:20px;margin-bottom:8px;">등록된 블랙리스트 이력이 없습니다</h3>
    </div>
    {% endif %}
    <div class="pagination">
        {% if current_page > 1 %}<a href="?page={{ current_page - 1 }}"><i class="fas fa-chevron-left"></i> 이전</a>{% endif %}
        <a class="active">{{ current_page }} 페이지</a>
        {% if scammers|length == 20 %}<a href="?page={{ current_page + 1 }}">다음 <i class="fas fa-chevron-right"></i></a>{% endif %}
    </div>

{# ════════════════════ 상세 페이지 ════════════════════ #}
{% elif page=='detail' %}
    <div style="max-width:640px;margin:0 auto;">
        <div style="background:linear-gradient(135deg,rgba(255,94,122,0.12),rgba(255,94,122,0.05));border:1px solid rgba(255,94,122,0.3);border-radius:16px;padding:20px 24px;margin-bottom:20px;display:flex;align-items:center;gap:14px;">
            <div style="width:44px;height:44px;background:rgba(255,94,122,0.2);border-radius:12px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                <i class="fas fa-exclamation-triangle" style="color:var(--danger);font-size:18px;"></i>
            </div>
            <div>
                <div style="font-size:14px;font-weight:700;color:var(--danger);">블랙리스트 이력 확인됨</div>
                <div style="font-size:13px;color:var(--text-muted);margin-top:2px;">이 유저와의 거래를 강력히 권장하지 않습니다.</div>
            </div>
        </div>
        <!-- 블랙리스트 경고 배너 -->
        <div style="background:linear-gradient(135deg,rgba(255,94,122,0.18),rgba(255,94,122,0.08));border:2px solid rgba(255,94,122,0.5);border-radius:16px;padding:18px 24px;margin-bottom:20px;text-align:center;">
            <div style="font-size:22px;font-weight:900;color:var(--danger);letter-spacing:2px;margin-bottom:8px;">⚠️ 블랙리스트 ⚠️</div>
            <div style="font-size:14px;font-weight:700;color:rgba(255,94,122,0.9);letter-spacing:0.5px;">🚫 블랙리스트에 등록된 유저는 제보를 받지않습니다 🚫</div>
        </div>
        <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:20px;overflow:hidden;margin-bottom:16px;box-shadow:var(--card-shadow);">
            <div style="background:linear-gradient(135deg,rgba(255,94,122,0.08),transparent);padding:28px;border-bottom:1px solid var(--border-color);display:flex;align-items:center;gap:20px;">
                <div style="width:64px;height:64px;background:rgba(255,94,122,0.15);border:2px solid rgba(255,94,122,0.3);border-radius:18px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                    <i class="fas fa-user-slash" style="color:var(--danger);font-size:24px;"></i>
                </div>
                <div style="flex:1;min-width:0;">
                    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
                        <h2 style="font-size:24px;font-weight:900;margin:0;font-family:'Pretendard',system-ui,sans-serif;color:#A8D932;">{{ s.name }}</h2>
                        <div style="display:inline-flex;align-items:center;gap:6px;background:rgba(168,217,50,0.1);border:1.5px solid rgba(168,217,50,0.35);border-radius:10px;padding:4px 12px;">
                            <span style="font-family:'Pretendard',system-ui,sans-serif;color:#A8D932;font-size:17px;font-weight:900;">{{ s.unique_id }}번</span>
                            <button onclick="copyToClipboard('{{ s.unique_id }}')" style="background:none;border:none;cursor:pointer;color:#A8D932;padding:0;transition:opacity 0.2s;opacity:0.6;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.6'" title="복사"><i class="fas fa-copy" style="font-size:13px;"></i></button>
                        </div>
                    </div>
                </div>
            </div>
            <div style="padding:24px 28px;">
                <div style="display:grid;gap:14px;">
                    {% set has_item = s.category and ('아이템' in s.category) %}
                    {% set has_money = s.category and ('돈' in s.category) %}
                    {% set item_only = has_item and s.item_name and not has_money %}
                    {% if has_item and s.item_name %}
                    <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 16px;background:rgba(167,139,250,0.08);border-radius:12px;border:1px solid rgba(167,139,250,0.3);">
                        <div style="display:flex;align-items:center;gap:10px;color:var(--text-muted);font-size:14px;">
                            <i class="fas fa-box" style="font-size:12px;color:var(--accent);"></i>먹튀 아이템
                        </div>
                        <strong style="color:var(--accent);font-size:18px;font-weight:900;">{{ s.item_name }}</strong>
                    </div>
                    {% endif %}
                    {% if not item_only %}
                    <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 16px;background:var(--bg-elevated);border-radius:12px;border:1px solid var(--border-color);">
                        <div style="display:flex;align-items:center;gap:10px;color:var(--text-muted);font-size:14px;">
                            <i class="fas fa-won-sign" style="font-size:12px;color:var(--danger);"></i>피해 금액
                        </div>
                        <div style="text-align:right;">
                            <strong style="color:var(--danger);font-size:20px;font-weight:800;">{{ s.amount_display }}</strong>
                            <div style="font-size:12px;color:var(--text-muted);">({{ korean_num(s.amount_int) }})</div>
                        </div>
                    </div>
                    {% endif %}
                    <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 16px;background:var(--bg-elevated);border-radius:12px;border:1px solid var(--border-color);">
                        <div style="display:flex;align-items:center;gap:10px;color:var(--text-muted);font-size:14px;">
                            <i class="fas fa-tag" style="font-size:12px;color:var(--accent);"></i>카테고리
                        </div>
                        <span style="color:var(--accent);font-size:14px;font-weight:700;background:rgba(167,139,250,0.1);padding:4px 12px;border-radius:8px;border:1px solid rgba(167,139,250,0.2);">{{ s.category or '주사위' }}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 16px;background:var(--bg-elevated);border-radius:12px;border:1px solid var(--border-color);">
                        <div style="display:flex;align-items:center;gap:10px;color:var(--text-muted);font-size:14px;">
                            <i class="fas fa-calendar" style="font-size:12px;color:var(--primary);"></i>등록 일자
                        </div>
                        <span style="color:#fff;font-size:14px;font-weight:600;">{{ s.date }}</span>
                    </div>
                    {% if s.reason %}
                    <div style="padding:14px 16px;background:var(--bg-elevated);border-radius:12px;border:1px solid var(--border-color);">
                        <div style="display:flex;align-items:center;gap:10px;color:var(--text-muted);font-size:13px;margin-bottom:8px;">
                            <i class="fas fa-comment" style="font-size:12px;color:var(--warning);"></i>사유
                        </div>
                        <div style="font-size:13px;color:var(--text-main);line-height:1.7;white-space:pre-wrap;">{{ s.reason }}</div>
                    </div>
                    {% endif %}
                    {% if s.evidence_url %}
                    <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 16px;background:var(--bg-elevated);border-radius:12px;border:1px solid var(--border-color);">
                        <div style="display:flex;align-items:center;gap:10px;color:var(--text-muted);font-size:14px;">
                            <i class="fas fa-paperclip" style="font-size:12px;color:var(--accent);"></i>증거 자료
                        </div>
                        <a href="{{ s.evidence_url }}" target="_blank" style="display:inline-flex;align-items:center;gap:6px;padding:6px 14px;background:rgba(91,159,255,0.1);border:1px solid rgba(91,159,255,0.25);border-radius:8px;color:var(--primary);font-size:13px;font-weight:600;text-decoration:none;">링크 열기 <i class="fas fa-external-link-alt" style="font-size:10px;"></i></a>
                    </div>
                    {% endif %}
                    {% if s.admin_memo %}
                    <div style="padding:14px 16px;background:rgba(255,202,94,0.05);border:1px solid rgba(255,202,94,0.2);border-radius:12px;">
                        <div style="display:flex;align-items:center;gap:8px;font-size:13px;color:var(--warning);">
                            <i class="fas fa-sticky-note"></i><span>{{ s.admin_memo }}</span>
                        </div>
                    </div>
                    {% endif %}
                    {% if s.victim_id or s.victim_name %}
                    <div style="padding:14px 16px;background:rgba(255,94,122,0.04);border:1px solid rgba(255,94,122,0.15);border-radius:12px;">
                        <div style="display:flex;align-items:center;gap:8px;font-size:13px;color:var(--danger);margin-bottom:8px;">
                            <i class="fas fa-user-shield" style="font-size:12px;"></i><span style="font-weight:700;">피해자 정보</span>
                        </div>
                        <div style="display:flex;gap:10px;flex-wrap:wrap;">
                            {% if s.victim_id %}
                            <span style="font-size:12px;background:rgba(255,255,255,0.05);border:1px solid var(--border-color);border-radius:6px;padding:3px 10px;color:var(--text-muted);font-family:'Pretendard',system-ui,sans-serif;"># {{ s.victim_id }}</span>
                            {% endif %}
                            {% if s.victim_name %}
                            <span style="font-size:12px;background:rgba(255,255,255,0.05);border:1px solid var(--border-color);border-radius:6px;padding:3px 10px;color:#fff;font-weight:600;">{{ s.victim_name }}</span>
                            {% endif %}
                        </div>
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>

{# ════════════════════ 후원의 전당 ════════════════════ #}
{% elif page=='hof' %}
    <div style="max-width:720px;margin:0 auto;">
        <div style="text-align:center;margin-bottom:28px;">
            <div style="font-size:52px;margin-bottom:12px;">💝</div>
            <h2 style="font-size:26px;font-weight:900;letter-spacing:-0.5px;font-family:'Pretendard',system-ui,sans-serif;">후원의 전당</h2>
            <p style="color:var(--text-muted);font-size:14px;margin-top:6px;font-family:'Pretendard',system-ui,sans-serif;">FREEDOM을 응원해주신 소중한 분들</p>
        </div>

        {% if total_hof_amount and total_hof_amount > 0 %}
        <div style="background:linear-gradient(135deg,rgba(167,139,250,0.18),rgba(91,159,255,0.12));border:2px solid rgba(167,139,250,0.5);border-radius:16px;padding:18px 24px;margin-bottom:24px;text-align:center;box-shadow:0 0 30px rgba(167,139,250,0.15);">
            <div style="font-size:12px;font-weight:700;color:var(--accent);letter-spacing:1px;margin-bottom:6px;font-family:'Pretendard',system-ui,sans-serif;">💜 총 누적 후원금액</div>
            <div style="font-size:28px;font-weight:900;color:#fff;font-family:'Pretendard',system-ui,sans-serif;">{{ korean_hof(total_hof_amount) }}</div>
        </div>
        {% endif %}

        {% if hof_entries %}
        <div style="display:flex;flex-direction:column;gap:12px;">
            {% for entry in hof_entries %}
            <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:16px;padding:18px 22px;display:flex;align-items:center;gap:16px;transition:all 0.2s;" onmouseover="this.style.borderColor='rgba(167,139,250,0.4)';this.style.boxShadow='0 4px 20px rgba(0,0,0,0.3)'" onmouseout="this.style.borderColor='var(--border-color)';this.style.boxShadow=''">
                <div style="width:46px;height:46px;border-radius:13px;background:linear-gradient(135deg,rgba(167,139,250,0.2),rgba(91,159,255,0.1));border:1px solid rgba(167,139,250,0.3);display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0;">
                    {{ entry.badge or '💝' }}
                </div>
                <div style="flex:1;min-width:0;">
                    <div style="font-size:15px;font-weight:800;color:#fff;margin-bottom:3px;font-family:'Pretendard',system-ui,sans-serif;">{{ entry.name }}</div>
                    {% if entry.description %}
                    <div style="font-size:13px;color:var(--text-muted);line-height:1.5;font-family:'Pretendard',system-ui,sans-serif;">{{ entry.description }}</div>
                    {% endif %}
                </div>
                {% if entry.amount %}
                <div style="text-align:right;flex-shrink:0;">
                    <div style="font-size:10px;color:var(--text-muted);margin-bottom:3px;font-weight:600;letter-spacing:0.4px;font-family:'Pretendard',system-ui,sans-serif;">후원 금액</div>
                    <div style="font-size:16px;font-weight:900;color:var(--accent);font-family:'Pretendard',system-ui,sans-serif;">{{ entry.amount }}</div>
                </div>
                {% endif %}
                <div style="text-align:right;flex-shrink:0;">
                    <div style="font-size:11px;color:var(--text-muted);font-family:'Pretendard',system-ui,sans-serif;">{{ entry.created_at[:10] }}</div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div style="text-align:center;padding:80px 20px;background:var(--bg-surface);border-radius:20px;border:1px solid var(--border-color);">
            <div style="font-size:56px;margin-bottom:16px;">💝</div>
            <h3 style="font-size:18px;margin-bottom:8px;color:var(--text-muted);font-family:'Pretendard',system-ui,sans-serif;">아직 후원자가 없습니다</h3>
            <p style="color:var(--text-muted);font-size:14px;font-family:'Pretendard',system-ui,sans-serif;">FREEDOM을 응원해주세요!</p>
        </div>
        {% endif %}
    </div>

{# ════════════════════ 이의제기 ════════════════════ #}
{% elif page=='appeal' %}
    <div style="max-width:620px;margin:0 auto;">
        <div style="margin-bottom:28px;">
            <div style="display:inline-flex;align-items:center;gap:7px;background:rgba(255,202,94,0.12);border:1px solid rgba(255,202,94,0.25);border-radius:20px;padding:5px 14px;font-size:12px;color:var(--warning);font-weight:700;margin-bottom:12px;">
                <i class="fas fa-gavel"></i> APPEAL
            </div>
            <h2 style="font-size:24px;letter-spacing:-0.5px;margin-bottom:6px;">이의 제기</h2>
            <p style="color:var(--text-muted);font-size:14px;line-height:1.7;">허위 사실로 등록된 경우, 소명 자료를 제출하시면 관리자가 검토 후 조치해 드립니다.</p>
        </div>
        <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:20px;overflow:hidden;box-shadow:var(--card-shadow);">
            <div style="background:linear-gradient(135deg,rgba(255,202,94,0.06),transparent);border-bottom:1px solid var(--border-color);padding:16px 24px;display:flex;align-items:center;gap:12px;">
                <i class="fas fa-info-circle" style="color:var(--warning);font-size:14px;"></i>
                <span style="font-size:13px;color:var(--text-muted);">허위 이의 제기는 제보 차단으로 이어질 수 있습니다.</span>
            </div>
            <div style="padding:28px;">
                <form method="POST" action="{{ url_for('submit_appeal') }}" style="display:flex;flex-direction:column;gap:16px;">
                    <input type="hidden" name="unique_id" value="{{ request.args.get('uid', '') }}">
                    <div>
                        <label style="display:block;font-size:13px;font-weight:600;color:var(--text-muted);margin-bottom:8px;">본인 고유번호</label>
                        <input class="input" value="{{ request.args.get('uid', '고유번호가 없습니다') }}" disabled style="opacity:0.6;">
                    </div>
                    <div>
                        <label style="display:block;font-size:13px;font-weight:600;color:var(--text-muted);margin-bottom:8px;">연락처 <span style="color:var(--danger)">*</span></label>
                        <input class="input" name="contact" placeholder="Discord 닉네임 또는 연락 가능한 수단" required>
                    </div>
                    <div>
                        <label style="display:block;font-size:13px;font-weight:600;color:var(--text-muted);margin-bottom:8px;">소명 내용 및 증거 링크 <span style="color:var(--danger)">*</span></label>
                        <textarea class="input" name="reason" placeholder="억울한 상황을 상세히 설명하고, 증거 자료 링크를 첨부해주세요." required style="min-height:140px;"></textarea>
                    </div>
                    <button class="btn" type="submit" style="width:100%;padding:16px;font-size:15px;margin-top:8px;">
                        <i class="fas fa-paper-plane"></i> 이의 제기 제출
                    </button>
                </form>
            </div>
        </div>
    </div>

{# ════════════════════ 관리자 패널 ════════════════════ #}
{% elif page=='admin' %}

    {# ════ 대시보드 홈 ════ #}
    {% if tab=='dashboard' %}
    {% set ns2 = namespace(item_cnt=0, money_cnt=0, total_amt=0) %}
    {% for s in all_scammers %}
        {% if s.category and '아이템' in s.category %}{% set ns2.item_cnt = ns2.item_cnt + 1 %}{% endif %}
        {% if s.category and '금전' in s.category or (s.category and '돈' in s.category) %}{% set ns2.money_cnt = ns2.money_cnt + 1 %}{% endif %}
        {% set ns2.total_amt = ns2.total_amt + (s.amount_int or 0) %}
    {% endfor %}

    <!-- 어드민 웰컴 배너 -->
    <div style="background:linear-gradient(135deg,rgba(91,159,255,0.12) 0%,rgba(167,139,250,0.08) 50%,rgba(91,159,255,0.06) 100%);border:1px solid rgba(91,159,255,0.25);border-radius:18px;padding:20px 24px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;">
        <div style="display:flex;align-items:center;gap:14px;">
            <img src="{{ user.avatar_url }}" style="width:48px;height:48px;border-radius:50%;border:2px solid rgba(91,159,255,0.4);">
            <div>
                <div style="font-size:12px;color:var(--text-muted);margin-bottom:3px;">관리자 패널</div>
                <div style="font-size:18px;font-weight:800;color:#fff;">안녕하세요, {{ user.username }}님 👋</div>
            </div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
            <a href="{{ url_for('admin_export_csv') }}" style="display:inline-flex;align-items:center;gap:6px;padding:8px 14px;border-radius:9px;background:rgba(34,240,181,0.1);border:1px solid rgba(34,240,181,0.25);color:var(--success);font-size:13px;font-weight:700;text-decoration:none;transition:all 0.2s;" onmouseover="this.style.background='rgba(34,240,181,0.18)'" onmouseout="this.style.background='rgba(34,240,181,0.1)'">
                <i class="fas fa-download" style="font-size:11px;"></i> DB 백업
            </a>
            <a href="{{ url_for('index') }}" target="_blank" style="display:inline-flex;align-items:center;gap:6px;padding:8px 14px;border-radius:9px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:var(--text-muted);font-size:13px;font-weight:700;text-decoration:none;transition:all 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.1)';this.style.color='#fff'" onmouseout="this.style.background='rgba(255,255,255,0.05)';this.style.color='var(--text-muted)'">
                <i class="fas fa-external-link-alt" style="font-size:11px;"></i> 조회 페이지
            </a>
        </div>
    </div>

    <!-- 통계 카드 4개 (컴팩트) -->
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px;">
        <div style="background:var(--bg-surface);border:1px solid rgba(255,94,122,0.25);border-radius:14px;padding:16px 14px;display:flex;align-items:center;gap:12px;">
            <div style="width:40px;height:40px;border-radius:11px;background:rgba(255,94,122,0.15);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                <i class="fas fa-user-slash" style="color:var(--danger);font-size:15px;"></i>
            </div>
            <div>
                <div style="font-size:24px;font-weight:900;color:var(--danger);line-height:1.1;">{{ distinct_scammer_count }}</div>
                <div style="font-size:13px;font-weight:700;color:var(--text-muted);margin-top:3px;">총 블랙리스트</div>
            </div>
        </div>
        <div style="background:var(--bg-surface);border:1px solid rgba(167,139,250,0.25);border-radius:14px;padding:16px 14px;display:flex;align-items:center;gap:12px;">
            <div style="width:40px;height:40px;border-radius:11px;background:rgba(167,139,250,0.15);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                <i class="fas fa-box" style="color:#a78bfa;font-size:15px;"></i>
            </div>
            <div>
                <div style="font-size:24px;font-weight:900;color:#a78bfa;line-height:1.1;">{{ ns2.item_cnt }}</div>
                <div style="font-size:13px;font-weight:700;color:var(--text-muted);margin-top:3px;">아이템 사기</div>
            </div>
        </div>
        <div style="background:var(--bg-surface);border:1px solid rgba(16,230,166,0.25);border-radius:14px;padding:16px 14px;display:flex;align-items:center;gap:12px;">
            <div style="width:40px;height:40px;border-radius:11px;background:rgba(16,230,166,0.12);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                <i class="fas fa-won-sign" style="color:var(--success);font-size:15px;"></i>
            </div>
            <div>
                <div style="font-size:24px;font-weight:900;color:var(--success);line-height:1.1;">{{ ns2.money_cnt }}</div>
                <div style="font-size:13px;font-weight:700;color:var(--text-muted);margin-top:3px;">금전 사기</div>
            </div>
        </div>
        <div style="background:var(--bg-surface);border:1px solid rgba(255,202,94,0.25);border-radius:14px;padding:16px 14px;display:flex;align-items:center;gap:12px;">
            <div style="width:40px;height:40px;border-radius:11px;background:rgba(255,202,94,0.12);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                <i class="fas fa-chart-bar" style="color:var(--warning);font-size:15px;"></i>
            </div>
            <div>
                <div style="font-size:16px;font-weight:900;color:var(--warning);line-height:1.2;word-break:break-all;">{{ korean_num(ns2.total_amt) }}</div>
                <div style="font-size:13px;font-weight:700;color:var(--text-muted);margin-top:3px;">누적 피해</div>
            </div>
        </div>
    </div>

    <!-- 메인 2컬럼 레이아웃 -->
    <div style="display:grid;grid-template-columns:1fr 280px;gap:16px;align-items:start;">

        <!-- 왼쪽: 빠른 실행 + 최근 등록 -->
        <div style="display:flex;flex-direction:column;gap:14px;">

            <!-- 빠른 실행 -->
            <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:16px;overflow:hidden;">
                <div style="padding:12px 18px;border-bottom:1px solid var(--border-color);display:flex;align-items:center;gap:8px;">
                    <i class="fas fa-bolt" style="color:var(--warning);font-size:12px;"></i>
                    <span style="font-size:13px;font-weight:700;color:#fff;">빠른 실행</span>
                </div>
                <div style="padding:14px;display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">
                    <a href="?tab=add" style="text-decoration:none;display:flex;flex-direction:column;align-items:center;gap:8px;padding:14px 10px;border-radius:12px;background:rgba(91,159,255,0.07);border:1px solid rgba(91,159,255,0.2);transition:all 0.2s;" onmouseover="this.style.background='rgba(91,159,255,0.15)';this.style.borderColor='rgba(91,159,255,0.45)';this.style.transform='translateY(-2px)'" onmouseout="this.style.background='rgba(91,159,255,0.07)';this.style.borderColor='rgba(91,159,255,0.2)';this.style.transform=''">
                        <div style="width:36px;height:36px;border-radius:10px;background:rgba(91,159,255,0.2);display:flex;align-items:center;justify-content:center;"><i class="fas fa-plus" style="color:var(--primary);font-size:14px;"></i></div>
                        <span style="font-size:12px;font-weight:700;color:#fff;text-align:center;">수동 등록</span>
                    </a>
                    <a href="?tab=scammers" style="text-decoration:none;display:flex;flex-direction:column;align-items:center;gap:8px;padding:14px 10px;border-radius:12px;background:rgba(255,94,122,0.07);border:1px solid rgba(255,94,122,0.2);transition:all 0.2s;" onmouseover="this.style.background='rgba(255,94,122,0.15)';this.style.borderColor='rgba(255,94,122,0.45)';this.style.transform='translateY(-2px)'" onmouseout="this.style.background='rgba(255,94,122,0.07)';this.style.borderColor='rgba(255,94,122,0.2)';this.style.transform=''">
                        <div style="width:36px;height:36px;border-radius:10px;background:rgba(255,94,122,0.18);display:flex;align-items:center;justify-content:center;"><i class="fas fa-user-slash" style="color:var(--danger);font-size:14px;"></i></div>
                        <span style="font-size:12px;font-weight:700;color:#fff;text-align:center;">블랙리스트<br><span style="font-size:10px;color:var(--text-muted);font-weight:600;">{{ distinct_scammer_count }}명</span></span>
                    </a>
                    <a href="?tab=notices" style="text-decoration:none;display:flex;flex-direction:column;align-items:center;gap:8px;padding:14px 10px;border-radius:12px;background:rgba(255,202,94,0.07);border:1px solid rgba(255,202,94,0.2);transition:all 0.2s;" onmouseover="this.style.background='rgba(255,202,94,0.15)';this.style.borderColor='rgba(255,202,94,0.45)';this.style.transform='translateY(-2px)'" onmouseout="this.style.background='rgba(255,202,94,0.07)';this.style.borderColor='rgba(255,202,94,0.2)';this.style.transform=''">
                        <div style="width:36px;height:36px;border-radius:10px;background:rgba(255,202,94,0.18);display:flex;align-items:center;justify-content:center;"><i class="fas fa-bullhorn" style="color:var(--warning);font-size:14px;"></i></div>
                        <span style="font-size:12px;font-weight:700;color:#fff;text-align:center;">공지 관리<br><span style="font-size:10px;color:var(--text-muted);font-weight:600;">{{ all_notices|length }}건</span></span>
                    </a>
                    <a href="?tab=hof_admin" style="text-decoration:none;display:flex;flex-direction:column;align-items:center;gap:8px;padding:14px 10px;border-radius:12px;background:rgba(167,139,250,0.07);border:1px solid rgba(167,139,250,0.2);transition:all 0.2s;" onmouseover="this.style.background='rgba(167,139,250,0.15)';this.style.borderColor='rgba(167,139,250,0.45)';this.style.transform='translateY(-2px)'" onmouseout="this.style.background='rgba(167,139,250,0.07)';this.style.borderColor='rgba(167,139,250,0.2)';this.style.transform=''">
                        <div style="width:36px;height:36px;border-radius:10px;background:rgba(167,139,250,0.18);display:flex;align-items:center;justify-content:center;"><i class="fas fa-heart" style="color:var(--accent);font-size:14px;"></i></div>
                        <span style="font-size:12px;font-weight:700;color:#fff;text-align:center;">후원의 전당</span>
                    </a>
                    <a href="?tab=logs" style="text-decoration:none;display:flex;flex-direction:column;align-items:center;gap:8px;padding:14px 10px;border-radius:12px;background:rgba(16,230,166,0.06);border:1px solid rgba(16,230,166,0.18);transition:all 0.2s;" onmouseover="this.style.background='rgba(16,230,166,0.14)';this.style.borderColor='rgba(16,230,166,0.4)';this.style.transform='translateY(-2px)'" onmouseout="this.style.background='rgba(16,230,166,0.06)';this.style.borderColor='rgba(16,230,166,0.18)';this.style.transform=''">
                        <div style="width:36px;height:36px;border-radius:10px;background:rgba(16,230,166,0.15);display:flex;align-items:center;justify-content:center;"><i class="fas fa-history" style="color:var(--success);font-size:14px;"></i></div>
                        <span style="font-size:12px;font-weight:700;color:#fff;text-align:center;">감사 로그</span>
                    </a>
                    <a href="?tab=settings" style="text-decoration:none;display:flex;flex-direction:column;align-items:center;gap:8px;padding:14px 10px;border-radius:12px;background:rgba(148,163,184,0.06);border:1px solid rgba(148,163,184,0.15);transition:all 0.2s;" onmouseover="this.style.background='rgba(148,163,184,0.14)';this.style.borderColor='rgba(148,163,184,0.35)';this.style.transform='translateY(-2px)'" onmouseout="this.style.background='rgba(148,163,184,0.06)';this.style.borderColor='rgba(148,163,184,0.15)';this.style.transform=''">
                        <div style="width:36px;height:36px;border-radius:10px;background:rgba(148,163,184,0.14);display:flex;align-items:center;justify-content:center;"><i class="fas fa-cog" style="color:#94a3b8;font-size:14px;"></i></div>
                        <span style="font-size:12px;font-weight:700;color:#fff;text-align:center;">설정</span>
                    </a>
                </div>
            </div>

            <!-- 최근 등록 -->
            {% if all_scammers %}
            <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:16px;overflow:hidden;">
                <div style="padding:12px 18px;border-bottom:1px solid var(--border-color);display:flex;align-items:center;justify-content:space-between;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <div style="width:7px;height:7px;border-radius:50%;background:var(--danger);box-shadow:0 0 7px var(--danger);animation:pulse 1.5s infinite;"></div>
                        <span style="font-size:13px;font-weight:700;color:var(--danger);">최근 등록</span>
                    </div>
                    <a href="?tab=scammers" style="font-size:12px;color:var(--primary);text-decoration:none;font-weight:600;">전체 보기 →</a>
                </div>
                {% for s in all_scammers[:8] %}
                <div style="padding:10px 18px;border-bottom:1px solid rgba(255,255,255,0.03);display:flex;align-items:center;gap:12px;">
                    <span style="font-size:12px;font-weight:700;color:var(--primary);background:rgba(91,159,255,0.1);padding:2px 7px;border-radius:5px;white-space:nowrap;min-width:52px;text-align:center;">{{ s.unique_id }}번</span>
                    <span style="font-size:13px;font-weight:700;color:#fff;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ s.name }}</span>
                    {% if s.category %}<span style="font-size:10px;color:#a78bfa;background:rgba(167,139,250,0.1);padding:2px 6px;border-radius:4px;white-space:nowrap;border:1px solid rgba(167,139,250,0.2);">{{ s.category }}</span>{% endif %}
                    <span style="font-size:11px;color:var(--danger);font-weight:700;white-space:nowrap;">{{ s.amount_display }}</span>
                    <span style="font-size:11px;color:var(--text-muted);white-space:nowrap;">{{ s.date[:10] if s.date else '' }}</span>
                </div>
                {% endfor %}
            </div>
            {% endif %}
        </div>

        <!-- 오른쪽: 시스템 현황 + 대기 신고 -->
        <div style="display:flex;flex-direction:column;gap:14px;">

            <!-- 시스템 현황 -->
            <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:16px;overflow:hidden;">
                <div style="padding:12px 18px;border-bottom:1px solid var(--border-color);display:flex;align-items:center;gap:8px;">
                    <i class="fas fa-server" style="color:var(--success);font-size:12px;"></i>
                    <span style="font-size:13px;font-weight:700;color:#fff;">시스템 현황</span>
                </div>
                <div style="padding:14px;display:flex;flex-direction:column;gap:10px;">
                    <div style="display:flex;align-items:center;justify-content:space-between;">
                        <span style="font-size:12px;color:var(--text-muted);">DB 상태</span>
                        <span style="font-size:12px;font-weight:700;color:var(--success);display:flex;align-items:center;gap:5px;"><span style="width:6px;height:6px;border-radius:50%;background:var(--success);display:inline-block;"></span>정상</span>
                    </div>
                    <div style="display:flex;align-items:center;justify-content:space-between;">
                        <span style="font-size:12px;color:var(--text-muted);">총 등록 인원</span>
                        <span style="font-size:12px;font-weight:700;color:#fff;">{{ distinct_scammer_count }}명</span>
                    </div>
                    <div style="display:flex;align-items:center;justify-content:space-between;">
                        <span style="font-size:12px;color:var(--text-muted);">공지/패치노트</span>
                        <span style="font-size:12px;font-weight:700;color:#fff;">{{ all_notices|length }}건</span>
                    </div>
                    <div style="display:flex;align-items:center;justify-content:space-between;">
                        <span style="font-size:12px;color:var(--text-muted);">내 권한</span>
                        {% if readonly_admin %}
                        <span style="font-size:11px;font-weight:700;color:var(--text-muted);background:rgba(255,255,255,0.06);padding:2px 8px;border-radius:5px;">읽기 전용</span>
                        {% else %}
                        <span style="font-size:11px;font-weight:700;color:var(--warning);background:rgba(255,202,94,0.1);padding:2px 8px;border-radius:5px;border:1px solid rgba(255,202,94,0.2);">전체 관리자</span>
                        {% endif %}
                    </div>
                </div>
            </div>

            <!-- 대기 중인 신고 -->
            {% if pending_reports %}
            <div style="background:var(--bg-surface);border:1px solid rgba(255,94,122,0.25);border-radius:16px;overflow:hidden;">
                <div style="padding:12px 18px;border-bottom:1px solid rgba(255,94,122,0.2);display:flex;align-items:center;justify-content:space-between;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <i class="fas fa-exclamation-circle" style="color:var(--danger);font-size:12px;"></i>
                        <span style="font-size:13px;font-weight:700;color:var(--danger);">대기 신고</span>
                    </div>
                    <span style="font-size:11px;font-weight:800;color:var(--danger);background:rgba(255,94,122,0.15);border:1px solid rgba(255,94,122,0.3);padding:2px 8px;border-radius:10px;">{{ pending_reports|length }}건</span>
                </div>
                {% for rp in pending_reports[:5] %}
                <div style="padding:10px 16px;border-bottom:1px solid rgba(255,255,255,0.03);">
                    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
                        <span style="font-size:12px;font-weight:700;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ rp.target_name }}</span>
                        <span style="font-size:10px;color:var(--text-muted);white-space:nowrap;">{{ rp.created_at[:10] if rp.created_at else '' }}</span>
                    </div>
                    <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">{{ rp.category or '' }} · {{ rp.amount_display }}</div>
                </div>
                {% endfor %}
                <div style="padding:10px 16px;">
                    <a href="?tab=reports" style="font-size:12px;color:var(--primary);font-weight:700;text-decoration:none;">신고 관리 →</a>
                </div>
            </div>
            {% else %}
            <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:16px;padding:20px;text-align:center;">
                <div style="font-size:24px;margin-bottom:8px;">✅</div>
                <div style="font-size:12px;color:var(--text-muted);">대기 중인 신고가 없습니다</div>
            </div>
            {% endif %}

            <!-- 대기 중인 이의제기 -->
            {% if pending_appeals %}
            <div style="background:var(--bg-surface);border:1px solid rgba(255,202,94,0.25);border-radius:16px;overflow:hidden;">
                <div style="padding:12px 18px;border-bottom:1px solid rgba(255,202,94,0.2);display:flex;align-items:center;justify-content:space-between;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <i class="fas fa-gavel" style="color:var(--warning);font-size:12px;"></i>
                        <span style="font-size:13px;font-weight:700;color:var(--warning);">이의제기</span>
                    </div>
                    <span style="font-size:11px;font-weight:800;color:var(--warning);background:rgba(255,202,94,0.12);border:1px solid rgba(255,202,94,0.25);padding:2px 8px;border-radius:10px;">{{ pending_appeals|length }}건</span>
                </div>
                {% for ap in pending_appeals[:3] %}
                <div style="padding:10px 16px;border-bottom:1px solid rgba(255,255,255,0.03);">
                    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
                        <span style="font-size:12px;font-weight:700;color:#fff;">{{ ap.unique_id }}번</span>
                        <span style="font-size:10px;color:var(--text-muted);white-space:nowrap;">{{ ap.created_at[:10] if ap.created_at else '' }}</span>
                    </div>
                    <div style="font-size:11px;color:var(--text-muted);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ ap.reason[:40] if ap.reason else '' }}</div>
                </div>
                {% endfor %}
                <div style="padding:10px 16px;">
                    <a href="?tab=appeals" style="font-size:12px;color:var(--primary);font-weight:700;text-decoration:none;">이의제기 관리 →</a>
                </div>
            </div>
            {% endif %}

        </div>
    </div>

    {% endif %}{# end dashboard #}

    <!-- 서브 탭 공통 상단 네비 (dashboard 제외) -->
    {% if tab != 'dashboard' %}
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid var(--border-color);">
        <a href="?tab=dashboard" style="display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:9px;background:var(--bg-elevated);border:1px solid var(--border-color);color:var(--text-muted);font-size:13px;font-weight:700;text-decoration:none;transition:all 0.2s;" onmouseover="this.style.borderColor='var(--primary)';this.style.color='#fff'" onmouseout="this.style.borderColor='var(--border-color)';this.style.color='var(--text-muted)'">
            <i class="fas fa-chevron-left" style="font-size:11px;"></i> 홈
        </a>
        <span style="color:var(--text-muted);font-size:13px;">
            {% if tab=='add' %}<i class="fas fa-plus-circle" style="color:var(--primary);"></i> <span style="color:#fff;font-weight:700;">수동 등록</span>
            {% elif tab=='scammers' %}<i class="fas fa-user-slash" style="color:var(--danger);"></i> <span style="color:#fff;font-weight:700;">블랙리스트 관리</span>
            {% elif tab=='notices' %}<i class="fas fa-bullhorn" style="color:var(--warning);"></i> <span style="color:#fff;font-weight:700;">공지 관리</span>
            {% elif tab=='hof_admin' %}<i class="fas fa-heart" style="color:var(--accent);"></i> <span style="color:#fff;font-weight:700;">후원의 전당</span>
            {% elif tab=='logs' %}<i class="fas fa-history" style="color:var(--success);"></i> <span style="color:#fff;font-weight:700;">감사 로그</span>
            {% elif tab=='settings' %}<i class="fas fa-cog" style="color:#94a3b8;"></i> <span style="color:#fff;font-weight:700;">설정</span>
            {% elif tab=='reports' %}<i class="fas fa-flag" style="color:var(--primary);"></i> <span style="color:#fff;font-weight:700;">신고 관리</span>
            {% elif tab=='appeals' %}<i class="fas fa-gavel" style="color:var(--warning);"></i> <span style="color:#fff;font-weight:700;">이의제기 관리</span>
            {% elif tab=='blacklist' %}<i class="fas fa-ban" style="color:var(--danger);"></i> <span style="color:#fff;font-weight:700;">제보자 블랙리스트</span>
            {% endif %}
        </span>
    </div>
    {% endif %}

    <!-- 관리자 통계 미니바 (scammers 탭) -->
    {% if tab=='scammers' %}
    {% set ns = namespace(item_cnt=0, money_cnt=0, total_amt=0) %}
    {% for s in all_scammers %}
        {% if s.category and '아이템' in s.category %}{% set ns.item_cnt = ns.item_cnt + 1 %}{% endif %}
        {% if s.category and '돈' in s.category %}{% set ns.money_cnt = ns.money_cnt + 1 %}{% endif %}
        {% set ns.total_amt = ns.total_amt + (s.amount_int or 0) %}
    {% endfor %}
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;">
        <div style="background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:12px;padding:16px;text-align:center;">
            <div style="font-size:22px;font-weight:900;color:var(--danger);font-family:'Pretendard',system-ui,sans-serif;">{{ distinct_scammer_count }}</div>
            <div style="font-size:13px;font-weight:700;color:var(--text-muted);margin-top:4px;font-family:'Pretendard',system-ui,sans-serif;">총 블랙리스트</div>
        </div>
        <div style="background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:12px;padding:16px;text-align:center;">
            <div style="font-size:22px;font-weight:900;color:#a78bfa;font-family:'Pretendard',system-ui,sans-serif;">{{ ns.item_cnt }}</div>
            <div style="font-size:13px;font-weight:700;color:var(--text-muted);margin-top:4px;font-family:'Pretendard',system-ui,sans-serif;">아이템 사기</div>
        </div>
        <div style="background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:12px;padding:16px;text-align:center;">
            <div style="font-size:22px;font-weight:900;color:var(--success);font-family:'Pretendard',system-ui,sans-serif;">{{ ns.money_cnt }}</div>
            <div style="font-size:13px;font-weight:700;color:var(--text-muted);margin-top:4px;font-family:'Pretendard',system-ui,sans-serif;">금전 사기</div>
        </div>
        <div style="background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:12px;padding:16px;text-align:center;">
            <div style="font-size:16px;font-weight:900;color:var(--warning);word-break:break-all;font-family:'Pretendard',system-ui,sans-serif;">{{ korean_num(ns.total_amt) }}</div>
            <div style="font-size:13px;font-weight:700;color:var(--text-muted);margin-top:4px;font-family:'Pretendard',system-ui,sans-serif;">누적 피해</div>
        </div>
    </div>
    {% endif %}

    {# ════ 블랙리스트 관리 ════ #}
    {% if tab=='scammers' %}

    <!-- 일괄변경 모달 -->
    <div id="bulkUpdateModal" style="display:none;position:fixed;inset:0;z-index:999;background:rgba(5,7,15,0.82);backdrop-filter:blur(7px);align-items:center;justify-content:center;padding:20px;">
        <div style="width:100%;max-width:520px;background:var(--bg-surface);border-radius:20px;border:1px solid var(--border-color);box-shadow:0 24px 80px rgba(0,0,0,0.7);overflow:hidden;">
            <div style="padding:20px 24px;border-bottom:1px solid var(--border-color);display:flex;justify-content:space-between;align-items:center;background:rgba(255,202,94,0.05);">
                <h3 style="font-size:16px;display:flex;align-items:center;gap:8px;"><i class="fas fa-exchange-alt" style="color:var(--warning);"></i> 고유번호 + 닉네임 일괄변경</h3>
                <button onclick="document.getElementById('bulkUpdateModal').style.display='none'" style="background:rgba(255,255,255,0.07);border:none;cursor:pointer;width:32px;height:32px;border-radius:50%;color:var(--text-muted);font-size:16px;display:flex;align-items:center;justify-content:center;transition:all 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.12)';this.style.color='#fff'" onmouseout="this.style.background='rgba(255,255,255,0.07)';this.style.color='var(--text-muted)'"><i class="fas fa-times"></i></button>
            </div>
            <div style="padding:24px;display:flex;flex-direction:column;gap:16px;">
                <div style="background:rgba(255,202,94,0.06);border:1px solid rgba(255,202,94,0.2);border-radius:10px;padding:12px 14px;font-size:12px;color:var(--warning);line-height:1.6;">
                    <i class="fas fa-info-circle" style="margin-right:5px;"></i>
                    특정 고유번호를 가진 가해자의 <strong>고유번호와 닉네임</strong>을 한번에 변경합니다.
                </div>
                <form method="POST" action="/admin/bulk_update_scammer" style="display:flex;flex-direction:column;gap:12px;">
                    <div style="background:var(--bg-elevated);border-radius:10px;padding:14px;border:1px solid var(--border-color);">
                        <div style="font-size:11px;font-weight:700;color:var(--text-muted);margin-bottom:10px;letter-spacing:0.5px;text-transform:uppercase;">🔍 변경 대상</div>
                        <div style="display:flex;gap:10px;">
                            <div style="flex:1;">
                                <label style="display:block;font-size:11px;color:var(--text-muted);margin-bottom:5px;">현재 고유번호</label>
                                <input class="input" name="old_unique_id" placeholder="예: 12345" required style="padding:10px 12px;font-size:14px;">
                            </div>
                        </div>
                    </div>
                    <div style="background:var(--bg-elevated);border-radius:10px;padding:14px;border:1px solid rgba(91,159,255,0.2);">
                        <div style="font-size:11px;font-weight:700;color:var(--primary);margin-bottom:10px;letter-spacing:0.5px;text-transform:uppercase;">✏️ 변경 내용</div>
                        <div style="display:flex;flex-direction:column;gap:10px;">
                            <div>
                                <label style="display:block;font-size:11px;color:var(--text-muted);margin-bottom:5px;">새 고유번호 <span style="color:var(--text-muted);font-weight:400;">(변경 안 할 시 비워두세요)</span></label>
                                <input class="input" name="new_unique_id" placeholder="새 고유번호 (선택)" style="padding:10px 12px;font-size:14px;">
                            </div>
                            <div>
                                <label style="display:block;font-size:11px;color:var(--text-muted);margin-bottom:5px;">새 닉네임 <span style="color:var(--text-muted);font-weight:400;">(변경 안 할 시 비워두세요)</span></label>
                                <input class="input" name="new_name" placeholder="새 닉네임 (선택)" style="padding:10px 12px;font-size:14px;">
                            </div>
                        </div>
                    </div>
                    <div style="display:flex;gap:10px;margin-top:4px;">
                        <button type="submit" class="btn" style="flex:1;padding:13px;background:linear-gradient(135deg,var(--warning),#e0a800);color:#0d0f17;box-shadow:0 4px 14px var(--warning-glow);" onclick="return confirm('정말 일괄 변경합니까?')"><i class="fas fa-exchange-alt"></i> 일괄 변경 실행</button>
                        <button type="button" onclick="document.getElementById('bulkUpdateModal').style.display='none'" class="btn btn-outline" style="flex:1;padding:13px;">취소</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
    <script>
    document.getElementById('bulkUpdateModal').addEventListener('click', function(e){ if(e.target===this) this.style.display='none'; });
    </script>

    <!-- 수정 모달 -->
    <div id="editScammerModal" style="display:none;position:fixed;inset:0;z-index:999;background:rgba(5,7,15,0.8);backdrop-filter:blur(6px);align-items:center;justify-content:center;padding:20px;">
        <div style="width:100%;max-width:480px;background:var(--bg-surface);border-radius:20px;border:1px solid var(--border-color);box-shadow:0 24px 80px rgba(0,0,0,0.7);overflow:hidden;">
            <div style="padding:20px 24px;border-bottom:1px solid var(--border-color);display:flex;justify-content:space-between;align-items:center;background:rgba(91,159,255,0.05);">
                <h3 style="font-size:16px;display:flex;align-items:center;gap:8px;"><i class="fas fa-edit" style="color:var(--primary);"></i> 정보 수정</h3>
                <button onclick="closeEditScammer()" style="background:rgba(255,255,255,0.07);border:none;cursor:pointer;width:32px;height:32px;border-radius:50%;color:var(--text-muted);font-size:16px;display:flex;align-items:center;justify-content:center;transition:all 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.12)';this.style.color='#fff'" onmouseout="this.style.background='rgba(255,255,255,0.07)';this.style.color='var(--text-muted)'"><i class="fas fa-times"></i></button>
            </div>
            <form method="POST" action="{{ url_for('admin_scammer_edit') }}" style="padding:24px;display:flex;flex-direction:column;gap:14px;">
                <input type="hidden" name="record_id" id="editUid">
                <div>
                    <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;letter-spacing:0.5px;">고유번호 수정</label>
                    <input class="input" name="new_unique_id" id="editNewUid" placeholder="새 고유번호 (변경 안 할 시 비워두세요)" style="border-color:rgba(91,159,255,0.4);">
                    <div style="font-size:11px;color:var(--text-muted);margin-top:4px;"><i class="fas fa-info-circle"></i> 비워두면 기존 고유번호 유지</div>
                </div>
                <div>
                    <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;letter-spacing:0.5px;">닉네임</label>
                    <input class="input" name="name" id="editName" required>
                </div>
                <div>
                    <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;letter-spacing:0.5px;">카테고리</label>
                    <select class="input" name="category" id="editCategory" style="padding:10px 14px;" onchange="toggleItemField(this.value)">
                        <option value="아이템">아이템</option>
                        <option value="돈">돈</option>
                        <option value="아이템,돈">아이템+돈</option>
                    </select>
                </div>
                <div id="editItemNameWrap" style="display:none;">
                    <label style="display:block;font-size:12px;font-weight:700;color:var(--accent);margin-bottom:7px;letter-spacing:0.5px;">아이템 이름</label>
                    <input class="input" name="item_name" id="editItemName" placeholder="예: 전설 칼, 드래곤 방패 등" style="border-color:rgba(167,139,250,0.4);">
                </div>
                <div>
                    <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;letter-spacing:0.5px;">피해 금액</label>
                    <input class="input" name="amount" id="editAmount" placeholder="숫자만 입력" required oninput="updateAmountPreview(this,'editAmountPreview')">
                    <div id="editAmountPreview" style="font-size:12px;color:var(--primary);margin-top:4px;"></div>
                </div>
                <div>
                    <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;letter-spacing:0.5px;">관리자 메모 (비공개)</label>
                    <input class="input" name="admin_memo" id="editMemo" placeholder="선택">
                </div>
                <div style="display:flex;gap:10px;margin-top:6px;">
                    <button type="submit" class="btn" style="flex:1;padding:13px;"><i class="fas fa-save"></i> 저장</button>
                    <button type="button" onclick="closeEditScammer()" class="btn btn-outline" style="flex:1;padding:13px;">취소</button>
                </div>
            </form>
        </div>
    </div>
    <script>
    function openEditScammer(recordId, uid, name, amount, memo, category, itemName) {
        document.getElementById('editUid').value = recordId;
        document.getElementById('editNewUid').value = '';
        document.getElementById('editName').value = name;
        document.getElementById('editAmount').value = amount;
        document.getElementById('editMemo').value = memo || '';
        document.getElementById('editItemName').value = itemName || '';
        const sel = document.getElementById('editCategory');
        for(let i=0; i<sel.options.length; i++){
            if(sel.options[i].value === category) { sel.selectedIndex = i; break; }
        }
        toggleItemField(sel.value);
        document.getElementById('editScammerModal').style.display = 'flex';
    }
    function toggleItemField(cat) {
        const wrap = document.getElementById('editItemNameWrap');
        if (cat && cat.includes('아이템')) { wrap.style.display = 'block'; }
        else { wrap.style.display = 'none'; }
    }
    function closeEditScammer() { document.getElementById('editScammerModal').style.display = 'none'; }
    document.getElementById('editScammerModal').addEventListener('click', function(e){ if(e.target===this) closeEditScammer(); });
    function adminFilterList(q) {
        const rows = document.querySelectorAll('.admin-scammer-row');
        const term = q.toLowerCase().trim();
        let visible = 0;
        rows.forEach(row => {
            const match = !term || row.dataset.search.includes(term);
            row.style.display = match ? '' : 'none';
            if (match) visible++;
        });
        const cntEl = document.getElementById('adminListCount');
        if (cntEl) cntEl.textContent = term ? `검색 결과: ${visible}명` : '';
    }
    </script>

    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;flex-wrap:wrap;gap:10px;">
        <div>
            <h3 style="font-size:16px;margin-bottom:4px;font-family:'Pretendard',system-ui,sans-serif;">블랙리스트 전체 관리</h3>
            <p style="font-size:13px;color:var(--text-muted);font-family:'Pretendard',system-ui,sans-serif;">총 {{ distinct_scammer_count }}명 등록됨{% if not readonly_admin %} · 수정/삭제 가능{% endif %}</p>
        </div>
        {% if not readonly_admin %}
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <a href="?tab=add" style="display:inline-flex;align-items:center;gap:7px;padding:9px 18px;border-radius:10px;background:linear-gradient(135deg,var(--primary),#4a8ef0);color:#fff;font-size:13px;font-weight:700;text-decoration:none;box-shadow:0 4px 14px var(--primary-glow);transition:all 0.2s;font-family:'Pretendard',system-ui,sans-serif;">
                <i class="fas fa-plus"></i> 새로 등록
            </a>
            <button onclick="document.getElementById('bulkUpdateModal').style.display='flex'" style="display:inline-flex;align-items:center;gap:7px;padding:9px 18px;border-radius:10px;background:rgba(255,202,94,0.12);border:1px solid rgba(255,202,94,0.3);color:var(--warning);font-size:13px;font-weight:700;cursor:pointer;transition:all 0.2s;font-family:'Pretendard',system-ui,sans-serif;" onmouseover="this.style.background='rgba(255,202,94,0.2)'" onmouseout="this.style.background='rgba(255,202,94,0.12)'">
                <i class="fas fa-exchange-alt"></i> 일괄 변경
            </button>
            <form method="POST" action="{{ url_for('admin_scammer_delete_all') }}" onsubmit="return confirm('블랙리스트 전체 ' + {{ all_scammers|length }} + '명을 삭제합니까? 되돌릴 수 없습니다!')">
                <button type="submit" style="display:none;"></button>
            </form>
        </div>
        {% endif %}
    </div>
    <!-- 실시간 검색 필터 -->
    <div style="margin-bottom:14px;position:relative;z-index:1;">
        <i class="fas fa-search" style="position:absolute;left:14px;top:50%;transform:translateY(-50%);color:var(--text-muted);font-size:13px;pointer-events:none;"></i>
        <input id="adminSearchInput" type="text" placeholder="닉네임 또는 고유번호로 빠른 검색..." oninput="adminFilterList(this.value)"
            style="width:100%;box-sizing:border-box;padding:12px 14px 12px 40px;border-radius:10px;border:1px solid var(--border-color);background:var(--bg-elevated);color:#fff;font-size:14px;outline:none;transition:border-color 0.2s;"
            onfocus="this.style.borderColor='var(--primary)'"
            onblur="this.style.borderColor='var(--border-color)'">
    </div>
    <div id="adminListCount" style="font-size:13px;color:var(--text-muted);margin-bottom:10px;"></div>
    <div style="overflow-x:auto;border-radius:12px;border:1px solid var(--border-color);max-width:100%;">
    <table style="width:100%;border-collapse:collapse;font-family:'Pretendard',system-ui,sans-serif;">
        <thead>
            <tr style="background:var(--bg-elevated);">
                <th style="padding:12px 14px;text-align:left;font-size:12px;font-weight:700;color:var(--text-muted);border-bottom:1px solid var(--border-color);white-space:nowrap;">고유번호</th>
                <th style="padding:12px 14px;text-align:left;font-size:12px;font-weight:700;color:var(--text-muted);border-bottom:1px solid var(--border-color);">닉네임</th>
                <th style="padding:12px 14px;text-align:left;font-size:12px;font-weight:700;color:var(--text-muted);border-bottom:1px solid var(--border-color);">피해자</th>
                <th style="padding:12px 14px;text-align:left;font-size:12px;font-weight:700;color:var(--text-muted);border-bottom:1px solid var(--border-color);">카테고리</th>
                <th style="padding:12px 14px;text-align:right;font-size:12px;font-weight:700;color:var(--text-muted);border-bottom:1px solid var(--border-color);white-space:nowrap;">피해금액</th>
                <th style="padding:12px 14px;text-align:left;font-size:12px;font-weight:700;color:var(--text-muted);border-bottom:1px solid var(--border-color);white-space:nowrap;">등록일</th>
                {% if not readonly_admin %}
                <th style="padding:12px 14px;text-align:center;font-size:12px;font-weight:700;color:var(--text-muted);border-bottom:1px solid var(--border-color);">관리</th>
                {% endif %}
            </tr>
        </thead>
        <tbody>
        {% for s in all_scammers %}
        <tr class="admin-scammer-row" data-search="{{ s.name|lower }} {{ s.unique_id }}"
            style="border-bottom:1px solid var(--border-color);transition:background 0.15s;"
            onmouseover="this.style.background='rgba(255,94,122,0.04)'" onmouseout="this.style.background=''">
            <td style="padding:12px 14px;white-space:nowrap;">
                <span style="font-size:13px;font-weight:800;color:var(--primary);background:rgba(91,159,255,0.1);padding:2px 8px;border-radius:5px;font-family:'Pretendard',system-ui,sans-serif;">{{ s.unique_id }}번</span>
            </td>
            <td style="padding:12px 14px;">
                <div style="font-size:14px;font-weight:800;color:#fff;font-family:'Pretendard',system-ui,sans-serif;">{{ s.name }}</div>
                {% if s.admin_memo %}<div style="font-size:11px;color:var(--warning);margin-top:2px;">📝 {{ s.admin_memo[:25] }}{% if s.admin_memo|length > 25 %}…{% endif %}</div>{% endif %}
            </td>
            <td style="padding:12px 14px;">
                {% if s.victim_name or s.victim_id %}
                <div style="font-size:13px;font-weight:700;color:rgba(255,255,255,0.8);font-family:'Pretendard',system-ui,sans-serif;">{{ s.victim_name or '-' }}</div>
                {% if s.victim_id %}<div style="font-size:11px;color:var(--text-muted);font-family:'Pretendard',system-ui,sans-serif;">{{ s.victim_id }}번</div>{% endif %}
                {% else %}<span style="font-size:12px;color:var(--text-muted);">-</span>{% endif %}
            </td>
            <td style="padding:12px 14px;">
                {% if s.category %}<span style="font-size:12px;color:var(--accent);background:rgba(167,139,250,0.1);padding:2px 8px;border-radius:5px;font-family:'Pretendard',system-ui,sans-serif;">{{ s.category }}</span>{% endif %}
                {% if s.item_name %}<div style="font-size:11px;color:#a78bfa;margin-top:3px;font-family:'Pretendard',system-ui,sans-serif;">📦 {{ s.item_name }}</div>{% endif %}
            </td>
            <td style="padding:12px 14px;text-align:right;white-space:nowrap;">
                <div style="font-size:14px;font-weight:800;color:var(--danger);font-family:'Pretendard',system-ui,sans-serif;">{{ s.amount_display }}</div>
                <div style="font-size:11px;color:var(--text-muted);font-family:'Pretendard',system-ui,sans-serif;">({{ korean_num(s.amount_int) }})</div>
            </td>
            <td style="padding:12px 14px;white-space:nowrap;">
                <span style="font-size:12px;color:var(--text-muted);font-family:'Pretendard',system-ui,sans-serif;">{{ s.date[:10] }}</span>
            </td>
            {% if not readonly_admin %}
            <td style="padding:12px 14px;text-align:center;white-space:nowrap;">
                <div style="display:flex;gap:5px;justify-content:center;">
                    <button onclick="openEditScammer('{{ s.id }}', '{{ s.unique_id }}', '{{ s.name|replace("'","\\'")|replace('"','\\"') }}', '{{ s.amount_int }}', '{{ s.admin_memo|replace("'","\\'")|replace('"','\\"') }}', '{{ s.category|replace("'","\\'")|replace('"','\\"') }}', '{{ (s.item_name or '')|replace("'","\\'")|replace('"','\\"') }}')" style="padding:6px 12px;border-radius:7px;background:rgba(91,159,255,0.1);border:1px solid rgba(91,159,255,0.25);color:var(--primary);font-size:12px;font-weight:700;cursor:pointer;transition:all 0.2s;white-space:nowrap;" onmouseover="this.style.background='rgba(91,159,255,0.2)'" onmouseout="this.style.background='rgba(91,159,255,0.1)'">
                        <i class="fas fa-edit" style="font-size:11px;"></i>
                    </button>
                    <form method="POST" action="{{ url_for('admin_scammer_delete') }}" onsubmit="return confirm('이 사건을 삭제합니까?')" style="display:inline;">
                        <input type="hidden" name="record_id" value="{{ s.id }}">
                        <button type="submit" style="padding:6px 12px;border-radius:7px;background:rgba(255,94,122,0.1);border:1px solid rgba(255,94,122,0.25);color:var(--danger);font-size:12px;font-weight:700;cursor:pointer;transition:all 0.2s;" onmouseover="this.style.background='rgba(255,94,122,0.2)'" onmouseout="this.style.background='rgba(255,94,122,0.1)'">
                            <i class="fas fa-trash" style="font-size:11px;"></i>
                        </button>
                    </form>
                </div>
            </td>
            {% endif %}
        </tr>
        {% else %}
        <tr><td colspan="7" style="padding:60px 20px;text-align:center;color:var(--text-muted);">
            <div style="font-size:44px;margin-bottom:12px;">🎉</div>
            <p>등록된 블랙리스트가 없습니다.</p>
        </td></tr>
        {% endfor %}
        </tbody>
    </table>
    </div>

    {# ════ 공지 관리 ════ #}
    {% elif tab=='notices' %}

    <!-- 공지 수정 모달 -->
    <div id="editNoticeModal" style="display:none;position:fixed;inset:0;z-index:999;background:rgba(5,7,15,0.8);backdrop-filter:blur(6px);align-items:center;justify-content:center;padding:20px;">
        <div style="width:100%;max-width:540px;background:var(--bg-surface);border-radius:20px;border:1px solid var(--border-color);box-shadow:0 24px 80px rgba(0,0,0,0.7);overflow:hidden;">
            <div style="padding:20px 24px;border-bottom:1px solid var(--border-color);display:flex;justify-content:space-between;align-items:center;background:rgba(167,139,250,0.05);">
                <h3 style="font-size:16px;display:flex;align-items:center;gap:8px;"><i class="fas fa-edit" style="color:var(--accent);"></i> 공지 수정</h3>
                <button onclick="closeEditNotice()" style="background:rgba(255,255,255,0.07);border:none;cursor:pointer;width:32px;height:32px;border-radius:50%;color:var(--text-muted);font-size:16px;display:flex;align-items:center;justify-content:center;transition:all 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.12)';this.style.color='#fff'" onmouseout="this.style.background='rgba(255,255,255,0.07)';this.style.color='var(--text-muted)'"><i class="fas fa-times"></i></button>
            </div>
            <form method="POST" action="{{ url_for('admin_notice_edit') }}" style="padding:24px;display:flex;flex-direction:column;gap:14px;">
                <input type="hidden" name="notice_id" id="editNid">
                <div>
                    <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;letter-spacing:0.5px;">유형</label>
                    <select class="input" name="notice_type" id="editNType" style="padding:10px 14px;">
                        <option value="공지">📢 공지</option>
                        <option value="패치노트">🔧 패치노트</option>
                    </select>
                </div>
                <div>
                    <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;letter-spacing:0.5px;">제목</label>
                    <input class="input" name="title" id="editNTitle" required>
                </div>
                <div>
                    <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;letter-spacing:0.5px;">내용</label>
                    <textarea class="input" name="content" id="editNContent" required style="min-height:140px;"></textarea>
                </div>
                <div style="display:flex;gap:10px;margin-top:6px;">
                    <button type="submit" class="btn" style="flex:1;padding:13px;background:linear-gradient(135deg,var(--accent),#8b6fda);box-shadow:0 4px 14px var(--accent-glow);"><i class="fas fa-save"></i> 저장</button>
                    <button type="button" onclick="closeEditNotice()" class="btn btn-outline" style="flex:1;padding:13px;">취소</button>
                </div>
            </form>
        </div>
    </div>
    <script>
    function openEditNoticeFromBtn(btn) {
        document.getElementById('editNid').value = btn.dataset.nid;
        document.getElementById('editNTitle').value = btn.dataset.ntitle;
        document.getElementById('editNContent').value = btn.dataset.ncontent;
        const sel = document.getElementById('editNType');
        const type = btn.dataset.ntype;
        for(let i=0; i<sel.options.length; i++){
            if(sel.options[i].value === type) { sel.selectedIndex = i; break; }
        }
        document.getElementById('editNoticeModal').style.display = 'flex';
    }
    function openEditNotice(nid, type, title, content) {
        document.getElementById('editNid').value = nid;
        document.getElementById('editNTitle').value = title;
        document.getElementById('editNContent').value = content;
        const sel = document.getElementById('editNType');
        for(let i=0; i<sel.options.length; i++){
            if(sel.options[i].value === type) { sel.selectedIndex = i; break; }
        }
        document.getElementById('editNoticeModal').style.display = 'flex';
    }
    function closeEditNotice() { document.getElementById('editNoticeModal').style.display = 'none'; }
    document.getElementById('editNoticeModal').addEventListener('click', function(e){ if(e.target===this) closeEditNotice(); });
    </script>

    <div style="display:grid;grid-template-columns:340px 1fr;gap:20px;align-items:start;">
        <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:16px;overflow:hidden;box-shadow:var(--card-shadow);position:sticky;top:80px;">
            <div style="padding:16px 20px;border-bottom:1px solid var(--border-color);background:rgba(167,139,250,0.05);display:flex;align-items:center;gap:10px;">
                <i class="fas fa-plus-circle" style="color:var(--accent);font-size:14px;"></i>
                <h3 style="font-size:15px;">새 글 작성</h3>
            </div>
            <div style="padding:20px;">
                <form method="POST" action="{{ url_for('admin_notice_add') }}" style="display:flex;flex-direction:column;gap:12px;">
                    <select class="input" name="notice_type" style="padding:10px 14px;">
                        <option value="공지">📢 공지</option>
                        <option value="패치노트">🔧 패치노트</option>
                    </select>
                    <input class="input" name="title" placeholder="제목" required>
                    <textarea class="input" name="content" placeholder="내용을 입력하세요." required style="min-height:120px;"></textarea>
                    <button class="btn" type="submit" style="background:linear-gradient(135deg,var(--accent),#8b6fda);box-shadow:0 4px 14px var(--accent-glow);"><i class="fas fa-paper-plane"></i> 등록</button>
                </form>
            </div>
        </div>
        <div>
            <p style="font-size:13px;color:var(--text-muted);margin-bottom:14px;">총 {{ all_notices|length }}개</p>
            <div style="display:flex;flex-direction:column;gap:10px;">
                {% for n in all_notices %}
                <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:14px;overflow:hidden;transition:border-color 0.2s;" onmouseover="this.style.borderColor='rgba(167,139,250,0.3)'" onmouseout="this.style.borderColor='var(--border-color)'">
                    <div style="padding:14px 18px;display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid var(--border-color);background:rgba(167,139,250,0.04);flex-wrap:wrap;">
                        <div style="display:flex;align-items:center;gap:10px;flex:1;min-width:0;">
                            <span style="font-size:11px;background:rgba(167,139,250,0.15);color:var(--accent);padding:2px 8px;border-radius:6px;white-space:nowrap;">{{ '📢 공지' if n.notice_type == '공지' else '🔧 패치노트' }}</span>
                            <span style="font-size:14px;font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ n.title }}</span>
                        </div>
                        <div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">
                            <span style="font-size:11px;color:var(--text-muted);background:var(--bg-elevated);padding:2px 9px;border-radius:20px;">{{ n.created_at[:10] }}</span>
                            <button
                                data-nid="{{ n.id }}"
                                data-ntype="{{ n.notice_type|e }}"
                                data-ntitle="{{ n.title|e }}"
                                data-ncontent="{{ n.content|e }}"
                                onclick="openEditNoticeFromBtn(this)"
                                style="padding:6px 12px;border-radius:7px;background:rgba(91,159,255,0.1);border:1px solid rgba(91,159,255,0.25);color:var(--primary);font-size:12px;font-weight:700;cursor:pointer;transition:all 0.2s;display:flex;align-items:center;gap:5px;" onmouseover="this.style.background='rgba(91,159,255,0.2)'" onmouseout="this.style.background='rgba(91,159,255,0.1)'"><i class="fas fa-edit" style="font-size:10px;"></i>수정</button>
                            <form method="POST" action="{{ url_for('admin_notice_delete') }}" onsubmit="return confirm('이 글을 삭제합니까?')" style="display:inline;">
                                <input type="hidden" name="notice_id" value="{{ n.id }}">
                                <button type="submit" style="padding:6px 12px;border-radius:7px;background:rgba(255,94,122,0.1);border:1px solid rgba(255,94,122,0.25);color:var(--danger);font-size:12px;font-weight:700;cursor:pointer;transition:all 0.2s;display:flex;align-items:center;gap:5px;" onmouseover="this.style.background='rgba(255,94,122,0.2)'" onmouseout="this.style.background='rgba(255,94,122,0.1)'"><i class="fas fa-trash" style="font-size:10px;"></i>삭제</button>
                            </form>
                        </div>
                    </div>
                    <div style="padding:14px 18px;font-size:13px;color:var(--text-muted);line-height:1.6;white-space:pre-wrap;max-height:80px;overflow:hidden;text-overflow:ellipsis;">{{ n.content }}</div>
                </div>
                {% else %}
                <div style="text-align:center;padding:60px 20px;background:var(--bg-surface);border-radius:16px;border:1px solid var(--border-color);">
                    <div style="font-size:44px;margin-bottom:12px;">📢</div>
                    <p style="color:var(--text-muted);">등록된 글이 없습니다.</p>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>

    {# ════ 후원의 전당 관리 ════ #}
    {% elif tab=='hof_admin' %}

    <!-- 후원의 전당 수정 모달 -->
    <div id="editHofModal" style="display:none;position:fixed;inset:0;z-index:999;background:rgba(5,7,15,0.8);backdrop-filter:blur(6px);align-items:center;justify-content:center;padding:20px;">
        <div style="width:100%;max-width:480px;background:var(--bg-surface);border-radius:20px;border:1px solid var(--border-color);box-shadow:0 24px 80px rgba(0,0,0,0.7);overflow:hidden;">
            <div style="padding:20px 24px;border-bottom:1px solid var(--border-color);display:flex;justify-content:space-between;align-items:center;background:rgba(167,139,250,0.05);">
                <h3 style="font-size:16px;display:flex;align-items:center;gap:8px;font-family:'Pretendard',system-ui,sans-serif;"><i class="fas fa-edit" style="color:var(--accent);"></i> 후원자 수정</h3>
                <button onclick="closeEditHof()" style="background:rgba(255,255,255,0.07);border:none;cursor:pointer;width:32px;height:32px;border-radius:50%;color:var(--text-muted);font-size:16px;display:flex;align-items:center;justify-content:center;transition:all 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.12)';this.style.color='#fff'" onmouseout="this.style.background='rgba(255,255,255,0.07)';this.style.color='var(--text-muted)'"><i class="fas fa-times"></i></button>
            </div>
            <form method="POST" action="{{ url_for('admin_hof_edit') }}" style="padding:24px;display:flex;flex-direction:column;gap:14px;">
                <input type="hidden" name="hof_id" id="editHofId">
                <div>
                    <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;font-family:'Pretendard',system-ui,sans-serif;">이름</label>
                    <input class="input" name="name" id="editHofName" required>
                </div>
                <div>
                    <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;font-family:'Pretendard',system-ui,sans-serif;">뱃지 (이모지)</label>
                    <input class="input" name="badge" id="editHofBadge" placeholder="💝">
                </div>
                <div>
                    <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;font-family:'Pretendard',system-ui,sans-serif;">후원 금액 (숫자만)</label>
                    <input class="input" name="amount" id="editHofAmount" placeholder="예: 100000" type="text" oninput="updateHofPreview(this,'editHofPreview')">
                    <div id="editHofPreview" style="font-size:12px;color:var(--accent);margin-top:4px;font-family:'Pretendard',system-ui,sans-serif;"></div>
                </div>
                <div>
                    <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;font-family:'Pretendard',system-ui,sans-serif;">한마디</label>
                    <input class="input" name="description" id="editHofDesc" placeholder="선택">
                </div>
                <div style="display:flex;gap:10px;margin-top:6px;">
                    <button type="submit" class="btn" style="flex:1;padding:13px;background:linear-gradient(135deg,var(--accent),#8b6fda);box-shadow:0 4px 14px var(--accent-glow);font-family:'Pretendard',system-ui,sans-serif;"><i class="fas fa-save"></i> 저장</button>
                    <button type="button" onclick="closeEditHof()" class="btn btn-outline" style="flex:1;padding:13px;font-family:'Pretendard',system-ui,sans-serif;">취소</button>
                </div>
            </form>
        </div>
    </div>
    <script>
    function updateHofPreview(input, previewId) {
        const val = input.value.replace(/[^0-9]/g,'');
        const preview = document.getElementById(previewId);
        if (!preview) return;
        if (!val || parseInt(val) === 0) { preview.textContent = ''; return; }
        const n = parseInt(val);
        let jo   = Math.floor(n / 1000000000000);
        let uk   = Math.floor((n % 1000000000000) / 100000000);
        let man  = Math.floor((n % 100000000) / 10000);
        let rem  = n % 10000;
        let parts = [];
        if (jo)  parts.push(jo + '조');
        if (uk)  parts.push(uk + '억');
        if (man) parts.push(man + '만');
        if (rem) parts.push(rem.toLocaleString());
        preview.textContent = '→ ' + n.toLocaleString() + '원 (' + (parts.join('') || n) + '원)';
    }
    // data-* 속성에서 읽어서 모달 열기 (따옴표 등 특수문자 안전 처리)
    function openEditHofFromBtn(btn) {
        var id    = btn.getAttribute('data-id');
        var name  = btn.getAttribute('data-name');
        var badge = btn.getAttribute('data-badge');
        var amt   = btn.getAttribute('data-amount-int');
        var desc  = btn.getAttribute('data-desc');
        document.getElementById('editHofId').value    = id;
        document.getElementById('editHofName').value  = name || '';
        document.getElementById('editHofBadge').value = badge || '';
        document.getElementById('editHofAmount').value = amt || '';
        document.getElementById('editHofDesc').value  = desc || '';
        var amountEl = document.getElementById('editHofAmount');
        updateHofPreview(amountEl, 'editHofPreview');
        document.getElementById('editHofModal').style.display = 'flex';
    }
    function closeEditHof() { document.getElementById('editHofModal').style.display = 'none'; }
    (function(){ var m = document.getElementById('editHofModal'); if(m) m.addEventListener('click', function(e){ if(e.target===this) closeEditHof(); }); })();
    function addHofFill(v) {
        var el = document.getElementById('addHofAmount');
        el.value = (parseInt(el.value.replace(/[^0-9]/g,'') || '0') + v).toString();
        updateHofPreview(el, 'addHofPreview');
    }
    </script>

    {% if total_hof_amount and total_hof_amount > 0 %}
    <div style="background:linear-gradient(135deg,rgba(167,139,250,0.18),rgba(91,159,255,0.12));border:2px solid rgba(167,139,250,0.45);border-radius:14px;padding:14px 20px;margin-bottom:18px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;box-shadow:0 0 24px rgba(167,139,250,0.12);">
        <span style="font-size:13px;font-weight:700;color:var(--accent);font-family:'Pretendard',system-ui,sans-serif;">💜 총 누적 후원금액</span>
        <span style="font-size:20px;font-weight:900;color:#fff;font-family:'Pretendard',system-ui,sans-serif;">{{ korean_hof(total_hof_amount) }}</span>
    </div>
    {% endif %}

    <div style="display:grid;grid-template-columns:340px 1fr;gap:20px;align-items:start;">
        <!-- 새 후원자 등록 -->
        <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:16px;overflow:hidden;box-shadow:var(--card-shadow);position:sticky;top:80px;">
            <div style="padding:16px 20px;border-bottom:1px solid var(--border-color);background:rgba(167,139,250,0.05);display:flex;align-items:center;gap:10px;">
                <i class="fas fa-heart" style="color:var(--accent);font-size:14px;"></i>
                <h3 style="font-size:15px;font-family:'Pretendard',system-ui,sans-serif;">후원자 등록</h3>
            </div>
            <div style="padding:20px;">
                <form method="POST" action="{{ url_for('admin_hof_add') }}" style="display:flex;flex-direction:column;gap:12px;">
                    <input class="input" name="name" placeholder="닉네임 *" required>
                    <input class="input" name="badge" placeholder="뱃지 이모지 (예: 💝)">
                    <div>
                        <input class="input" name="amount" id="addHofAmount" placeholder="후원 금액 (숫자만, 예: 100000)" type="text" oninput="updateHofPreview(this,'addHofPreview')">
                        <div id="addHofPreview" style="font-size:12px;color:var(--accent);margin-top:4px;"></div>
                    </div>
                    <input class="input" name="description" placeholder="한마디 (선택)">
                    <button class="btn" type="submit" style="background:linear-gradient(135deg,var(--accent),#8b6fda);box-shadow:0 4px 14px var(--accent-glow);font-family:'Pretendard',system-ui,sans-serif;"><i class="fas fa-heart"></i> 등록</button>
                </form>
            </div>
        </div>
        <!-- 후원자 목록 -->
        <div>
            <p style="font-size:13px;color:var(--text-muted);margin-bottom:14px;font-family:'Pretendard',system-ui,sans-serif;">총 {{ all_hof|length }}명</p>
            <div style="display:flex;flex-direction:column;gap:10px;">
                {% for h in all_hof %}
                <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:14px;padding:14px 18px;display:flex;align-items:center;gap:14px;transition:border-color 0.2s;" onmouseover="this.style.borderColor='rgba(167,139,250,0.3)'" onmouseout="this.style.borderColor='var(--border-color)'">
                    <div style="font-size:24px;flex-shrink:0;">{{ h.badge or '💝' }}</div>
                    <div style="flex:1;min-width:0;">
                        <div style="font-size:14px;font-weight:800;color:#fff;font-family:'Pretendard',system-ui,sans-serif;">{{ h.name }}</div>
                        {% if h.description %}<div style="font-size:12px;color:var(--text-muted);font-family:'Pretendard',system-ui,sans-serif;">{{ h.description }}</div>{% endif %}
                    </div>
                    {% if h.amount %}<div style="font-size:14px;font-weight:800;color:var(--accent);white-space:nowrap;font-family:'Pretendard',system-ui,sans-serif;">{{ h.amount }}</div>{% endif %}
                    <div style="display:flex;gap:6px;flex-shrink:0;">
                        <button type="button"
                            onclick="openEditHofFromBtn(this)"
                            data-id="{{ h.id }}"
                            data-name="{{ h.name | e }}"
                            data-badge="{{ h.badge | e }}"
                            data-amount-int="{{ h.amount_int or 0 }}"
                            data-desc="{{ h.description | e }}"
                            style="padding:6px 12px;border-radius:7px;background:rgba(91,159,255,0.1);border:1px solid rgba(91,159,255,0.25);color:var(--primary);font-size:12px;font-weight:700;cursor:pointer;transition:all 0.2s;display:flex;align-items:center;gap:5px;font-family:'Pretendard',system-ui,sans-serif;"
                            onmouseover="this.style.background='rgba(91,159,255,0.2)'"
                            onmouseout="this.style.background='rgba(91,159,255,0.1)'"
                        ><i class="fas fa-edit" style="font-size:10px;"></i>수정</button>
                        <form method="POST" action="{{ url_for('admin_hof_delete') }}" onsubmit="return confirm('삭제합니까?')" style="display:inline;">
                            <input type="hidden" name="hof_id" value="{{ h.id }}">
                            <button type="submit" style="padding:6px 12px;border-radius:7px;background:rgba(255,94,122,0.1);border:1px solid rgba(255,94,122,0.25);color:var(--danger);font-size:12px;font-weight:700;cursor:pointer;transition:all 0.2s;display:flex;align-items:center;gap:5px;font-family:'Pretendard',system-ui,sans-serif;" onmouseover="this.style.background='rgba(255,94,122,0.2)'" onmouseout="this.style.background='rgba(255,94,122,0.1)'"><i class="fas fa-trash" style="font-size:10px;"></i>삭제</button>
                        </form>
                    </div>
                </div>
                {% else %}
                <div style="text-align:center;padding:60px 20px;background:var(--bg-surface);border-radius:16px;border:1px solid var(--border-color);">
                    <div style="font-size:44px;margin-bottom:12px;">💝</div>
                    <p style="color:var(--text-muted);font-family:'Pretendard',system-ui,sans-serif;">등록된 후원자가 없습니다.</p>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>

    {# ════ 수동 등록 ════ #}
    {% elif tab=='add' %}
    <div style="max-width:560px;">
        <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:16px;overflow:hidden;box-shadow:var(--card-shadow);">
            <div style="padding:16px 22px;border-bottom:1px solid var(--border-color);background:rgba(91,159,255,0.04);display:flex;align-items:center;gap:10px;">
                <i class="fas fa-user-plus" style="color:var(--primary);font-size:14px;"></i>
                <h3 style="font-size:15px;">블랙리스트 수동 등록</h3>
            </div>
            <div style="padding:22px;">
                <form method="POST" action="{{ url_for('admin_register') }}" style="display:flex;flex-direction:column;gap:12px;">
                    <div>
                        <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;">가해자 고유번호 *</label>
                        <input class="input" name="unique_id" placeholder="가해자 고유번호" required>
                    </div>
                    <div>
                        <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;">가해자 닉네임 *</label>
                        <input class="input" name="name" placeholder="가해자 닉네임" required>
                    </div>
                    <div style="border-top:1px solid rgba(255,94,122,0.2);padding-top:12px;">
                        <div style="display:flex;align-items:center;gap:6px;margin-bottom:10px;">
                            <i class="fas fa-user-shield" style="color:var(--danger);font-size:12px;"></i>
                            <span style="font-size:12px;font-weight:700;color:var(--danger);">피해자 정보</span>
                        </div>
                        <div style="display:flex;flex-direction:column;gap:10px;">
                            <div>
                                <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;">피해자 고유번호 *</label>
                                <input class="input" name="victim_id" placeholder="피해자 고유번호" required>
                            </div>
                            <div>
                                <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;">피해자 닉네임 *</label>
                                <input class="input" name="victim_name" placeholder="피해자 닉네임" required>
                            </div>
                        </div>
                    </div>
                    <div>
                        <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;">카테고리 *</label>
                        <div style="display:flex;gap:8px;flex-wrap:wrap;">
                            <label id="lblCatItem" style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:8px 16px;background:var(--bg-elevated);border:1.5px solid var(--border-color);border-radius:8px;font-size:13px;transition:all 0.2s;">
                                <input type="checkbox" name="cat_item" id="addCatItem" value="1" style="width:14px;height:14px;" onchange="onCategoryChange()"> 📦 아이템
                            </label>
                            <label id="lblCatMoney" style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:8px 16px;background:var(--bg-elevated);border:1.5px solid var(--border-color);border-radius:8px;font-size:13px;transition:all 0.2s;">
                                <input type="checkbox" name="cat_money" id="addCatMoney" value="1" style="width:14px;height:14px;" onchange="onCategoryChange()"> 💰 돈
                            </label>
                        </div>
                    </div>
                    <div id="addItemNameWrap" style="display:none;">
                        <label style="display:block;font-size:12px;font-weight:700;color:var(--accent);margin-bottom:7px;">📦 아이템 이름 *</label>
                        <input class="input" name="item_name" id="addItemName" placeholder="예: 전설 칼, 드래곤 방패 등" style="border-color:rgba(167,139,250,0.4);">
                    </div>
                    <div id="addAmountWrap" style="display:none;">
                        <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;">💰 피해액 *</label>
                        <input class="input" name="amount" id="addAmount" placeholder="피해액 (숫자만)" oninput="updateAmountPreview(this,'amountPreviewAdd')">
                        <div id="amountPreviewAdd" style="font-size:12px;color:var(--primary);margin-top:4px;"></div>
                    </div>
                    <script>
                    function onCategoryChange() {
                        var hasItem = document.getElementById('addCatItem').checked;
                        var hasMoney = document.getElementById('addCatMoney').checked;
                        document.getElementById('addItemNameWrap').style.display = hasItem ? 'block' : 'none';
                        document.getElementById('addAmountWrap').style.display = hasMoney ? 'block' : 'none';
                        document.getElementById('lblCatItem').style.borderColor = hasItem ? '#a78bfa' : 'var(--border-color)';
                        document.getElementById('lblCatMoney').style.borderColor = hasMoney ? 'var(--success)' : 'var(--border-color)';
                    }
                    </script>
                    <div>
                        <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;">사유 *</label>
                        <textarea class="input" name="reason" placeholder="블랙리스트 사유를 자세히 입력하세요." required style="min-height:100px;"></textarea>
                    </div>
                    <div>
                        <label style="display:block;font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:7px;">관리자 메모 (비공개, 선택)</label>
                        <input class="input" name="admin_memo" placeholder="관리자 메모">
                    </div>
                    <button class="btn" type="submit" style="margin-top:4px;"><i class="fas fa-plus"></i> 등록</button>
                </form>
            </div>
        </div>
    </div>

    {# ════ 감사 로그 ════ #}
    {% elif tab=='logs' %}
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px;">
        <div>
            <h3 style="font-size:16px;margin-bottom:4px;">감사 로그</h3>
            <p style="font-size:13px;color:var(--text-muted);">관리자 활동 전체 기록 · 최근 200건</p>
        </div>
        <form method="POST" action="{{ url_for('admin_clear_logs') }}" onsubmit="return confirm('감사 로그를 전체 삭제합니까?')">
            <button type="submit" style="padding:9px 16px;border-radius:9px;background:rgba(255,94,122,0.1);border:1px solid rgba(255,94,122,0.3);color:var(--danger);font-size:13px;font-weight:600;cursor:pointer;"><i class="fas fa-trash"></i> 로그 초기화</button>
        </form>
    </div>
    <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:16px;overflow:hidden;box-shadow:var(--card-shadow);">
        {% if audit_logs %}
        <div class="table-wrapper">
            <table class="table">
                <thead><tr><th>시간</th><th>관리자 ID</th><th>액션</th><th>대상</th></tr></thead>
                <tbody>
                    {% for log in audit_logs %}
                    <tr>
                        <td style="font-size:12px;color:var(--text-muted);white-space:nowrap;">{{ log.timestamp }}</td>
                        <td style="font-family:'Pretendard',system-ui,sans-serif;font-size:12px;color:var(--primary);">{{ log.admin_id }}</td>
                        <td style="font-size:13px;font-weight:600;color:#fff;">{{ log.action }}</td>
                        <td style="font-size:12px;color:var(--text-muted);">{{ log.target_info or '—' }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <div style="text-align:center;padding:60px 20px;color:var(--text-muted);">
            <div style="font-size:44px;margin-bottom:12px;">📜</div>
            <p>감사 로그가 없습니다.</p>
        </div>
        {% endif %}
    </div>

    {% endif %}{# end admin tab #}

    {# ════ 설정 ════ #}
    {% if tab=='settings' %}
    <div style="max-width:480px;">
        <div style="background:var(--bg-surface);border:1px solid var(--border-color);border-radius:16px;overflow:hidden;box-shadow:var(--card-shadow);">
            <div style="padding:16px 22px;border-bottom:1px solid var(--border-color);background:rgba(91,159,255,0.04);display:flex;align-items:center;gap:10px;">
                <i class="fas fa-key" style="color:var(--primary);font-size:14px;"></i>
                <h3 style="font-size:15px;font-family:'Pretendard',system-ui,sans-serif;">입장코드 변경</h3>
            </div>
            <div style="padding:22px;">
                {% if not readonly_admin %}
                <form method="POST" action="{{ url_for('admin_change_password') }}" style="display:flex;flex-direction:column;gap:14px;">
                    <div>
                        <label style="display:block;font-size:13px;font-weight:600;color:var(--text-muted);margin-bottom:8px;font-family:'Pretendard',system-ui,sans-serif;">새 입장코드 <span style="color:var(--danger);">*</span></label>
                        <input class="input" name="new_password" type="text" placeholder="새 입장코드 (4자리 이상)" required minlength="4" autocomplete="off">
                    </div>
                    <div style="background:rgba(255,202,94,0.06);border:1px solid rgba(255,202,94,0.2);border-radius:10px;padding:12px 14px;font-size:12px;color:var(--warning);font-family:'Pretendard',system-ui,sans-serif;">
                        <i class="fas fa-info-circle" style="margin-right:5px;"></i>변경 후 기존 사용자는 새 코드로 재입장해야 합니다.
                    </div>
                    <button class="btn" type="submit" onclick="return confirm('입장코드를 변경합니까?')"><i class="fas fa-save"></i> 변경 저장</button>
                </form>
                {% else %}
                <div style="text-align:center;padding:30px;color:var(--text-muted);font-family:'Pretendard',system-ui,sans-serif;">
                    <i class="fas fa-lock" style="font-size:32px;margin-bottom:12px;opacity:0.5;"></i>
                    <p>조회 전용 계정은 설정을 변경할 수 없습니다.</p>
                </div>
                {% endif %}
            </div>
        </div>
    </div>
    {% endif %}{# end settings #}

{% endif %}{# end page #}
</main>
</body>
</html>
"""

# ==========================================
# 🚀 Routes
# ==========================================

@app.before_request
def make_session_permanent():
    session.permanent = True

# ── 로그인 (비밀번호 방식) ──
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw == get_login_password():
            session["user"] = {
                "id": "guest",
                "username": "방문자",
                "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png"
            }
            return redirect(url_for("index"))
        else:
            error = "비밀번호가 올바르지 않습니다."
    return render_template_string(LOGIN_TEMPLATE, auth_url=discord_auth_url(), logo_url=LOGO_URL, error=error)

@app.route("/admin/view_as_user")
def admin_view_as_user():
    user = session.get("user")
    if not is_admin(user): return abort(403)
    session["view_as_user"] = True
    return redirect(url_for("index"))

@app.route("/admin/view_as_admin")
def admin_view_as_admin():
    session.pop("view_as_user", None)
    return redirect(url_for("index"))

def get_is_admin(user):
    if session.get("view_as_user"):
        return False
    return is_admin(user)

def get_readonly_admin(user):
    if session.get("view_as_user"):
        return False
    return is_readonly_admin(user)

@app.route("/", methods=["GET"])
def index():
    user = session.get("user")
    if not user: return redirect(url_for("login"))
    conn = get_conn()
    recent_scammers = [dict(r) for r in conn.execute("SELECT unique_id, name, amount_display, amount_int, category, item_name FROM scammers ORDER BY date DESC LIMIT 10").fetchall()]
    notices_list = [dict(r) for r in conn.execute("SELECT * FROM notices ORDER BY created_at DESC LIMIT 10").fetchall()]
    conn.close()
    return render_template_string(APP_TEMPLATE, page="home", user=user,
        recent_scammers=recent_scammers, notices_list=notices_list,
        is_admin=get_is_admin(user), readonly_admin=get_readonly_admin(user),
        view_as_user=session.get("view_as_user", False), is_real_admin=is_admin(user),
        logo_url=LOGO_URL, korean_num=korean_amount, korean_hof=korean_amount_hof,
        total_hof_amount=0)

@app.route("/scammers")
def scammers():
    user = session.get("user")
    if not user: return redirect(url_for("login"))
    page = int(request.args.get("page", 1))
    per_page = 20
    offset = (page - 1) * per_page
    conn = get_conn()
    rows = conn.execute("SELECT * FROM scammers ORDER BY date DESC LIMIT ? OFFSET ?", (per_page, offset)).fetchall()
    conn.close()
    return render_template_string(APP_TEMPLATE, page="list", user=user,
        scammers=[dict(r) for r in rows], is_admin=get_is_admin(user),
        readonly_admin=get_readonly_admin(user), view_as_user=session.get("view_as_user", False),
        is_real_admin=is_admin(user), current_page=page,
        logo_url=LOGO_URL, korean_num=korean_amount, korean_hof=korean_amount_hof,
        total_hof_amount=0, recent_scammers=[], notices_list=[])

@app.route("/scammer/<int:uid>")
def scammer_detail(uid):
    user = session.get("user")
    if not user: return redirect(url_for("login"))
    conn = get_conn()
    s = conn.execute("SELECT * FROM scammers WHERE unique_id = ?", (uid,)).fetchone()
    conn.close()
    if not s: return abort(404)
    return render_template_string(APP_TEMPLATE, page="detail", user=user,
        s=dict(s), is_admin=get_is_admin(user), readonly_admin=get_readonly_admin(user),
        view_as_user=session.get("view_as_user", False), is_real_admin=is_admin(user),
        logo_url=LOGO_URL, korean_num=korean_amount, korean_hof=korean_amount_hof,
        total_hof_amount=0, recent_scammers=[], notices_list=[])

@app.route("/hall_of_fame")
def hall_of_fame():
    user = session.get("user")
    if not user: return redirect(url_for("login"))
    conn = get_conn()
    hof_entries = [dict(r) for r in conn.execute("SELECT * FROM hall_of_fame ORDER BY created_at DESC").fetchall()]
    recent_scammers = [dict(r) for r in conn.execute("SELECT unique_id, name, amount_display, amount_int, category, item_name FROM scammers ORDER BY date DESC LIMIT 10").fetchall()]
    conn.close()
    total_hof_amount = sum(int(e.get("amount_int") or 0) for e in hof_entries)
    return render_template_string(APP_TEMPLATE, page="hof", user=user,
        hof_entries=hof_entries, is_admin=get_is_admin(user), readonly_admin=get_readonly_admin(user),
        logo_url=LOGO_URL, korean_num=korean_amount, korean_hof=korean_amount_hof,
        total_hof_amount=total_hof_amount, view_as_user=session.get("view_as_user", False),
        is_real_admin=is_admin(user), recent_scammers=recent_scammers, notices_list=[])

@app.route("/appeal")
def appeal():
    user = session.get("user")
    if not user: return redirect(url_for("login"))
    return render_template_string(APP_TEMPLATE, page="appeal", user=user,
        is_admin=get_is_admin(user), readonly_admin=get_readonly_admin(user),
        view_as_user=session.get("view_as_user", False), is_real_admin=is_admin(user),
        logo_url=LOGO_URL, korean_num=korean_amount, korean_hof=korean_amount_hof,
        total_hof_amount=0, recent_scammers=[], notices_list=[])

@app.route("/submit_appeal", methods=["POST"])
def submit_appeal():
    user = session.get("user")
    if not user: return abort(403)
    uid = request.form.get("unique_id")
    contact = request.form.get("contact")
    reason = request.form.get("reason")
    if uid and contact and reason:
        conn = get_conn()
        conn.execute("INSERT INTO appeals (unique_id, reason, contact, created_at) VALUES (?, ?, ?, ?)", (uid, reason, contact, now_iso()))
        conn.commit()
        conn.close()
    return "<script>alert('이의 제기가 접수되었습니다. 관리자가 검토합니다.'); location.href='/';</script>"

@app.route("/admin", methods=["GET"])
def admin_panel():
    user = session.get("user")
    if not is_admin(user): return abort(403)
    tab = request.args.get("tab", "dashboard")
    conn = get_conn()
    all_scammers = [dict(r) for r in conn.execute("SELECT * FROM scammers ORDER BY date DESC").fetchall()]
    distinct_scammer_count = conn.execute("SELECT COUNT(DISTINCT unique_id) as c FROM scammers").fetchone()["c"]
    all_notices  = [dict(r) for r in conn.execute("SELECT * FROM notices ORDER BY created_at DESC").fetchall()]
    all_hof      = [dict(r) for r in conn.execute("SELECT * FROM hall_of_fame ORDER BY created_at DESC").fetchall()]
    audit_logs   = [dict(r) for r in conn.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 200").fetchall()]
    recent_scammers = [dict(r) for r in conn.execute("SELECT unique_id, name, amount_display, amount_int, category, item_name FROM scammers ORDER BY date DESC LIMIT 10").fetchall()]
    total_hof_amount = sum(int(e.get("amount_int") or 0) for e in all_hof)
    conn.close()
    return render_template_string(APP_TEMPLATE, page="admin", user=user, tab=tab,
        all_scammers=all_scammers, all_notices=all_notices, all_hof=all_hof,
        audit_logs=audit_logs, is_admin=True, readonly_admin=is_readonly_admin(user),
        logo_url=LOGO_URL, korean_num=korean_amount, korean_hof=korean_amount_hof,
        total_hof_amount=total_hof_amount, view_as_user=False, is_real_admin=True,
        recent_scammers=recent_scammers, notices_list=[], distinct_scammer_count=distinct_scammer_count)

# ── 관리자: 블랙리스트 CRUD ──
@app.route("/admin/register", methods=["POST"])
def admin_register():
    user = session.get("user")
    if not is_admin(user) or is_readonly_admin(user): return abort(403)
    uid_raw = request.form.get("unique_id", "0")
    uid = int(re.sub(r"[^\d]", "", uid_raw) or "0")
    name = request.form.get("name", "Unknown").strip()
    amount_int, amount_disp = parse_amount(request.form.get("amount", ""))
    memo = request.form.get("admin_memo", "")
    reason = request.form.get("reason", "").strip()
    victim_id = request.form.get("victim_id", "").strip()
    victim_name = request.form.get("victim_name", "").strip()

    # 카테고리 조합
    cats = []
    if request.form.get("cat_item"): cats.append("아이템")
    if request.form.get("cat_money"): cats.append("돈")
    category = ",".join(cats) if cats else "아이템"
    item_name = request.form.get("item_name", "").strip()

    conn = get_conn()
    conn.execute("INSERT INTO scammers (unique_id, name, amount_display, amount_int, category, reason, admin_memo, reporter_id, victim_id, victim_name, item_name, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (uid, name, amount_disp, amount_int, category, reason, memo, user["id"], victim_id, victim_name, item_name, now_iso()))
    log_admin_action(conn, user["id"], "블랙리스트 수동 등록", f"UID {uid} - {name}")
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel", tab="scammers"))

@app.route("/admin/scammer_delete", methods=["POST"])
def admin_scammer_delete():
    user = session.get("user")
    if not is_admin(user) or is_readonly_admin(user): return abort(403)
    record_id = request.form.get("record_id")
    conn = get_conn()
    row = conn.execute("SELECT name, unique_id FROM scammers WHERE id=?", (record_id,)).fetchone()
    conn.execute("DELETE FROM scammers WHERE id=?", (record_id,))
    log_admin_action(conn, user["id"], "블랙리스트 사건 삭제", f"ID {record_id} - UID {row['unique_id'] if row else '?'} - {row['name'] if row else '?'}")
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel", tab="scammers"))

@app.route("/admin/scammer_delete_all", methods=["POST"])
def admin_scammer_delete_all():
    user = session.get("user")
    if not is_admin(user) or is_readonly_admin(user): return abort(403)
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) as c FROM scammers").fetchone()["c"]
    conn.execute("DELETE FROM scammers")
    log_admin_action(conn, user["id"], "블랙리스트 전체 삭제", f"총 {count}명 삭제")
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel", tab="scammers"))

@app.route("/admin/bulk_update_scammer", methods=["POST"])
def admin_bulk_update_scammer():
    user = session.get("user")
    if not is_admin(user) or is_readonly_admin(user): return abort(403)
    old_uid_raw = request.form.get("old_unique_id", "").strip()
    new_uid_raw = request.form.get("new_unique_id", "").strip()
    new_name = request.form.get("new_name", "").strip()

    if not old_uid_raw.isdigit():
        return "<script>alert('현재 고유번호를 올바르게 입력해주세요.'); history.back();</script>"

    old_uid = int(old_uid_raw)
    conn = get_conn()
    rows = conn.execute("SELECT id, unique_id, name FROM scammers WHERE unique_id = ?", (old_uid,)).fetchall()
    if not rows:
        conn.close()
        return "<script>alert('해당 고유번호를 가진 등록 정보를 찾을 수 없습니다.'); history.back();</script>"

    update_parts = []
    params = []
    if new_uid_raw and new_uid_raw.isdigit():
        update_parts.append("unique_id = ?")
        params.append(int(new_uid_raw))
    if new_name:
        update_parts.append("name = ?")
        params.append(new_name)

    if not update_parts:
        conn.close()
        return "<script>alert('변경할 내용(새 고유번호 또는 새 닉네임)을 최소 하나 입력해주세요.'); history.back();</script>"

    params.append(old_uid)
    count = len(rows)
    conn.execute(f"UPDATE scammers SET {', '.join(update_parts)} WHERE unique_id = ?", params)
    log_admin_action(conn, user["id"], "블랙리스트 일괄변경",
        f"UID {old_uid} → {new_uid_raw or old_uid} / 닉네임 → {new_name or '유지'} ({count}건)")
    conn.commit()
    conn.close()
    return f"<script>alert('일괄변경 완료! 총 {count}건이 변경되었습니다.'); location.href='/admin?tab=scammers';</script>"

@app.route("/admin/scammer_edit", methods=["POST"])
def admin_scammer_edit():
    user = session.get("user")
    if not is_admin(user) or is_readonly_admin(user): return abort(403)
    record_id = request.form.get("record_id")
    new_uid_raw = request.form.get("new_unique_id", "").strip()
    name = request.form.get("name", "").strip()
    amount_int, amount_disp = parse_amount(request.form.get("amount", ""))
    memo = request.form.get("admin_memo", "").strip()
    category = request.form.get("category", "주사위")
    item_name = request.form.get("item_name", "").strip()
    conn = get_conn()
    # 고유번호 변경 여부
    if new_uid_raw.isdigit():
        conn.execute("UPDATE scammers SET unique_id=?, name=?, amount_display=?, amount_int=?, admin_memo=?, category=?, item_name=? WHERE id=?",
            (int(new_uid_raw), name, amount_disp, amount_int, memo, category, item_name, record_id))
    else:
        conn.execute("UPDATE scammers SET name=?, amount_display=?, amount_int=?, admin_memo=?, category=?, item_name=? WHERE id=?",
            (name, amount_disp, amount_int, memo, category, item_name, record_id))
    log_admin_action(conn, user["id"], "블랙리스트 수정", f"RecordID {record_id} → {name}")
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel", tab="scammers"))

# ── 관리자: 공지 CRUD ──
@app.route("/admin/notice_add", methods=["POST"])
def admin_notice_add():
    user = session.get("user")
    if not is_admin(user): return abort(403)
    title = request.form.get("title")
    content = request.form.get("content")
    notice_type = request.form.get("notice_type", "공지")
    conn = get_conn()
    conn.execute("INSERT INTO notices (title, content, notice_type, created_at) VALUES (?, ?, ?, ?)", (title, content, notice_type, now_iso()))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel", tab="notices"))

@app.route("/admin/notice_delete", methods=["POST"])
def admin_notice_delete():
    user = session.get("user")
    if not is_admin(user): return abort(403)
    nid = request.form.get("notice_id")
    conn = get_conn()
    conn.execute("DELETE FROM notices WHERE id=?", (nid,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel", tab="notices"))

@app.route("/admin/notice_edit", methods=["POST"])
def admin_notice_edit():
    user = session.get("user")
    if not is_admin(user): return abort(403)
    nid = request.form.get("notice_id")
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    notice_type = request.form.get("notice_type", "공지")
    conn = get_conn()
    conn.execute("UPDATE notices SET title=?, content=?, notice_type=? WHERE id=?", (title, content, notice_type, nid))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel", tab="notices"))

# ── 관리자: 후원의 전당 CRUD ──
@app.route("/admin/hof_add", methods=["POST"])
def admin_hof_add():
    user = session.get("user")
    if not is_admin(user): return abort(403)
    name = request.form.get("name", "").strip()
    badge = request.form.get("badge", "💝").strip()
    amount_raw = request.form.get("amount", "").strip()
    description = request.form.get("description", "").strip()
    # 금액 파싱
    digits = re.sub(r"[^\d]", "", amount_raw)
    amount_int = int(digits) if digits else 0
    amount_display = korean_amount_hof(amount_int) if amount_int else amount_raw
    if name:
        conn = get_conn()
        conn.execute("INSERT INTO hall_of_fame (name, badge, amount, amount_int, description, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (name, badge, amount_display, amount_int, description, now_iso()))
        log_admin_action(conn, user["id"], "후원의 전당 등록", f"{name}")
        conn.commit()
        conn.close()
    return redirect(url_for("admin_panel", tab="hof_admin"))

@app.route("/admin/hof_edit", methods=["POST"])
def admin_hof_edit():
    user = session.get("user")
    if not is_admin(user): return abort(403)
    hof_id = request.form.get("hof_id")
    name = request.form.get("name", "").strip()
    badge = request.form.get("badge", "💝").strip()
    amount_raw = request.form.get("amount", "").strip()
    description = request.form.get("description", "").strip()
    digits = re.sub(r"[^\d]", "", amount_raw)
    amount_int = int(digits) if digits else 0
    amount_display = korean_amount_hof(amount_int) if amount_int else amount_raw
    conn = get_conn()
    conn.execute("UPDATE hall_of_fame SET name=?, badge=?, amount=?, amount_int=?, description=? WHERE id=?",
        (name, badge, amount_display, amount_int, description, hof_id))
    log_admin_action(conn, user["id"], "후원의 전당 수정", f"ID {hof_id} → {name}")
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel", tab="hof_admin"))

@app.route("/admin/hof_delete", methods=["POST"])
def admin_hof_delete():
    user = session.get("user")
    if not is_admin(user): return abort(403)
    hof_id = request.form.get("hof_id")
    conn = get_conn()
    conn.execute("DELETE FROM hall_of_fame WHERE id=?", (hof_id,))
    log_admin_action(conn, user["id"], "후원의 전당 삭제", f"ID {hof_id}")
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel", tab="hof_admin"))

@app.route("/admin/change_password", methods=["POST"])
def admin_change_password():
    user = session.get("user")
    if not is_admin(user) or is_readonly_admin(user): return abort(403)
    new_pw = request.form.get("new_password", "").strip()
    if new_pw and len(new_pw) >= 4:
        set_login_password(new_pw)
        log_admin_action(get_conn(), user["id"], "입장코드 변경", "")
        return "<script>alert('입장코드가 변경되었습니다.'); location.href='/admin?tab=settings';</script>"
    return "<script>alert('4자리 이상 입력해주세요.'); history.back();</script>"

# ── 관리자: 감사 로그 ──
@app.route("/admin/clear_logs", methods=["POST"])
def admin_clear_logs():
    user = session.get("user")
    if not is_admin(user): return abort(403)
    conn = get_conn()
    conn.execute("DELETE FROM audit_logs")
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel", tab="logs"))

# ── CSV 내보내기 ──
@app.route("/admin/export_csv")
def admin_export_csv():
    user = session.get("user")
    if not is_admin(user): return abort(403)
    conn = get_conn()
    rows = conn.execute("SELECT unique_id, name, amount_int, category, reason, admin_memo, date FROM scammers").fetchall()
    conn.close()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['고유번호', '닉네임', '피해금액', '카테고리', '사유', '관리자메모', '등록일자'])
    for r in rows:
        cw.writerow([r['unique_id'], r['name'], r['amount_int'], r['category'], r['reason'], r['admin_memo'], r['date']])
    return Response(si.getvalue().encode('utf-8-sig'), mimetype='text/csv',
        headers={"Content-Disposition": "attachment;filename=freedom_db.csv"})

# ── API ──
@app.route("/api/search")
def api_search():
    user = session.get("user")
    if not user:
        return jsonify({"success": False, "results": []})
    q = request.args.get("q", "").strip()
    if not q.isdigit():
        return jsonify({"success": True, "results": [], "msg": "고유번호(숫자)로만 검색 가능합니다."})
    conn = get_conn()
    rows = conn.execute("SELECT * FROM scammers WHERE unique_id = ? ORDER BY date DESC", (int(q),)).fetchall()
    conn.close()
    if not rows:
        return jsonify({"success": True, "results": []})
    latest_name = rows[0]["name"]  # 가장 최근 닉네임
    results = [{"unique_id": r["unique_id"], "name": latest_name,
                "amount_display": r["amount_display"], "amount_int": r["amount_int"],
                "amount_korean": korean_amount(r["amount_int"]),
                "category": r["category"] or "",
                "item_name": r["item_name"] or "" if "item_name" in r.keys() else "",
                "victim_id": r["victim_id"] or "" if "victim_id" in r.keys() else "",
                "victim_name": r["victim_name"] or "" if "victim_name" in r.keys() else "",
                "reason": r["reason"] or "" if "reason" in r.keys() else "",
                "date": r["date"]} for r in rows]
    return jsonify({"success": True, "results": results})

@app.route("/api/stats")
def api_stats():
    conn = get_conn()
    s = get_stats(conn)
    conn.close()
    return jsonify({"success": True, "stats": s})

@app.route("/api/check/<int:target_id>")
def api_check(target_id):
    conn = get_conn()
    row = conn.execute("SELECT unique_id, name, amount_display, date FROM scammers WHERE unique_id = ?", (target_id,)).fetchone()
    conn.close()
    if row: return jsonify({"is_scammer": True, "data": dict(row)})
    return jsonify({"is_scammer": False})

# ── Discord OAuth (관리자 전용) ──
@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code: return "No code provided", 400
    r = requests.post("https://discord.com/api/v10/oauth2/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT_URI, "scope": "identify"
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    access_token = r.json().get("access_token")
    if not access_token: return "Token exchange failed", 400

    user_info = requests.get("https://discord.com/api/v10/users/@me",
        headers={"Authorization": f"Bearer {access_token}"}).json()
    discord_id = str(user_info.get("id"))

    if discord_id not in ADMIN_IDS:
        return render_template_string(ERROR_TEMPLATE, code="403", title="접근 권한 없음",
            desc="관리자 권한이 없습니다.<br>이 페이지는 인가된 관리자만 접근할 수 있습니다.",
            back_url="/login", back_text="로그인으로 돌아가기")

    avatar_url = f"https://cdn.discordapp.com/avatars/{discord_id}/{user_info.get('avatar')}.png" if user_info.get("avatar") else "https://cdn.discordapp.com/embed/avatars/0.png"
    session["user"] = {"id": discord_id, "username": user_info.get("username"), "avatar_url": avatar_url}
    return redirect(url_for("admin_panel"))

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)