from flask import Flask, render_template, request, redirect, url_for, flash, make_response, session, jsonify, Response
import psycopg2
import psycopg2.extras
from pathlib import Path
from datetime import datetime, date, timedelta, timezone
import calendar
import csv
import io
import zoneinfo
import os
import json
import hmac
import hashlib
import base64
import time
import threading
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "iread@123")

from werkzeug.middleware.proxy_fix import ProxyFix

APP_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    static_folder=str(APP_DIR / "static"),
    template_folder=str(APP_DIR / "templates"),
)
app.secret_key = os.environ.get("SECRET_KEY", "iread-print-billing-secret-key-2026")
app.debug = False

# Reverse proxy support for Vercel / HTTPS headers
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

# Persistent, robust session cookie configuration
app.config.update(
    SESSION_COOKIE_NAME="iread_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_PATH="/",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

# Unified Single & Double Sided services list
DEFAULT_SERVICES = [
    # (name, single_rate, double_rate, print_type, paper_size, sheets_per_unit)
    ('Photostat B&W — A4', 2.00, 3.00, 'bw', 'A4', 1),
    ('Photostat B&W — Legal', 3.00, 4.00, 'bw', 'Legal', 1),
    ('Photostat B&W — A3', 5.00, 7.00, 'bw', 'A3', 1),
    ('Photostat Colour — A4', 8.00, 14.00, 'color', 'A4', 1),
    ('Photostat Colour — Legal', 10.00, 18.00, 'color', 'Legal', 1),
    ('Photostat Colour — A3', 15.00, 25.00, 'color', 'A3', 1),
    ('Print B&W — A4', 2.00, 3.00, 'bw', 'A4', 1),
    ('Print B&W — Legal', 4.00, 5.00, 'bw', 'Legal', 1),
    ('Print B&W — A3', 6.00, 9.00, 'bw', 'A3', 1),
    ('Print Colour — A4', 10.00, 18.00, 'color', 'A4', 1),
    ('Print Colour — A3', 18.00, 25.00, 'color', 'A3', 1),
    ('Scanning — per page', 2.00, None, 'service', 'Digital', 0),
    ('Sending — email/upload', 5.00, None, 'service', 'Digital', 0),
    ('Photo Paper — A4 130 gsm', 15.00, None, 'photo', 'A4', 1),
    ('Photo Paper — A4 220 gsm', 20.00, None, 'photo', 'A4', 1),
    ('Photo Paper — A3 220 gsm', 25.00, None, 'photo', 'A3', 1),
    ('Laser 12x18 — 220 gsm', 20.00, None, 'photo', '12x18', 1),
    ('Laser 12x18 — 130 gsm', 15.00, None, 'photo', '12x18', 1),
    ('Laser 12x18 — waterproof', 25.00, None, 'photo', '12x18', 1),
    ('Laser 12x18 — sticker sheet', 20.00, None, 'photo', '12x18', 1),
    ('Laser 12x18 — waterproof sticker', 25.00, None, 'photo', '12x18', 1),
    ('Lamination — ID card', 5.00, None, 'service', 'ID card', 0),
    ('Lamination — RC book', 5.00, None, 'service', 'RC book', 0),
    ('Lamination — A4', 10.00, None, 'service', 'A4', 0),
    ('Lamination — Legal', 15.00, None, 'service', 'Legal', 0),
    ('Lamination — A3', 25.00, None, 'service', 'A3', 0),
    ('Frame setting — Mini', 5.00, None, 'service', 'Mini', 0),
    ('Frame setting — 4x4', 8.00, None, 'service', '4x4', 0),
    ('Frame setting — A5', 10.00, None, 'service', 'A5', 0),
    ('Frame setting — A4', 15.00, None, 'service', 'A4', 0),
    ('Frame setting — A3', 25.00, None, 'service', 'A3', 0),
    ('Polaroids — 12x18 printing', 25.00, None, 'photo', '12x18', 1),
]

from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager

# ── Thread-Safe Connection Pool for High Performance ──
_DB_POOL = None
_POOL_LOCK = threading.Lock()

def get_db_pool():
    global _DB_POOL
    if _DB_POOL is None:
        with _POOL_LOCK:
            if _DB_POOL is None:
                _DB_POOL = ThreadedConnectionPool(
                    minconn=1,
                    maxconn=20,
                    dsn=DATABASE_URL,
                    cursor_factory=psycopg2.extras.RealDictCursor,
                    keepalives=1,
                    keepalives_idle=30,
                    keepalives_interval=10,
                    keepalives_count=5
                )
    return _DB_POOL

@contextmanager
def db():
    """
    Thread-safe connection pool context manager.
    Eliminates remote TCP+TLS handshake latency across all routes.
    """
    pool = get_db_pool()
    conn = pool.getconn()
    try:
        if conn.closed:
            conn = pool.getconn()
        yield conn
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            pool.putconn(conn)
        except Exception:
            pass

def init_db():
    if not DATABASE_URL:
        return
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    id SERIAL PRIMARY KEY,
                    category TEXT NOT NULL DEFAULT 'Paper',
                    item_name TEXT NOT NULL,
                    size_spec TEXT DEFAULT '',
                    bundles INTEGER NOT NULL DEFAULT 1,
                    sheets_per_bundle INTEGER NOT NULL DEFAULT 500,
                    total_sheets INTEGER NOT NULL DEFAULT 500,
                    available_sheets INTEGER NOT NULL DEFAULT 500,
                    reorder_level INTEGER NOT NULL DEFAULT 100,
                    cost REAL NOT NULL DEFAULT 0,
                    notes TEXT DEFAULT '',
                    updated_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                );
                ALTER TABLE inventory ADD COLUMN IF NOT EXISTS is_active INTEGER NOT NULL DEFAULT 1;
                CREATE TABLE IF NOT EXISTS stock_movements (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER REFERENCES inventory(id) ON DELETE CASCADE,
                    movement_type TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    reference_id TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS services (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    rate REAL NOT NULL DEFAULT 0,
                    double_rate REAL DEFAULT NULL,
                    print_type TEXT NOT NULL DEFAULT 'bw',
                    paper_size TEXT NOT NULL DEFAULT 'A4',
                    sheets_per_unit INTEGER NOT NULL DEFAULT 1,
                    paper_id INTEGER REFERENCES inventory(id) ON DELETE SET NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS bills (
                    id SERIAL PRIMARY KEY,
                    bill_no TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    customer TEXT DEFAULT '',
                    payment_method TEXT NOT NULL DEFAULT 'Cash',
                    subtotal REAL NOT NULL,
                    discount REAL NOT NULL DEFAULT 0,
                    total REAL NOT NULL,
                    paid REAL NOT NULL,
                    balance REAL NOT NULL DEFAULT 0,
                    paper_cost REAL DEFAULT 0,
                    profit REAL DEFAULT 0,
                    notes TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS bill_items (
                    id SERIAL PRIMARY KEY,
                    bill_id INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
                    service_name TEXT NOT NULL,
                    print_type TEXT NOT NULL,
                    paper_size TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    pages_per_copy INTEGER NOT NULL DEFAULT 1,
                    sides TEXT NOT NULL DEFAULT 'Single',
                    rate REAL NOT NULL,
                    line_total REAL NOT NULL,
                    paper_sheets INTEGER NOT NULL DEFAULT 0,
                    color_units INTEGER NOT NULL DEFAULT 0,
                    paper_cost REAL DEFAULT 0,
                    profit REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS maintenance_expenses (
                    id SERIAL PRIMARY KEY,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    machine_model TEXT DEFAULT '',
                    amount REAL NOT NULL DEFAULT 0,
                    expense_date TEXT NOT NULL,
                    technician_or_vendor TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );

                -- Migrations for Payment Status, Direct Printing, Bill Editing & Audit
                ALTER TABLE bills ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'Paid';
                ALTER TABLE bills ADD COLUMN IF NOT EXISTS is_deleted INTEGER NOT NULL DEFAULT 0;
                ALTER TABLE bills ADD COLUMN IF NOT EXISTS original_created_at TEXT;
                ALTER TABLE bills ADD COLUMN IF NOT EXISTS biller_name TEXT DEFAULT '';
                ALTER TABLE bills ADD COLUMN IF NOT EXISTS other_charges REAL DEFAULT 0;
                ALTER TABLE bills ADD COLUMN IF NOT EXISTS client_tx_id TEXT;
                CREATE UNIQUE INDEX IF NOT EXISTS idx_bills_client_tx_id ON bills(client_tx_id) WHERE client_tx_id IS NOT NULL;
                UPDATE bills SET original_created_at = created_at WHERE original_created_at IS NULL;
                ALTER TABLE bill_items ADD COLUMN IF NOT EXISTS inventory_id INTEGER REFERENCES inventory(id) ON DELETE SET NULL;

                CREATE TABLE IF NOT EXISTS bill_payments (
                    id SERIAL PRIMARY KEY,
                    bill_id INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
                    amount REAL NOT NULL,
                    payment_method TEXT NOT NULL DEFAULT 'Cash',
                    recorded_by TEXT DEFAULT 'Staff',
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS bill_audit_log (
                    id SERIAL PRIMARY KEY,
                    bill_id INTEGER,
                    bill_no TEXT NOT NULL,
                    action TEXT NOT NULL,
                    performed_by TEXT NOT NULL DEFAULT 'Admin',
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                ALTER TABLE bill_audit_log ADD COLUMN IF NOT EXISTS original_values TEXT DEFAULT '';
                ALTER TABLE bill_audit_log ADD COLUMN IF NOT EXISTS updated_values TEXT DEFAULT '';
                ALTER TABLE bill_audit_log ADD COLUMN IF NOT EXISTS fields_changed TEXT DEFAULT '';
                ALTER TABLE bill_audit_log ADD COLUMN IF NOT EXISTS reason TEXT DEFAULT '';
                ALTER TABLE bill_audit_log ADD COLUMN IF NOT EXISTS original_created_at TEXT DEFAULT '';

                CREATE TABLE IF NOT EXISTS purchases (
                    id SERIAL PRIMARY KEY,
                    purchase_date TEXT NOT NULL,
                    biller_name TEXT NOT NULL DEFAULT '',
                    supplier_name TEXT NOT NULL DEFAULT '',
                    bill_number TEXT NOT NULL DEFAULT '',
                    item_id INTEGER REFERENCES inventory(id) ON DELETE SET NULL,
                    item_name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Paper',
                    bundles INTEGER NOT NULL DEFAULT 1,
                    sheets_per_bundle INTEGER NOT NULL DEFAULT 500,
                    total_sheets INTEGER NOT NULL DEFAULT 500,
                    total_amount REAL NOT NULL DEFAULT 0,
                    paid_amount REAL NOT NULL DEFAULT 0,
                    balance_amount REAL NOT NULL DEFAULT 0,
                    payment_status TEXT NOT NULL DEFAULT 'Paid',
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS purchase_payments (
                    id SERIAL PRIMARY KEY,
                    purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
                    amount REAL NOT NULL,
                    payment_date TEXT NOT NULL,
                    payment_method TEXT NOT NULL DEFAULT 'Cash',
                    recorded_by TEXT DEFAULT 'Admin',
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );

                -- Migrations for Multi-Item Purchases, Audit Log & Stock Movement Tracking
                ALTER TABLE purchases ADD COLUMN IF NOT EXISTS is_deleted INTEGER NOT NULL DEFAULT 0;
                ALTER TABLE purchases ALTER COLUMN item_name DROP NOT NULL;

                CREATE TABLE IF NOT EXISTS purchase_items (
                    id SERIAL PRIMARY KEY,
                    purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
                    item_id INTEGER REFERENCES inventory(id) ON DELETE SET NULL,
                    item_name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Paper',
                    size_spec TEXT DEFAULT '',
                    quantity INTEGER NOT NULL,
                    unit_cost REAL NOT NULL DEFAULT 0,
                    line_total REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS purchase_audit_log (
                    id SERIAL PRIMARY KEY,
                    purchase_id INTEGER NOT NULL,
                    bill_number TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL,
                    performed_by TEXT NOT NULL DEFAULT 'Admin',
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS previous_balance INTEGER;
                ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS recorded_by TEXT DEFAULT 'Admin';
                ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS movement_date TEXT DEFAULT '';

                -- Migrations for Supplier Purchase Returns & Credits
                ALTER TABLE purchases ADD COLUMN IF NOT EXISTS returned_amount REAL NOT NULL DEFAULT 0;
                ALTER TABLE purchases ADD COLUMN IF NOT EXISTS supplier_credit REAL NOT NULL DEFAULT 0;
                ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS returned_quantity INTEGER NOT NULL DEFAULT 0;
                ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS returned_amount REAL NOT NULL DEFAULT 0;

                CREATE TABLE IF NOT EXISTS purchase_returns (
                    id SERIAL PRIMARY KEY,
                    purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
                    purchase_item_id INTEGER REFERENCES purchase_items(id) ON DELETE SET NULL,
                    item_id INTEGER REFERENCES inventory(id) ON DELETE SET NULL,
                    item_name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Paper',
                    size_spec TEXT DEFAULT '',
                    purchased_quantity INTEGER NOT NULL,
                    consumed_quantity INTEGER NOT NULL DEFAULT 0,
                    available_before INTEGER NOT NULL DEFAULT 0,
                    return_quantity INTEGER NOT NULL,
                    unit_cost REAL NOT NULL DEFAULT 0,
                    return_amount REAL NOT NULL DEFAULT 0,
                    return_date TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    notes TEXT DEFAULT '',
                    recorded_by TEXT NOT NULL DEFAULT 'Admin',
                    created_at TEXT NOT NULL
                );

                -- Backfill purchase_items from existing purchases if not already backfilled
                INSERT INTO purchase_items (purchase_id, item_id, item_name, category, quantity, unit_cost, line_total, created_at)
                SELECT p.id, p.item_id, p.item_name, p.category, p.total_sheets, 
                       CASE WHEN p.total_sheets > 0 THEN (p.total_amount::numeric / p.total_sheets)::real ELSE 0 END, 
                       p.total_amount, p.created_at
                FROM purchases p
                WHERE p.item_name IS NOT NULL AND p.item_name != ''
                  AND NOT EXISTS (SELECT 1 FROM purchase_items pi WHERE pi.purchase_id = p.id);

                -- Service tiered pricing columns & rule for Print B&W A4
                ALTER TABLE services ADD COLUMN IF NOT EXISTS double_rate REAL DEFAULT NULL;
                ALTER TABLE services ADD COLUMN IF NOT EXISTS extra_copy_rate REAL DEFAULT NULL;
                UPDATE services 
                SET rate = 10.0, double_rate = 15.0, extra_copy_rate = 5.0
                WHERE (id = 52 OR LOWER(TRIM(name)) = 'print b&w — a4' OR LOWER(TRIM(name)) = 'print b&w - a4')
                  AND (extra_copy_rate IS NULL OR double_rate != 15.0);
                """)

                # Seed essential paper stock if empty
                cur.execute("SELECT COUNT(*) AS c FROM inventory")
                if cur.fetchone()["c"] == 0:
                    now_iso = to_utc_iso()
                    default_papers = [
                        ('Paper', 'A4 75 GSM (JK Copier)', 'A4', 10, 500, 5000, 5000, 500, 2500.0, 'Initial JK Copier stock'),
                        ('Paper', 'Legal Paper 75 GSM', 'Legal', 5, 500, 2500, 2500, 250, 1500.0, 'Initial Legal paper stock'),
                        ('Paper', 'A3 Paper 75 GSM', 'A3', 2, 500, 1000, 1000, 100, 1000.0, 'Initial A3 paper stock'),
                        ('Lamination', 'A4 Lamination 125 Microns', 'A4', 5, 100, 500, 500, 50, 1250.0, 'Standard 125 mic pouches'),
                        ('Lamination', 'A4 Lamination 175 Microns', 'A4', 5, 100, 500, 500, 50, 1750.0, 'Heavy 175 mic pouches')
                    ]
                    for p in default_papers:
                        cur.execute("""
                        INSERT INTO inventory (category, item_name, size_spec, bundles, sheets_per_bundle, total_sheets, available_sheets, reorder_level, cost, notes, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (*p, now_iso))

                # App settings, users and print jobs tables
                cur.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'staff',
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS print_jobs (
                    id SERIAL PRIMARY KEY,
                    job_id TEXT UNIQUE NOT NULL,
                    bill_id INTEGER REFERENCES bills(id) ON DELETE CASCADE,
                    bill_no TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Print Pending',
                    printer_name TEXT DEFAULT '',
                    thermal_width TEXT NOT NULL DEFAULT '80mm',
                    receipt_text TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT DEFAULT '',
                    printed_by TEXT DEFAULT 'Staff',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_print_jobs_status ON print_jobs(status);
                CREATE INDEX IF NOT EXISTS idx_print_jobs_created_at ON print_jobs(created_at);
                CREATE INDEX IF NOT EXISTS idx_bills_deleted_created ON bills(is_deleted, created_at);
                """)

                # Seed admin and staff users if missing
                cur.execute("SELECT COUNT(*) AS c FROM users")
                if cur.fetchone()["c"] == 0:
                    now_iso = to_utc_iso()
                    admin_h = generate_password_hash("iread@123", method="pbkdf2:sha256")
                    staff_h = generate_password_hash("iread@staff123", method="pbkdf2:sha256")
                    cur.execute("""
                    INSERT INTO users (username, password_hash, role, name, created_at, is_active)
                    VALUES ('admin', %s, 'admin', 'Admin', %s, 1),
                           ('staff', %s, 'staff', 'Staff Counter', %s, 1)
                    """, (admin_h, now_iso, staff_h, now_iso))

                # Default app settings
                now_s = to_utc_iso()
                cur.execute("""
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ('printer_api_key', 'iread-print-token-2026', %s)
                ON CONFLICT (key) DO NOTHING;
                """, (now_s,))
                cur.execute("""
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ('thermal_width', '80mm', %s)
                ON CONFLICT (key) DO NOTHING;
                """, (now_s,))
                cur.execute("""
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ('default_printer', '__SYSTEM_DEFAULT__', %s)
                ON CONFLICT (key) DO NOTHING;
                """, (now_s,))
            conn.commit()
    except Exception as e:
        print(f"init_db skipped or failed: {e}")

def money(v):
    return round(float(v or 0), 2)

# ── Indian Standard Time (IST / Asia/Kolkata / UTC+05:30) Helpers ──
IST_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")

def get_utc_now():
    """Returns timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)

def get_ist_now():
    """Returns timezone-aware current Asia/Kolkata datetime (UTC+05:30)."""
    return datetime.now(timezone.utc).astimezone(IST_TZ)

def get_ist_today():
    """Returns date object for today in Asia/Kolkata."""
    return get_ist_now().date()

def get_ist_today_str():
    """Returns current date in Asia/Kolkata as YYYY-MM-DD."""
    return get_ist_today().strftime("%Y-%m-%d")

def to_utc_iso(dt_input=None):
    """
    Returns UTC ISO string (YYYY-MM-DDTHH:MM:SSZ).
    Normalizes any datetime or ISO string to standard UTC ISO.
    """
    if dt_input is None:
        return get_utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(dt_input, datetime):
        if dt_input.tzinfo is None:
            dt_input = dt_input.replace(tzinfo=timezone.utc)
        return dt_input.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    s = str(dt_input).strip()
    if not s:
        return get_utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s[:-1]).replace(tzinfo=timezone.utc)
        elif "+" in s[10:] or ("-" in s[10:] and len(s) > 19):
            dt = datetime.fromisoformat(s)
        else:
            # Historical naive string in DB: recorded in UTC
            dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return s

def to_ist_datetime(dt_input):
    """
    Converts any timestamp (UTC ISO, naive UTC string, or datetime object) to Asia/Kolkata datetime.
    Idempotent: will never apply timezone conversion twice!
    """
    if not dt_input:
        return None
    if isinstance(dt_input, datetime):
        if dt_input.tzinfo is None:
            dt_input = dt_input.replace(tzinfo=timezone.utc)
        return dt_input.astimezone(IST_TZ)
    s = str(dt_input).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s[:-1]).replace(tzinfo=timezone.utc)
        elif "+" in s[10:] or ("-" in s[10:] and len(s) > 19):
            dt = datetime.fromisoformat(s)
        else:
            dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return dt.astimezone(IST_TZ)
    except Exception:
        return None

def format_ist_datetime_str(dt_input, fmt="%Y-%m-%d %H:%M:%S"):
    """Returns formatted Asia/Kolkata date and time string."""
    dt = to_ist_datetime(dt_input)
    if not dt:
        return str(dt_input or '').replace('T', ' ')[:19]
    return dt.strftime(fmt)

def format_ist_date_str(dt_input):
    """Returns Asia/Kolkata date string (YYYY-MM-DD)."""
    dt = to_ist_datetime(dt_input)
    if not dt:
        return str(dt_input or '')[:10]
    return dt.strftime("%Y-%m-%d")

def ist_dates_to_utc_range(start_date_str, end_date_str):
    """
    Given YYYY-MM-DD date strings in Asia/Kolkata (IST), converts them to
    exact UTC ISO strings (start_utc_iso, end_utc_iso) so that:
        created_at >= start_utc_iso AND created_at < end_utc_iso
    efficiently queries rows belonging to the IST period using B-tree index
    without full table sequential scans or to_char() calls.
    """
    start_utc = None
    if start_date_str:
        try:
            s_clean = str(start_date_str).strip()[:10]
            s_dt = datetime.strptime(s_clean, "%Y-%m-%d").replace(tzinfo=IST_TZ)
            start_utc = s_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass

    end_utc = None
    if end_date_str:
        try:
            e_clean = str(end_date_str).strip()[:10]
            e_dt = (datetime.strptime(e_clean, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=IST_TZ)
            end_utc = e_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass

    return start_utc, end_utc

# ── In-Memory Fast Cache for Services Catalog ──
_SERVICES_CACHE = None
_SERVICES_CACHE_TIME = 0
_SERVICES_CACHE_TTL = 300  # 5 minutes, invalidated immediately on service modification

def get_cached_services(conn=None):
    global _SERVICES_CACHE, _SERVICES_CACHE_TIME
    now = time.time()
    if _SERVICES_CACHE is not None and (now - _SERVICES_CACHE_TIME) < _SERVICES_CACHE_TTL:
        return _SERVICES_CACHE

    def _query(c):
        with c.cursor() as cur:
            cur.execute("""
                SELECT id, name, rate, double_rate, extra_copy_rate, print_type, paper_size, sheets_per_unit, paper_id, active
                FROM services
                ORDER BY print_type, name
            """)
            rows = cur.fetchall()
            by_id = {r['id']: r for r in rows}
            by_name = {r['name'].strip().lower().replace('—', '-'): r for r in rows}
            active_list = [r for r in rows if r.get('active', 1) == 1]
            return {
                "rows": rows,
                "active_list": active_list,
                "by_id": by_id,
                "by_name": by_name
            }

    if conn:
        cache_data = _query(conn)
    else:
        with db() as c:
            cache_data = _query(c)

    _SERVICES_CACHE = cache_data
    _SERVICES_CACHE_TIME = now
    return _SERVICES_CACHE

def invalidate_services_cache():
    global _SERVICES_CACHE, _SERVICES_CACHE_TIME
    _SERVICES_CACHE = None
    _SERVICES_CACHE_TIME = 0

@app.template_filter("ist_datetime")
def filter_ist_datetime(dt_input, fmt="%Y-%m-%d %H:%M:%S"):
    return format_ist_datetime_str(dt_input, fmt)

@app.template_filter("ist_date")
def filter_ist_date(dt_input):
    return format_ist_date_str(dt_input)

@app.template_filter("inr")
def inr(value):
    return f"₹{float(value or 0):,.2f}"

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin login required to access this page.", "error")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated_function

# ── Login Rate Limiting & Anti-Brute-Force Protection ──
_LOGIN_ATTEMPTS = {}
_LOGIN_LOCK = threading.Lock()
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 300  # 5 minutes sliding window

def get_client_ip():
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"

def check_login_rate_limit(key):
    now = time.time()
    with _LOGIN_LOCK:
        attempts = _LOGIN_ATTEMPTS.get(key, [])
        valid_attempts = [t for t in attempts if now - t < LOGIN_LOCKOUT_SECONDS]
        _LOGIN_ATTEMPTS[key] = valid_attempts
        if len(valid_attempts) >= MAX_LOGIN_ATTEMPTS:
            remaining_seconds = int(LOGIN_LOCKOUT_SECONDS - (now - valid_attempts[0]))
            return False, max(1, remaining_seconds)
        return True, 0

def record_login_failure(key):
    now = time.time()
    with _LOGIN_LOCK:
        attempts = _LOGIN_ATTEMPTS.get(key, [])
        attempts.append(now)
        _LOGIN_ATTEMPTS[key] = attempts

def clear_login_failures(key):
    with _LOGIN_LOCK:
        if key in _LOGIN_ATTEMPTS:
            del _LOGIN_ATTEMPTS[key]

# ── Token Authentication & Security Helpers ──
def generate_auth_token(user_id, username, role, name, expires_in=86400 * 30):
    payload = {
        "uid": user_id,
        "username": username,
        "role": role,
        "name": name,
        "exp": int(time.time()) + expires_in
    }
    payload_json = json.dumps(payload, separators=(',', ':'))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode('utf-8')).decode('utf-8').rstrip('=')
    signature = hmac.new(app.secret_key.encode('utf-8'), payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"

def verify_auth_token(token):
    if not token or '.' not in token:
        return None
    try:
        parts = token.split('.')
        if len(parts) != 2:
            return None
        payload_b64, signature = parts
        expected_sig = hmac.new(app.secret_key.encode('utf-8'), payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        pad = len(payload_b64) % 4
        if pad:
            payload_b64 += '=' * (4 - pad)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode('utf-8')).decode('utf-8'))
        if payload.get('exp', 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif request.headers.get("X-Auth-Token"):
            token = request.headers.get("X-Auth-Token").strip()
        
        user_data = verify_auth_token(token)
        if not user_data:
            # Check Flask session for active Admin web session
            if session.get("is_admin"):
                user_data = {
                    "uid": session.get("user_id", 1),
                    "username": session.get("username") or "admin",
                    "role": "admin",
                    "name": session.get("name") or "Admin"
                }
            elif session.get("auth_token"):
                user_data = verify_auth_token(session.get("auth_token"))

        if not user_data:
            return jsonify({"success": False, "error": "Admin authentication required. Please log in."}), 401
        
        request.current_user = user_data
        return f(*args, **kwargs)
    return decorated

def admin_api_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif request.headers.get("X-Auth-Token"):
            token = request.headers.get("X-Auth-Token").strip()
        
        user_data = verify_auth_token(token)
        if not user_data:
            if session.get("is_admin"):
                user_data = {
                    "uid": session.get("user_id", 1),
                    "username": session.get("username") or "admin",
                    "role": "admin",
                    "name": session.get("name") or "Admin"
                }
            elif session.get("auth_token"):
                user_data = verify_auth_token(session.get("auth_token"))

        if not user_data:
            return jsonify({"success": False, "error": "Admin authentication required. Please log in."}), 401
        
        if user_data.get("role") != "admin":
            return jsonify({"success": False, "error": "Access denied. Admin privileges required."}), 403
        
        request.current_user = user_data
        return f(*args, **kwargs)
    return decorated

def printer_service_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        printer_token = request.headers.get("X-Printer-Token", "").strip()
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            user_data = verify_auth_token(token)
            if user_data and user_data.get("role") == "admin":
                return f(*args, **kwargs)
        
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM app_settings WHERE key='printer_api_key'")
                row = cur.fetchone()
                configured_token = row["value"] if row else "iread-print-token-2026"
                if printer_token and hmac.compare_digest(printer_token, configured_token):
                    return f(*args, **kwargs)
        
        return jsonify({"success": False, "error": "Invalid or missing printer authorization token."}), 401
    return decorated

# ── Thermal Receipt Formatter Helper ──
def format_thermal_receipt(bill, items, thermal_width="80mm", shop_name="IREAD STATIONS", cashier="Staff"):
    width = 32 if thermal_width == "58mm" else 42
    lines = []
    eq_border = "=" * width
    dash_border = "-" * width
    
    lines.append(eq_border)
    lines.append(shop_name.center(width))
    tagline = "Print • Photocopy • Lamination" if width > 35 else "Print • Copy • Laminate"
    lines.append(tagline.center(width))
    lines.append(eq_border)
    
    bill_no = bill.get("bill_no", "")
    created_at = bill.get("created_at", "")
    dt_str = format_ist_datetime_str(created_at, "%d/%m/%Y %I:%M %p")
    
    cust = (bill.get("customer") or "Walk-in Customer").strip()
    pay_method = bill.get("payment_method") or "Cash"
    pay_status = bill.get("payment_status") or "Paid"
    
    if width >= 40:
        lines.append(f"Bill No   : {bill_no}")
        lines.append(f"Date/Time : {dt_str}")
        lines.append(f"Customer  : {cust[:width-12]}")
        lines.append(f"Cashier   : {cashier}")
        lines.append(f"Payment   : {pay_method} ({pay_status})")
    else:
        lines.append(f"Bill : {bill_no}")
        lines.append(f"Date : {dt_str}")
        lines.append(f"Cust : {cust[:width-7]}")
        lines.append(f"User : {cashier}")
        lines.append(f"Pay  : {pay_method} ({pay_status})")
    
    lines.append(dash_border)
    if width >= 40:
        lines.append("Item                 Qty    Rate   Amount")
        lines.append(dash_border)
        for it in items:
            name = it.get("service_name", "")
            sides = it.get("sides", "Single")
            s_abbr = "(D)" if sides.lower().startswith("double") else "(S)"
            full_name = f"{name} {s_abbr}".strip()
            qty = it.get("quantity", 1)
            rate = f"{float(it.get('rate', 0)):.2f}"
            amount = f"{float(it.get('line_total', 0)):.2f}"
            if len(full_name) > 19:
                lines.append(full_name)
                lines.append(f"                    {qty:>4} {rate:>7} {amount:>8}")
            else:
                lines.append(f"{full_name:<19} {qty:>4} {rate:>7} {amount:>8}")
    else:
        lines.append("Item         Qty  Rate    Amount")
        lines.append(dash_border)
        for it in items:
            name = it.get("service_name", "")
            sides = it.get("sides", "Single")
            s_abbr = "(D)" if sides.lower().startswith("double") else "(S)"
            full_name = f"{name} {s_abbr}".strip()
            qty = it.get("quantity", 1)
            rate = f"{float(it.get('rate', 0)):.2f}"
            amount = f"{float(it.get('line_total', 0)):.2f}"
            if len(full_name) > 12:
                lines.append(full_name)
                lines.append(f"            {qty:>3} {rate:>6} {amount:>7}")
            else:
                lines.append(f"{full_name:<12} {qty:>3} {rate:>6} {amount:>7}")
                
    lines.append(dash_border)
    subtotal = f"Rs. {float(bill.get('subtotal', 0)):.2f}"
    discount = f"Rs. {float(bill.get('discount', 0)):.2f}"
    total = f"Rs. {float(bill.get('total', 0)):.2f}"
    paid = f"Rs. {float(bill.get('paid', 0)):.2f}"
    balance = f"Rs. {float(bill.get('balance', 0)):.2f}"
    
    lines.append(f"{'Subtotal:':<15}{subtotal:>{width-15}}")
    if float(bill.get("discount", 0)) > 0:
        lines.append(f"{'Discount:':<15}{discount:>{width-15}}")
    lines.append(dash_border)
    lines.append(f"{'TOTAL:':<15}{total:>{width-15}}")
    lines.append(f"{'PAID:':<15}{paid:>{width-15}}")
    if float(bill.get("balance", 0)) > 0:
        lines.append(f"{'BALANCE DUE:':<15}{balance:>{width-15}}")
    lines.append(eq_border)
    lines.append("Thank You! Visit Again".center(width))
    lines.append(eq_border)
    lines.append("\n\n\n\x1dVA0")
    
    return "\n".join(lines)

# ── Auth Routes & API ──
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        # Check database users first
        user_row = None
        try:
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM users WHERE username = %s AND is_active = 1", (username,))
                    user_row = cur.fetchone()
        except Exception:
            pass

        authenticated = False
        user_id = 1
        u_name = "admin"
        display_name = "Admin"

        if user_row and check_password_hash(user_row["password_hash"], password):
            authenticated = True
            user_id = user_row["id"]
            u_name = user_row["username"]
            display_name = user_row.get("name") or "Admin"
        elif username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            authenticated = True
            user_id = 1
            u_name = ADMIN_USERNAME
            display_name = "Admin"

        if authenticated:
            session.permanent = True
            session["user_id"] = user_id
            session["username"] = u_name
            session["user"] = u_name
            session["role"] = "admin"
            session["name"] = display_name
            session["is_admin"] = True
            token = generate_auth_token(user_id, u_name, "admin", display_name)
            session["auth_token"] = token
            flash(f"Welcome back, {display_name}!", "success")
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        else:
            flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("index"))

@app.route("/api/ping", methods=["GET"])
def api_ping():
    return jsonify({
        "ok": True,
        "success": True,
        "app": "iread-billing",
        "name": "Iread Stationery & Print Billing",
        "version": "2.1.0",
        "server_time": format_ist_datetime_str(get_utc_now()),
        "server_time_ist": format_ist_datetime_str(get_utc_now()),
        "timezone": "Asia/Kolkata (+05:30)"
    })

@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    
    if not username or not password:
        return jsonify({"success": False, "error": "Username and password required."}), 400

    client_ip = get_client_ip()
    rate_limit_key = f"{client_ip}:{username.lower()}"
    allowed, retry_after = check_login_rate_limit(rate_limit_key)
    if not allowed:
        return jsonify({
            "success": False,
            "error": f"Too many failed login attempts. Please wait {retry_after} seconds before trying again.",
            "retry_after": retry_after
        }), 429
        
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE username=%s AND is_active=1", (username,))
            user = cur.fetchone()
            
    authenticated = False
    auth_user = None
    if user and check_password_hash(user["password_hash"], password):
        authenticated = True
        auth_user = {
            "id": user["id"],
            "username": user["username"],
            "role": "admin",
            "name": user.get("name") or "Admin"
        }
    elif username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        authenticated = True
        auth_user = {
            "id": 1,
            "username": ADMIN_USERNAME,
            "role": "admin",
            "name": "Admin"
        }

    if not authenticated or not auth_user:
        record_login_failure(rate_limit_key)
        return jsonify({"success": False, "error": "Invalid username or password."}), 401
        
    clear_login_failures(rate_limit_key)
    token = generate_auth_token(auth_user["id"], auth_user["username"], "admin", auth_user["name"])
    
    # Establish session alongside token for seamless web/mobile parity
    session.permanent = True
    session["user_id"] = auth_user["id"]
    session["username"] = auth_user["username"]
    session["user"] = auth_user["username"]
    session["role"] = "admin"
    session["name"] = auth_user["name"]
    session["is_admin"] = True
    session["auth_token"] = token

    return jsonify({
        "success": True,
        "token": token,
        "user": {
            "id": auth_user["id"],
            "username": auth_user["username"],
            "role": "admin",
            "name": auth_user["name"]
        }
    })

@app.route("/api/auth/me", methods=["GET"])
@token_required
def api_auth_me():
    user = getattr(request, "current_user", {})
    return jsonify({
        "success": True,
        "user": user
    })

# ── Desktop / Install App & APK Download Route ──
@app.route("/install")
def install_page():
    apk_path = APP_DIR / "static" / "iread-billing-staff.apk"
    apk_exists = apk_path.exists()
    apk_size_mb = round(apk_path.stat().st_size / (1024 * 1024), 1) if apk_exists else 0
    return render_template("install.html", apk_exists=apk_exists, apk_size_mb=apk_size_mb)

@app.route("/download/apk")
def download_apk():
    from flask import send_from_directory
    apk_dir = APP_DIR / "static"
    apk_filename = "iread-billing-staff.apk"
    if not (apk_dir / apk_filename).exists():
        flash("Android APK is currently being generated. Please check back in a moment.", "info")
        return redirect(url_for("install_page"))
    return send_from_directory(apk_dir, apk_filename, as_attachment=True, download_name="iread-billing-staff.apk")

# ── Paper & Stock Inventory Helper Functions ──

def process_create_purchase(cur, data, is_admin, biller_default="Staff"):
    now = to_utc_iso()
    supplier_name = (data.get("supplier_name") or "").strip()
    bill_number = (data.get("bill_number") or "").strip()
    purchase_date = data.get("purchase_date") or get_ist_today_str()
    biller_name = (data.get("biller_name") or "").strip() or biller_default
    payment_method = (data.get("payment_method") or "Cash").strip()
    notes = (data.get("notes") or "").strip()
    raw_items = data.get("items") or []

    if not raw_items:
        raise ValueError("Purchase must contain at least one paper item.")

    parsed_items = []
    total_amount = 0.0
    total_sheets = 0
    for it in raw_items:
        i_name = (it.get("item_name") or "").strip()
        if not i_name:
            continue
        cat = (it.get("category") or "Paper").strip()
        size = (it.get("size_spec") or "A4").strip()
        qty = max(1, int(it.get("quantity") or it.get("qty") or 0))
        unit_cost = max(0.0, float(it.get("unit_cost") or it.get("rate") or 0))
        line_total = round(qty * unit_cost, 2)
        total_amount += line_total
        total_sheets += qty
        parsed_items.append({
            "item_name": i_name,
            "category": cat,
            "size_spec": size,
            "quantity": qty,
            "unit_cost": unit_cost,
            "line_total": line_total
        })

    if not parsed_items:
        raise ValueError("At least one valid paper item with name and quantity is required.")

    total_amount = round(total_amount, 2)
    paid_amount = max(0.0, round(float(data.get("paid_amount") or 0), 2))
    balance_amount = max(0.0, round(total_amount - paid_amount, 2))

    if paid_amount >= total_amount and total_amount > 0:
        payment_status = "Paid"
    elif paid_amount <= 0.001:
        payment_status = "Unpaid"
    else:
        payment_status = "Partially Paid"

    summary_name = parsed_items[0]["item_name"]
    if len(parsed_items) > 1:
        summary_name = f"{len(parsed_items)} items ({parsed_items[0]['item_name']}, +{len(parsed_items)-1} more)"

    # Insert 1 record into purchases
    cur.execute("""
    INSERT INTO purchases (purchase_date, biller_name, supplier_name, bill_number, item_name, category, bundles, sheets_per_bundle, total_sheets, total_amount, paid_amount, balance_amount, payment_status, notes, created_at, is_deleted)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
    RETURNING id
    """, (purchase_date, biller_name, supplier_name, bill_number, summary_name, parsed_items[0]["category"], 1, total_sheets, total_sheets, total_amount, paid_amount, balance_amount, payment_status, notes, now))
    purchase_id = cur.fetchone()["id"]

    # Insert items and update inventory stock
    for it in parsed_items:
        cur.execute("SELECT id, total_sheets, available_sheets, cost FROM inventory WHERE item_name ILIKE %s AND size_spec ILIKE %s", (it["item_name"], it["size_spec"]))
        existing = cur.fetchone()
        if not existing:
            cur.execute("SELECT id, total_sheets, available_sheets, cost FROM inventory WHERE item_name ILIKE %s", (it["item_name"],))
            existing = cur.fetchone()

        if existing:
            item_id = existing["id"]
            prev_bal = existing["available_sheets"]
            new_avail = prev_bal + it["quantity"]
            new_total = existing["total_sheets"] + it["quantity"]
            new_cost = round(existing["cost"] + it["line_total"], 2)
            cur.execute("""
            UPDATE inventory 
            SET total_sheets=%s, available_sheets=%s, cost=%s, updated_at=%s 
            WHERE id=%s
            """, (new_total, new_avail, new_cost, now, item_id))
        else:
            prev_bal = 0
            new_avail = it["quantity"]
            cur.execute("""
            INSERT INTO inventory (category, item_name, size_spec, bundles, sheets_per_bundle, total_sheets, available_sheets, reorder_level, cost, notes, updated_at)
            VALUES (%s, %s, %s, 1, %s, %s, %s, 100, %s, %s, %s)
            RETURNING id
            """, (it["category"], it["item_name"], it["size_spec"], it["quantity"], it["quantity"], it["quantity"], it["line_total"], notes, now))
            item_id = cur.fetchone()["id"]

        cur.execute("""
        INSERT INTO purchase_items (purchase_id, item_id, item_name, category, size_spec, quantity, unit_cost, line_total, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (purchase_id, item_id, it["item_name"], it["category"], it["size_spec"], it["quantity"], it["unit_cost"], it["line_total"], now))

        cur.execute("""
        INSERT INTO stock_movements (item_id, movement_type, quantity, previous_balance, balance_after, reference_id, notes, recorded_by, movement_date, created_at)
        VALUES (%s, 'PURCHASE', %s, %s, %s, %s, %s, %s, %s, %s)
        """, (item_id, it["quantity"], prev_bal, new_avail, bill_number, f"Supplier: {supplier_name} | By: {biller_name}", biller_name, purchase_date, now))

    if paid_amount > 0:
        cur.execute("""
        INSERT INTO purchase_payments (purchase_id, amount, payment_date, payment_method, recorded_by, notes, created_at)
        VALUES (%s, %s, %s, %s, %s, 'Initial purchase payment', %s)
        """, (purchase_id, paid_amount, purchase_date, payment_method, biller_name, now))

    return purchase_id, bill_number, total_amount, paid_amount, balance_amount, payment_status


def get_purchase_items_breakdown(cur, purchase_id):
    """
    Returns breakdown of purchased items, quantities consumed in billing,
    returned to supplier, and eligible unsold stock available for return.
    """
    cur.execute("""
        SELECT pi.*, 
               COALESCE(inv.available_sheets, 0) AS current_inv_avail,
               COALESCE(inv.total_sheets, 0) AS current_inv_total
        FROM purchase_items pi
        LEFT JOIN inventory inv ON pi.item_id = inv.id
        WHERE pi.purchase_id = %s
        ORDER BY pi.id ASC
    """, (purchase_id,))
    items = cur.fetchall()
    result = []
    for it in items:
        item_dict = dict(it)
        purchased_qty = int(item_dict.get("quantity") or 0)
        returned_qty = int(item_dict.get("returned_quantity") or 0)
        net_purchased = max(0, purchased_qty - returned_qty)
        inv_avail = int(item_dict.get("current_inv_avail") or 0)
        
        # Eligible to return is the unsold portion currently available in inventory
        eligible_return = max(0, min(net_purchased, inv_avail))
        # Consumed is whatever was purchased but is no longer available in stock
        consumed_qty = max(0, net_purchased - eligible_return)
        
        item_dict["net_quantity"] = net_purchased
        item_dict["eligible_to_return"] = eligible_return
        item_dict["consumed_quantity"] = consumed_qty
        item_dict["available_in_stock"] = inv_avail
        unit_cost = float(item_dict.get("unit_cost") or 0.0)
        item_dict["net_line_total"] = round(net_purchased * unit_cost, 2)
        result.append(item_dict)
    return result


def process_return_purchase_item(cur, purchase_id, purchase_item_id, return_qty, return_date=None, reason="", notes="", user_name="Admin"):
    now = to_utc_iso()
    return_date = return_date or get_ist_today_str()
    return_qty = int(return_qty or 0)
    if return_qty <= 0:
        raise ValueError("Return quantity must be greater than zero.")

    cur.execute("SELECT * FROM purchases WHERE id=%s AND is_deleted=0 FOR UPDATE", (purchase_id,))
    purchase = cur.fetchone()
    if not purchase:
        raise ValueError("Purchase bill not found or deleted.")

    cur.execute("SELECT * FROM purchase_items WHERE id=%s AND purchase_id=%s FOR UPDATE", (purchase_item_id, purchase_id))
    p_item = cur.fetchone()
    if not p_item:
        raise ValueError("Purchase item not found in this purchase bill.")

    item_id = p_item.get("item_id")
    if not item_id:
        raise ValueError("Inventory item reference missing for this purchase item.")

    cur.execute("SELECT id, item_name, available_sheets, total_sheets, cost FROM inventory WHERE id=%s FOR UPDATE", (item_id,))
    inv = cur.fetchone()
    if not inv:
        raise ValueError("Inventory item not found.")

    net_purchased = max(0, p_item["quantity"] - p_item["returned_quantity"])
    eligible_return = max(0, min(net_purchased, inv["available_sheets"]))
    consumed_qty = max(0, net_purchased - eligible_return)

    if return_qty > eligible_return:
        raise ValueError(
            f"Cannot return {return_qty} sheets of '{p_item['item_name']}': "
            f"only {eligible_return} unsold sheets are available in inventory. "
            f"The remaining {consumed_qty} sheets have already been consumed in billing."
        )

    unit_cost = float(p_item["unit_cost"] or 0.0)
    return_amount = round(return_qty * unit_cost, 2)

    # 1. Deduct stock from inventory
    prev_avail = inv["available_sheets"]
    new_avail = max(0, prev_avail - return_qty)
    new_total = max(0, inv["total_sheets"] - return_qty)
    new_cost = max(0.0, round(float(inv["cost"] or 0.0) - return_amount, 2))
    cur.execute("""
        UPDATE inventory 
        SET available_sheets=%s, total_sheets=%s, cost=%s, updated_at=%s 
        WHERE id=%s
    """, (new_avail, new_total, new_cost, now, item_id))

    # 2. Record stock movement
    cur.execute("""
        INSERT INTO stock_movements (item_id, movement_type, quantity, previous_balance, balance_after, reference_id, notes, recorded_by, movement_date, created_at)
        VALUES (%s, 'PURCHASE_RETURN', %s, %s, %s, %s, %s, %s, %s, %s)
    """, (item_id, -return_qty, prev_avail, new_avail, purchase["bill_number"], f"Returned to supplier {purchase['supplier_name']}: {reason}", user_name, return_date, now))

    # 3. Update purchase_items
    new_ret_qty = p_item["returned_quantity"] + return_qty
    new_ret_amt = round(float(p_item["returned_amount"] or 0.0) + return_amount, 2)
    cur.execute("""
        UPDATE purchase_items 
        SET returned_quantity=%s, returned_amount=%s 
        WHERE id=%s
    """, (new_ret_qty, new_ret_amt, purchase_item_id))

    # 4. Insert into purchase_returns
    cur.execute("""
        INSERT INTO purchase_returns (
            purchase_id, purchase_item_id, item_id, item_name, category, size_spec,
            purchased_quantity, consumed_quantity, available_before, return_quantity,
            unit_cost, return_amount, return_date, reason, notes, recorded_by, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        purchase_id, purchase_item_id, item_id, p_item["item_name"], p_item["category"], p_item["size_spec"],
        p_item["quantity"], consumed_qty, prev_avail, return_qty,
        unit_cost, return_amount, return_date, reason, notes, user_name, now
    ))

    # 5. Recalculate purchase financials
    cur.execute("SELECT COALESCE(SUM(returned_amount), 0) AS total_returned FROM purchase_items WHERE purchase_id=%s", (purchase_id,))
    total_returned = float(cur.fetchone()["total_returned"])

    gross_total = float(purchase["total_amount"])
    net_payable = max(0.0, round(gross_total - total_returned, 2))

    cur.execute("SELECT COALESCE(SUM(amount), 0) AS total_paid FROM purchase_payments WHERE purchase_id=%s", (purchase_id,))
    total_paid = float(cur.fetchone()["total_paid"])

    if total_paid > net_payable:
        new_balance = 0.0
        supplier_credit = round(total_paid - net_payable, 2)
        new_status = "Paid"
    else:
        new_balance = round(net_payable - total_paid, 2)
        supplier_credit = 0.0
        if new_balance <= 0.001:
            new_status = "Paid"
        elif total_paid <= 0.001:
            new_status = "Unpaid"
        else:
            new_status = "Partially Paid"

    cur.execute("""
        UPDATE purchases 
        SET returned_amount=%s, balance_amount=%s, supplier_credit=%s, payment_status=%s 
        WHERE id=%s
    """, (total_returned, new_balance, supplier_credit, new_status, purchase_id))

    # 6. Audit log
    cur.execute("""
        INSERT INTO purchase_audit_log (purchase_id, bill_number, action, performed_by, details, created_at)
        VALUES (%s, %s, 'RETURN', %s, %s, %s)
    """, (purchase_id, purchase["bill_number"], user_name, f"Returned {return_qty} sheets of '{p_item['item_name']}' (₹{return_amount}). Reason: {reason}.", now))

    return {
        "purchase_id": purchase_id,
        "item_name": p_item["item_name"],
        "return_quantity": return_qty,
        "return_amount": return_amount,
        "returned_total": total_returned,
        "net_payable": net_payable,
        "balance_amount": new_balance,
        "supplier_credit": supplier_credit,
        "payment_status": new_status
    }


def process_edit_purchase(cur, purchase_id, data, user_name="Admin"):
    now = to_utc_iso()
    cur.execute("SELECT * FROM purchases WHERE id=%s AND is_deleted=0 FOR UPDATE", (purchase_id,))
    purchase = cur.fetchone()
    if not purchase:
        raise ValueError("Purchase bill not found or already deleted.")

    cur.execute("SELECT * FROM purchase_items WHERE purchase_id=%s FOR UPDATE", (purchase_id,))
    old_items = cur.fetchall()
    old_items_by_id = {it["id"]: it for it in old_items}

    supplier_name = (data.get("supplier_name") or purchase["supplier_name"]).strip()
    bill_number = (data.get("bill_number") or purchase["bill_number"]).strip()
    purchase_date = data.get("purchase_date") or purchase["purchase_date"]
    biller_name = (data.get("biller_name") or purchase["biller_name"]).strip()
    notes = (data.get("notes") or "").strip()
    raw_new_items = data.get("items") or []

    if not raw_new_items:
        raise ValueError("Purchase must contain at least one item.")

    parsed_new_items = []
    for it in raw_new_items:
        i_name = (it.get("item_name") or "").strip()
        if not i_name:
            continue
        cat = (it.get("category") or "Paper").strip()
        size = (it.get("size_spec") or "A4").strip()
        qty = max(1, int(it.get("quantity") or it.get("qty") or 0))
        unit_cost = max(0.0, float(it.get("unit_cost") or it.get("rate") or 0))
        line_total = round(qty * unit_cost, 2)
        parsed_new_items.append({
            "id": it.get("id"),
            "item_name": i_name,
            "category": cat,
            "size_spec": size,
            "quantity": qty,
            "unit_cost": unit_cost,
            "line_total": line_total
        })

    if not parsed_new_items:
        raise ValueError("At least one valid paper item with name and quantity is required.")

    # Validate stock constraints against consumed and returned sheets
    for old_it in old_items:
        i_id = old_it.get("item_id")
        cur.execute("SELECT id, item_name, available_sheets, total_sheets, cost FROM inventory WHERE id=%s FOR UPDATE", (i_id,))
        inv = cur.fetchone()
        inv_avail = inv["available_sheets"] if inv else 0
        
        net_purchased = max(0, old_it["quantity"] - old_it["returned_quantity"])
        eligible_return = max(0, min(net_purchased, inv_avail))
        consumed_qty = max(0, net_purchased - eligible_return)
        min_allowed = consumed_qty + old_it["returned_quantity"]

        matching_new = None
        if old_it.get("id"):
            matching_new = next((n for n in parsed_new_items if n.get("id") and int(n["id"]) == old_it["id"]), None)
        if not matching_new:
            matching_new = next((n for n in parsed_new_items if n["item_name"].lower() == old_it["item_name"].lower()), None)

        if matching_new:
            if matching_new["quantity"] < min_allowed:
                raise ValueError(
                    f"Cannot reduce quantity of '{old_it['item_name']}' to {matching_new['quantity']} sheets: "
                    f"{consumed_qty} sheets have already been consumed in billing and {old_it['returned_quantity']} sheets returned to supplier "
                    f"(Minimum allowed: {min_allowed} sheets)."
                )
        else:
            if min_allowed > 0:
                raise ValueError(
                    f"Cannot remove '{old_it['item_name']}' from purchase bill: "
                    f"{consumed_qty} sheets have already been consumed in billing and {old_it['returned_quantity']} sheets returned to supplier."
                )

    # Process item updates and apply stock deltas cleanly
    handled_old_ids = set()
    for new_it in parsed_new_items:
        matched_old = None
        if new_it.get("id") and int(new_it["id"]) in old_items_by_id:
            matched_old = old_items_by_id[int(new_it["id"])]
        if not matched_old:
            for old_it in old_items:
                if old_it["id"] not in handled_old_ids and old_it["item_name"].lower() == new_it["item_name"].lower():
                    matched_old = old_it
                    break

        if matched_old:
            handled_old_ids.add(matched_old["id"])
            delta_qty = new_it["quantity"] - matched_old["quantity"]
            delta_cost = round((new_it["quantity"] * new_it["unit_cost"]) - (matched_old["quantity"] * float(matched_old["unit_cost"])), 2)
            i_id = matched_old["item_id"]

            if delta_qty != 0 or delta_cost != 0:
                cur.execute("SELECT id, available_sheets, total_sheets, cost FROM inventory WHERE id=%s FOR UPDATE", (i_id,))
                inv = cur.fetchone()
                if inv:
                    prev_bal = inv["available_sheets"]
                    new_avail = max(0, prev_bal + delta_qty)
                    new_tot = max(0, inv["total_sheets"] + delta_qty)
                    new_inv_cost = max(0.0, round(float(inv["cost"]) + delta_cost, 2))
                    cur.execute("""
                        UPDATE inventory 
                        SET available_sheets=%s, total_sheets=%s, cost=%s, updated_at=%s 
                        WHERE id=%s
                    """, (new_avail, new_tot, new_inv_cost, now, i_id))
                    cur.execute("""
                        INSERT INTO stock_movements (item_id, movement_type, quantity, previous_balance, balance_after, reference_id, notes, recorded_by, movement_date, created_at)
                        VALUES (%s, 'PURCHASE_EDIT', %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (i_id, delta_qty, prev_bal, new_avail, bill_number, f"Edit purchase item quantity ({matched_old['quantity']} -> {new_it['quantity']})", user_name, purchase_date, now))

            cur.execute("""
                UPDATE purchase_items 
                SET item_name=%s, category=%s, size_spec=%s, quantity=%s, unit_cost=%s, line_total=%s 
                WHERE id=%s
            """, (new_it["item_name"], new_it["category"], new_it["size_spec"], new_it["quantity"], new_it["unit_cost"], new_it["line_total"], matched_old["id"]))
        else:
            # Newly added item line
            cur.execute("SELECT id, total_sheets, available_sheets, cost FROM inventory WHERE item_name ILIKE %s AND size_spec ILIKE %s", (new_it["item_name"], new_it["size_spec"]))
            existing = cur.fetchone()
            if not existing:
                cur.execute("SELECT id, total_sheets, available_sheets, cost FROM inventory WHERE item_name ILIKE %s", (new_it["item_name"],))
                existing = cur.fetchone()

            if existing:
                i_id = existing["id"]
                prev_bal = existing["available_sheets"]
                new_avail = prev_bal + new_it["quantity"]
                new_tot = existing["total_sheets"] + new_it["quantity"]
                new_cost = round(float(existing["cost"]) + new_it["line_total"], 2)
                cur.execute("UPDATE inventory SET available_sheets=%s, total_sheets=%s, cost=%s, updated_at=%s WHERE id=%s", (new_avail, new_tot, new_cost, now, i_id))
            else:
                prev_bal = 0
                new_avail = new_it["quantity"]
                cur.execute("""
                    INSERT INTO inventory (category, item_name, size_spec, bundles, sheets_per_bundle, total_sheets, available_sheets, reorder_level, cost, notes, updated_at)
                    VALUES (%s, %s, %s, 1, %s, %s, %s, 100, %s, %s, %s)
                    RETURNING id
                """, (new_it["category"], new_it["item_name"], new_it["size_spec"], new_it["quantity"], new_it["quantity"], new_it["quantity"], new_it["line_total"], notes, now))
                i_id = cur.fetchone()["id"]

            cur.execute("""
                INSERT INTO purchase_items (purchase_id, item_id, item_name, category, size_spec, quantity, unit_cost, line_total, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (purchase_id, i_id, new_it["item_name"], new_it["category"], new_it["size_spec"], new_it["quantity"], new_it["unit_cost"], new_it["line_total"], now))

            cur.execute("""
                INSERT INTO stock_movements (item_id, movement_type, quantity, previous_balance, balance_after, reference_id, notes, recorded_by, movement_date, created_at)
                VALUES (%s, 'PURCHASE_EDIT_ADD', %s, %s, %s, %s, 'Added item during edit purchase', %s, %s, %s)
            """, (i_id, new_it["quantity"], prev_bal, new_avail, bill_number, user_name, purchase_date, now))

    # Remove items from purchase that were deleted in the edit (only if 0 consumed and 0 returned)
    for old_it in old_items:
        if old_it["id"] not in handled_old_ids:
            i_id = old_it.get("item_id")
            if i_id:
                cur.execute("SELECT id, available_sheets, total_sheets, cost FROM inventory WHERE id=%s FOR UPDATE", (i_id,))
                inv = cur.fetchone()
                if inv:
                    prev_bal = inv["available_sheets"]
                    new_avail = max(0, prev_bal - old_it["quantity"])
                    new_tot = max(0, inv["total_sheets"] - old_it["quantity"])
                    new_cost = max(0.0, round(float(inv["cost"]) - float(old_it["line_total"]), 2))
                    cur.execute("UPDATE inventory SET available_sheets=%s, total_sheets=%s, cost=%s, updated_at=%s WHERE id=%s", (new_avail, new_tot, new_cost, now, i_id))
                    cur.execute("""
                        INSERT INTO stock_movements (item_id, movement_type, quantity, previous_balance, balance_after, reference_id, notes, recorded_by, movement_date, created_at)
                        VALUES (%s, 'PURCHASE_EDIT_REMOVE', %s, %s, %s, %s, 'Removed item during edit purchase', %s, %s, %s)
                    """, (i_id, -old_it["quantity"], prev_bal, new_avail, bill_number, user_name, purchase_date, now))
            cur.execute("DELETE FROM purchase_items WHERE id=%s", (old_it["id"],))

    # Recalculate totals and financials
    cur.execute("""
        SELECT COALESCE(SUM(line_total), 0) AS total_amount,
               COALESCE(SUM(quantity), 0) AS total_sheets,
               COALESCE(SUM(returned_amount), 0) AS returned_amount
        FROM purchase_items
        WHERE purchase_id=%s
    """, (purchase_id,))
    summary = cur.fetchone()
    new_total_amount = round(float(summary["total_amount"]), 2)
    new_total_sheets = int(summary["total_sheets"])
    total_returned = round(float(summary["returned_amount"]), 2)
    net_payable = max(0.0, round(new_total_amount - total_returned, 2))

    cur.execute("SELECT COALESCE(SUM(amount), 0) AS total_paid FROM purchase_payments WHERE purchase_id=%s", (purchase_id,))
    total_paid_recorded = float(cur.fetchone()["total_paid"])

    if "paid_amount" in data and str(data["paid_amount"]).strip() != "":
        user_paid = max(0.0, round(float(data["paid_amount"]), 2))
        diff = round(user_paid - total_paid_recorded, 2)
        if diff != 0:
            cur.execute("""
            INSERT INTO purchase_payments (purchase_id, amount, payment_date, payment_method, recorded_by, notes, created_at)
            VALUES (%s, %s, %s, %s, %s, 'Edit payment adjustment', %s)
            """, (purchase_id, diff, purchase_date, data.get("payment_method", "Cash"), user_name, now))
            total_paid_recorded = user_paid

    if total_paid_recorded > net_payable:
        new_balance = 0.0
        supplier_credit = round(total_paid_recorded - net_payable, 2)
        new_status = "Paid"
    else:
        new_balance = round(net_payable - total_paid_recorded, 2)
        supplier_credit = 0.0
        if new_balance <= 0.001:
            new_status = "Paid"
        elif total_paid_recorded <= 0.001:
            new_status = "Unpaid"
        else:
            new_status = "Partially Paid"

    cur.execute("SELECT item_name FROM purchase_items WHERE purchase_id=%s ORDER BY id ASC", (purchase_id,))
    p_item_rows = cur.fetchall()
    summary_name = p_item_rows[0]["item_name"] if p_item_rows else "Paper"
    if len(p_item_rows) > 1:
        summary_name = f"{len(p_item_rows)} items ({p_item_rows[0]['item_name']}, +{len(p_item_rows)-1} more)"

    cur.execute("""
        UPDATE purchases 
        SET supplier_name=%s, bill_number=%s, purchase_date=%s, biller_name=%s,
            item_name=%s, total_sheets=%s, total_amount=%s, returned_amount=%s,
            paid_amount=%s, balance_amount=%s, supplier_credit=%s,
            payment_status=%s, notes=%s
        WHERE id=%s
    """, (supplier_name, bill_number, purchase_date, biller_name, summary_name, new_total_sheets, new_total_amount, total_returned, total_paid_recorded, new_balance, supplier_credit, new_status, notes, purchase_id))

    cur.execute("""
        INSERT INTO purchase_audit_log (purchase_id, bill_number, action, performed_by, details, created_at)
        VALUES (%s, %s, 'EDIT', %s, %s, %s)
    """, (purchase_id, bill_number, user_name, f"Edited purchase {bill_number}: Total {inr(new_total_amount)}, Balance {inr(new_balance)}.", now))

    return purchase_id, bill_number, new_total_amount, total_paid_recorded, new_balance, new_status


def process_delete_purchase(cur, purchase_id, reason="Admin deletion", user_name="Admin"):
    now = to_utc_iso()
    cur.execute("SELECT * FROM purchases WHERE id=%s AND is_deleted=0 FOR UPDATE", (purchase_id,))
    purchase = cur.fetchone()
    if not purchase:
        raise ValueError("Purchase bill not found or already deleted.")

    cur.execute("SELECT * FROM purchase_items WHERE purchase_id=%s", (purchase_id,))
    items = cur.fetchall()

    # Check returns and consumed stock constraints
    for it in items:
        if it.get("returned_quantity", 0) > 0:
            raise ValueError(
                f"Cannot delete purchase bill: {it['returned_quantity']} sheets of '{it['item_name']}' have already been returned to supplier. "
                "Purchase bills with return transactions must be preserved in history."
            )
        i_id = it.get("item_id")
        if i_id:
            cur.execute("SELECT item_name, available_sheets FROM inventory WHERE id=%s FOR UPDATE", (i_id,))
            inv = cur.fetchone()
            if inv:
                if inv["available_sheets"] < it["quantity"]:
                    consumed = it["quantity"] - inv["available_sheets"]
                    raise ValueError(
                        f"Cannot delete purchase bill: {consumed} sheets of '{inv['item_name']}' have already been consumed in billing. "
                        f"Use 'Return to Supplier' for remaining unsold stock instead of deleting the purchase bill."
                    )

    # Reverse stock from inventory
    for it in items:
        i_id = it.get("item_id")
        if i_id:
            cur.execute("SELECT id, available_sheets, total_sheets, cost FROM inventory WHERE id=%s FOR UPDATE", (i_id,))
            inv = cur.fetchone()
            if inv:
                prev_bal = inv["available_sheets"]
                new_avail = max(0, prev_bal - it["quantity"])
                new_tot = max(0, inv["total_sheets"] - it["quantity"])
                new_cost = max(0.0, round(float(inv["cost"]) - float(it["line_total"]), 2))
                cur.execute("UPDATE inventory SET available_sheets=%s, total_sheets=%s, cost=%s, updated_at=%s WHERE id=%s", (new_avail, new_tot, new_cost, now, i_id))
                cur.execute("""
                INSERT INTO stock_movements (item_id, movement_type, quantity, previous_balance, balance_after, reference_id, notes, recorded_by, movement_date, created_at)
                VALUES (%s, 'PURCHASE_CANCEL', %s, %s, %s, %s, %s, %s, %s, %s)
                """, (i_id, -it["quantity"], prev_bal, new_avail, purchase["bill_number"], f"Cancelled purchase {purchase['bill_number']}: {reason}", user_name, purchase["purchase_date"], now))

    # Soft delete purchase and clear balance
    cur.execute("""
    UPDATE purchases 
    SET is_deleted=1, balance_amount=0, notes=notes || %s 
    WHERE id=%s
    """, (f" [CANCELLED: {reason}]", purchase_id))

    cur.execute("""
    INSERT INTO purchase_audit_log (purchase_id, bill_number, action, performed_by, details, created_at)
    VALUES (%s, %s, 'DELETE', %s, %s, %s)
    """, (purchase_id, purchase["bill_number"], user_name, f"Deleted purchase {purchase['bill_number']}. Reason: {reason}. Stock reversed for {len(items)} items.", now))

    return purchase["bill_number"]


def process_stock_adjustment(cur, item_id, adj_type, quantity, adj_date, reason, user_name="Admin"):
    now = to_utc_iso()
    cur.execute("SELECT id, item_name, available_sheets FROM inventory WHERE id=%s FOR UPDATE", (item_id,))
    inv = cur.fetchone()
    if not inv:
        raise ValueError("Paper item not found.")

    old_bal = inv["available_sheets"]
    adj_type = (adj_type or "").upper().strip()

    if adj_type == "ADD":
        if quantity <= 0:
            raise ValueError("Adjustment quantity for Add Stock must be greater than zero.")
        sheets_change = quantity
        new_bal = old_bal + quantity
        m_type = "MANUAL_ADD"
    elif adj_type == "REDUCE":
        if quantity <= 0:
            raise ValueError("Adjustment quantity for Reduce Stock must be greater than zero.")
        if old_bal < quantity:
            raise ValueError(f"Cannot reduce stock below 0. Current available stock is only {old_bal} sheets.")
        sheets_change = -quantity
        new_bal = old_bal - quantity
        m_type = "MANUAL_REDUCE"
    elif adj_type == "SET":
        if quantity < 0:
            raise ValueError("Stock balance cannot be negative.")
        sheets_change = quantity - old_bal
        new_bal = quantity
        m_type = "MANUAL_SET"
    else:
        raise ValueError(f"Invalid adjustment type '{adj_type}'. Must be ADD, REDUCE, or SET.")

    cur.execute("UPDATE inventory SET available_sheets=%s, updated_at=%s WHERE id=%s", (new_bal, now, item_id))
    cur.execute("""
    INSERT INTO stock_movements (item_id, movement_type, quantity, previous_balance, balance_after, reference_id, notes, recorded_by, movement_date, created_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (item_id, m_type, sheets_change, old_bal, new_bal, f"Prev: {old_bal} -> New: {new_bal}", reason, user_name, adj_date, now))

    return inv["item_name"], old_bal, new_bal, sheets_change, m_type


# ── Safe Stock Item Removal & Archiving Logic (Admin only) ──
def process_remove_inventory_item(cur, item_id, reason="Removed by Admin", stock_treatment="zero_out", user_name="Admin"):
    cur.execute("SELECT id, item_name, category, size_spec, available_sheets, total_sheets, cost, is_active FROM inventory WHERE id = %s FOR UPDATE", (item_id,))
    item = cur.fetchone()
    if not item:
        raise ValueError("Inventory item not found.")

    item_name = item["item_name"]
    avail = item["available_sheets"] or 0

    # Inspect linked transactions across the application
    cur.execute("SELECT COUNT(*) AS c FROM purchase_items WHERE item_id = %s", (item_id,))
    purch_c = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) AS c FROM stock_movements WHERE item_id = %s", (item_id,))
    mov_c = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) AS c FROM purchase_returns WHERE item_id = %s", (item_id,))
    ret_c = cur.fetchone()["c"]

    cur.execute("SELECT id, name FROM services WHERE paper_id = %s", (item_id,))
    linked_services = cur.fetchall()

    has_transactions = (purch_c > 0 or mov_c > 0 or ret_c > 0)
    now_iso = to_utc_iso()
    today_iso = get_ist_today_str()

    if not has_transactions and len(linked_services) == 0:
        # Zero transactions and not linked to any services -> Safe permanent deletion
        cur.execute("DELETE FROM inventory WHERE id = %s", (item_id,))
        return f"Inventory item '{item_name}' permanently deleted as it had no transaction history."
    else:
        # Has historical transactions -> Safely archive/deactivate to preserve past bills, purchases & ledger
        stock_msg = ""
        if avail > 0:
            if stock_treatment == "zero_out":
                # Record explicit stock reduction in movement ledger
                cur.execute("""
                    INSERT INTO stock_movements (item_id, movement_type, quantity, previous_balance, balance_after, reference_id, notes, recorded_by, movement_date, created_at)
                    VALUES (%s, 'MANUAL_REDUCE', %s, %s, 0, 'ITEM_REMOVED', %s, %s, %s, %s)
                """, (item_id, -avail, avail, f"Stock written off upon item archiving/removal: {reason}", user_name, today_iso, now_iso))
                cur.execute("UPDATE inventory SET available_sheets = 0, is_active = 0, updated_at = %s WHERE id = %s", (now_iso, item_id))
                stock_msg = f"Remaining {avail} sheets written off and recorded in ledger."
            else:
                cur.execute("UPDATE inventory SET is_active = 0, updated_at = %s WHERE id = %s", (now_iso, item_id))
                stock_msg = f"Stock balance of {avail} sheets frozen on record."
        else:
            cur.execute("UPDATE inventory SET is_active = 0, updated_at = %s WHERE id = %s", (now_iso, item_id))
            stock_msg = "Stock balance was 0."

        # Unlink from active services so future bills don't attempt to deduct from this archived paper
        if linked_services:
            cur.execute("UPDATE services SET paper_id = NULL WHERE paper_id = %s", (item_id,))
            service_names = ", ".join([s["name"] for s in linked_services])
            stock_msg += f" Unlinked from service(s): {service_names}."

        return f"Inventory item '{item_name}' has been safely archived and removed from active stock ({stock_msg}). All historical records are preserved."

def process_reactivate_inventory_item(cur, item_id, user_name="Admin"):
    cur.execute("SELECT id, item_name, is_active FROM inventory WHERE id = %s FOR UPDATE", (item_id,))
    item = cur.fetchone()
    if not item:
        raise ValueError("Inventory item not found.")
    now_iso = to_utc_iso()
    cur.execute("UPDATE inventory SET is_active = 1, updated_at = %s WHERE id = %s", (now_iso, item_id))
    return f"Inventory item '{item['item_name']}' has been reactivated into active stock."


# ── Paper & Lamination Stock Inventory ──
@app.route("/inventory", methods=["GET", "POST"])
def inventory_page():
    if not DATABASE_URL:
        return "DATABASE_URL missing", 500
    is_admin = bool(session.get("is_admin"))
    user_name = "Admin" if is_admin else (session.get("user") or "Staff")

    with db() as conn:
        with conn.cursor() as cur:
            if request.method == "POST":
                action = request.form.get("action")
                now = to_utc_iso()

                # Action: Add Supplier Purchase (Supports Multi-item and Single-item)
                if action == "add":
                    try:
                        items_json = request.form.get("items_json")
                        if items_json:
                            items_data = json.loads(items_json)
                        else:
                            # Fallback to single item form inputs
                            item_name = request.form.get("item_name", "").strip()
                            category = request.form.get("category", "Paper").strip()
                            size_spec = request.form.get("size_spec", "").strip()
                            bundles = max(1, int(request.form.get("bundles", 1)))
                            sheets_per_bundle = max(1, int(request.form.get("sheets_per_bundle", 500)))
                            qty = bundles * sheets_per_bundle
                            total_amount = max(0.0, money(request.form.get("total_amount") or request.form.get("cost", 0)))
                            unit_cost = (total_amount / qty) if qty > 0 else 0.0
                            items_data = [{
                                "item_name": item_name,
                                "category": category,
                                "size_spec": size_spec,
                                "quantity": qty,
                                "unit_cost": unit_cost
                            }]

                        payload = {
                            "supplier_name": request.form.get("supplier_name", "").strip(),
                            "bill_number": request.form.get("bill_number", "").strip(),
                            "purchase_date": request.form.get("purchase_date") or get_ist_today_str(),
                            "biller_name": request.form.get("biller_name", "").strip() or user_name,
                            "payment_method": request.form.get("payment_method", "Cash").strip(),
                            "paid_amount": money(request.form.get("paid_amount", 0)),
                            "notes": request.form.get("notes", "").strip(),
                            "items": items_data
                        }

                        p_id, b_no, tot, pd, bal, st = process_create_purchase(cur, payload, is_admin, biller_default=user_name)
                        conn.commit()
                        flash(f"Recorded supplier purchase invoice '{b_no}' with {len(items_data)} item(s) (Total: {inr(tot)}).", "success")
                    except Exception as e:
                        conn.rollback()
                        flash(f"Error adding stock purchase: {e}", "error")

                # Action: Manual Stock Adjustment (Admin only)
                elif action == "adjust":
                    if not is_admin:
                        flash("Admin login required to adjust stock.", "error")
                        return redirect(url_for("login", next=request.path))
                    try:
                        item_id = int(request.form.get("item_id"))
                        adj_type = request.form.get("adj_type", "ADD")
                        quantity = int(request.form.get("sheets_change") or request.form.get("quantity", 0))
                        adj_date = request.form.get("adj_date") or get_ist_today_str()
                        reason = request.form.get("reason", "").strip()

                        i_name, old_bal, new_bal, change, m_type = process_stock_adjustment(
                            cur, item_id, adj_type, quantity, adj_date, reason, user_name=user_name
                        )
                        conn.commit()
                        flash(f"Manual stock adjustment for '{i_name}': {change:+d} sheets (New balance: {new_bal}).", "success")
                    except Exception as e:
                        conn.rollback()
                        flash(f"Error adjusting stock: {e}", "error")

                # Action: Remove / Archive / Delete stock item (Admin only)
                elif action in ("delete", "remove"):
                    if not is_admin:
                        flash("Admin login required to remove stock items.", "error")
                        return redirect(url_for("login", next=request.path))
                    try:
                        item_id = int(request.form.get("item_id"))
                        reason = (request.form.get("reason") or "Manual removal by Admin").strip()
                        stock_treatment = (request.form.get("stock_treatment") or "zero_out").strip()
                        msg = process_remove_inventory_item(cur, item_id, reason, stock_treatment, user_name)
                        conn.commit()
                        flash(msg, "success")
                    except Exception as e:
                        conn.rollback()
                        flash(f"Error removing stock item: {e}", "error")

                # Action: Reactivate / Restore archived stock item (Admin only)
                elif action == "reactivate":
                    if not is_admin:
                        flash("Admin login required to reactivate stock items.", "error")
                        return redirect(url_for("login", next=request.path))
                    try:
                        item_id = int(request.form.get("item_id"))
                        msg = process_reactivate_inventory_item(cur, item_id, user_name)
                        conn.commit()
                        flash(msg, "success")
                    except Exception as e:
                        conn.rollback()
                        flash(f"Error reactivating stock item: {e}", "error")

                return redirect(url_for("inventory_page"))

            # Fetch inventory counts
            cur.execute("""
            SELECT COUNT(*) AS total_count,
                   COUNT(CASE WHEN is_active = 1 THEN 1 END) AS active_count,
                   COUNT(CASE WHEN is_active = 0 THEN 1 END) AS archived_count
            FROM inventory
            """)
            counts = cur.fetchone()
            active_count = counts["active_count"]
            archived_count = counts["archived_count"]
            total_count = counts["total_count"]

            status_filter = request.args.get("status", "active").strip()
            inv_query = """
            SELECT id, category, item_name, size_spec, bundles, sheets_per_bundle, total_sheets, available_sheets, reorder_level, cost, notes, updated_at, is_active,
                   ROUND((cost / NULLIF(total_sheets, 0))::numeric, 3) AS cost_per_sheet
            FROM inventory 
            """
            if status_filter == "archived":
                inv_query += " WHERE is_active = 0"
            elif status_filter == "all":
                pass
            else:
                status_filter = "active"
                inv_query += " WHERE is_active = 1"

            inv_query += " ORDER BY is_active DESC, category, item_name"
            cur.execute(inv_query)
            items = cur.fetchall()
            for r in items:
                r['cost_per_sheet'] = float(r['cost_per_sheet'] or 0.0)

            # Active items for metrics and datalist (reuse items if already active to save remote roundtrip)
            if status_filter == "active":
                active_items = items
            elif status_filter == "all":
                active_items = [r for r in items if r.get('is_active') == 1]
            else:
                cur.execute("""
                SELECT id, category, item_name, size_spec, available_sheets, reorder_level, is_active,
                       ROUND((cost / NULLIF(total_sheets, 0))::numeric, 3) AS cost_per_sheet
                FROM inventory 
                WHERE is_active = 1
                ORDER BY category, item_name
                """)
                active_items = cur.fetchall()
                for r in active_items:
                    r['cost_per_sheet'] = float(r['cost_per_sheet'] or 0.0)

            total_items = len(active_items)
            total_available_sheets = sum(row.get("available_sheets", 0) for row in active_items)
            total_valuation = sum(row.get("available_sheets", 0) * row.get("cost_per_sheet", 0.0) for row in active_items)
            low_stock_items = [r for r in active_items if r.get('available_sheets', 0) <= r.get('reorder_level', 100)]

            # Fetch recent stock movements with audit fields
            cur.execute("""
            SELECT sm.created_at, sm.movement_type, sm.quantity, sm.previous_balance, sm.balance_after, sm.reference_id, sm.notes, sm.recorded_by, sm.movement_date, i.item_name
            FROM stock_movements sm
            JOIN inventory i ON sm.item_id = i.id
            ORDER BY sm.id DESC
            LIMIT 50
            """)
            movements = cur.fetchall()

            # Purchase history & filters (Active / non-deleted purchases)
            p_bill = request.args.get("p_bill", "").strip()
            p_biller = request.args.get("p_biller", "").strip()
            p_date = request.args.get("p_date", "").strip()

            p_query = "SELECT * FROM purchases WHERE is_deleted=0"
            p_params = []
            if p_bill:
                p_query += " AND bill_number ILIKE %s"
                p_params.append(f"%{p_bill}%")
            if p_biller:
                p_query += " AND (biller_name ILIKE %s OR supplier_name ILIKE %s)"
                p_params.append(f"%{p_biller}%")
                p_params.append(f"%{p_biller}%")
            if p_date:
                p_query += " AND purchase_date = %s"
                p_params.append(p_date)

            p_query += " ORDER BY id DESC LIMIT 100"
            cur.execute(p_query, tuple(p_params))
            purchases = cur.fetchall()

            # Attach purchase_items to each purchase
            purch_ids = [p["id"] for p in purchases]
            items_by_purch = {}
            if purch_ids:
                cur.execute("SELECT * FROM purchase_items WHERE purchase_id = ANY(%s) ORDER BY id ASC", (purch_ids,))
                for it in cur.fetchall():
                    items_by_purch.setdefault(it["purchase_id"], []).append(dict(it))

            for p in purchases:
                p_items = items_by_purch.get(p["id"], [])
                p["items"] = p_items
                p["items_count"] = len(p_items)

            # Supplier purchase stats for active invoices
            cur.execute("""
            SELECT COALESCE(SUM(total_amount), 0) AS total_purchases,
                   COALESCE(SUM(returned_amount), 0) AS total_returned_amount,
                   COALESCE(SUM(paid_amount), 0) AS total_paid_supplier,
                   COALESCE(SUM(balance_amount), 0) AS total_supplier_balance,
                   COALESCE(SUM(supplier_credit), 0) AS total_supplier_credit,
                   COUNT(CASE WHEN balance_amount > 0.001 THEN 1 END) AS pending_purchases_count
            FROM purchases
            WHERE is_deleted = 0
            """)
            purchase_stats = cur.fetchone()

    return render_template(
        "inventory.html",
        inventory=items,
        active_items=active_items,
        active_count=active_count,
        archived_count=archived_count,
        total_count=total_count,
        status_filter=status_filter,
        movements=movements,
        purchases=purchases,
        purchase_stats=purchase_stats,
        p_bill=p_bill,
        p_biller=p_biller,
        p_date=p_date,
        total_items=total_items,
        total_available_sheets=total_available_sheets,
        total_valuation=total_valuation,
        low_stock_items=low_stock_items,
        is_admin=is_admin
    )

# ── Maintenance & Expenses (Drum, Ink, Repair, Other) ──
@app.route("/maintenance", methods=["GET", "POST"])
@admin_required
def maintenance_page():
    if not DATABASE_URL:
        return "DATABASE_URL missing", 500
    with db() as conn:
        with conn.cursor() as cur:
            if request.method == "POST":
                action = request.form.get("action")
                if action == "add":
                    category = request.form.get("category", "Other").strip()
                    title = request.form.get("title", "").strip()
                    machine_model = request.form.get("machine_model", "").strip()
                    amount = max(0.0, money(request.form.get("amount", 0)))
                    expense_date = request.form.get("expense_date") or get_ist_today_str()
                    technician_or_vendor = request.form.get("technician_or_vendor", "").strip()
                    notes = request.form.get("notes", "").strip()
                    created_at = to_utc_iso()

                    if not title or amount <= 0:
                        flash("Please enter a valid description and cost amount.", "error")
                    else:
                        cur.execute("""
                        INSERT INTO maintenance_expenses (category, title, machine_model, amount, expense_date, technician_or_vendor, notes, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (category, title, machine_model, amount, expense_date, technician_or_vendor, notes, created_at))
                        conn.commit()
                        flash(f"Logged maintenance expense: '{title}' ({inr(amount)}).", "success")

                elif action == "delete":
                    try:
                        exp_id = int(request.form.get("expense_id"))
                        cur.execute("DELETE FROM maintenance_expenses WHERE id=%s", (exp_id,))
                        conn.commit()
                        flash("Maintenance entry deleted.", "success")
                    except Exception as e:
                        conn.rollback()
                        flash(f"Error deleting entry: {e}", "error")

                return redirect(url_for("maintenance_page"))

            cur.execute("SELECT * FROM maintenance_expenses ORDER BY expense_date DESC, id DESC")
            rows = cur.fetchall()
            total_count = len(rows)
            total_expense = sum(r.get("amount", 0.0) for r in rows)

    return render_template("maintenance.html", expenses=rows, total_count=total_count, total_expense=total_expense, today=get_ist_today_str())

# ── Dashboard Statistics Helper ──
def get_today_dashboard_stats(conn=None):
    today = get_ist_today_str()
    start_utc_iso, end_utc_iso = ist_dates_to_utc_range(today, today)
    
    def _run(cur):
        cur.execute("""
            SELECT COALESCE(SUM(total), 0) AS today_total,
                   COUNT(*) AS today_count
            FROM bills 
            WHERE created_at >= %s AND created_at < %s 
              AND is_deleted = 0
        """, (start_utc_iso, end_utc_iso))
        row = cur.fetchone()
        t_total = float(row['today_total'] if row else 0.0)
        t_count = int(row['today_count'] if row else 0)
        return {
            "today_total": t_total,
            "today_count": t_count,
            "today_total_formatted": inr(t_total)
        }

    if conn:
        with conn.cursor() as cur:
            return _run(cur)
    else:
        with db() as c:
            with c.cursor() as cur:
                return _run(cur)

@app.route("/api/dashboard-stats")
def dashboard_stats_api():
    try:
        stats = get_today_dashboard_stats()
        return {"ok": True, "success": True, **stats}
    except Exception as e:
        return {"ok": False, "success": False, "error": str(e)}, 500

# ── Billing Route (Fast Touch POS) ──
@app.route("/")
def index():
    if not DATABASE_URL:
        return "DATABASE_URL environment variable is missing.", 500
    try:
        services = get_cached_services()["active_list"]
        dash_stats = get_today_dashboard_stats()
        return render_template("index.html", services=services, today_total=dash_stats["today_total"], today_count=dash_stats["today_count"])
    except Exception as e:
        return f"Database query error: {str(e)}", 500

@app.post("/create-bill")
def create_bill():
    names      = request.form.getlist("item_service[]")
    quantities = request.form.getlist("item_qty[]")
    rates      = request.form.getlist("item_rate[]")
    pages      = request.form.getlist("item_pages[]")
    sides_list = request.form.getlist("item_sides[]")
    customer   = request.form.get("customer", "").strip()
    payment    = request.form.get("payment_method", "Cash")
    discount   = money(request.form.get("discount", 0))
    paid_input = request.form.get("paid", "")
    notes      = request.form.get("notes", "").strip()

    items = []
    subtotal = 0.0
    total_bill_paper_cost = 0.0
    cached_services = get_cached_services()

    with db() as conn:
        with conn.cursor() as cur:
            # Build sheet cost lookup from current active inventory
            cur.execute("""
            SELECT id, item_name, size_spec, available_sheets, 
                   ROUND((cost / NULLIF(total_sheets,0))::numeric, 4) AS cost_per_sheet
            FROM inventory
            WHERE is_active = 1
            """)
            inv_rows = cur.fetchall()
            inv_map = {r['id']: float(r['cost_per_sheet'] or 0.0) for r in inv_rows}
            inv_by_name = {r['item_name'].strip().lower(): (r['id'], float(r['cost_per_sheet'] or 0.0)) for r in inv_rows}
            inv_by_size = {}
            for r in inv_rows:
                key = (r['size_spec'] or '').strip().upper()
                if key and key not in inv_by_size:
                    inv_by_size[key] = (r['id'], float(r['cost_per_sheet'] or 0.0))

            for i, service_id in enumerate(names):
                if not service_id:
                    continue
                try:
                    qty            = int(quantities[i])
                    pages_per_copy = max(1, int(pages[i] or 1))
                    rate           = money(rates[i])
                    is_custom      = (service_id == 'custom')
                    service_id_int = None if is_custom else int(service_id)
                except (ValueError, IndexError):
                    continue

                if qty <= 0:
                    continue

                service = None
                if service_id_int:
                    service = cached_services['by_id'].get(service_id_int)

                sides = sides_list[i] if i < len(sides_list) else "Single"
                is_double = sides.lower().startswith("double")

                if service:
                    s_name = service["name"]
                    p_type = service["print_type"]
                    p_size = service["paper_size"]
                    paper_id = service.get("paper_id")
                    sheets_per_unit = service.get("sheets_per_unit", 1)
                else:
                    s_name = "Custom Service"
                    p_type = "service"
                    p_size = "A4"
                    paper_id = None
                    sheets_per_unit = 1

                # Physical sheets calculation: 1 copy = 1 physical sheet for both single-side and double-side jobs
                if sheets_per_unit == 0:
                    sheets = 0
                else:
                    sheets = qty * pages_per_copy

                line_total = money(qty * pages_per_copy * rate)
                color_units = qty * pages_per_copy if p_type in ("color", "photo") else 0

                # Determine cost per sheet from inventory
                unit_cost = 0.0
                matched_inventory_id = paper_id
                if matched_inventory_id and matched_inventory_id in inv_map:
                    unit_cost = inv_map[matched_inventory_id]
                elif s_name.lower() in inv_by_name:
                    matched_inventory_id, unit_cost = inv_by_name[s_name.lower()]
                else:
                    # Fallback to size spec
                    size_key = (p_size or '').strip().upper()
                    if size_key in inv_by_size and sheets > 0:
                        matched_inventory_id, unit_cost = inv_by_size[size_key]

                line_paper_cost = money(sheets * unit_cost) if sheets > 0 else 0.0
                line_profit = money(line_total - line_paper_cost)
                total_bill_paper_cost += line_paper_cost

                items.append({
                    "service_name": s_name,
                    "print_type": p_type,
                    "paper_size": p_size,
                    "quantity": qty,
                    "pages_per_copy": pages_per_copy,
                    "sides": sides,
                    "rate": rate,
                    "line_total": line_total,
                    "paper_sheets": sheets,
                    "color_units": color_units,
                    "paper_cost": line_paper_cost,
                    "profit": line_profit,
                    "inventory_id": matched_inventory_id
                })
                subtotal += line_total

            if not items:
                flash("Add at least one valid service to create a bill.", "error")
                return redirect(url_for("index"))

            subtotal   = money(subtotal)
            discount   = min(max(discount, 0), subtotal)
            total      = money(subtotal - discount)
            paid       = total if paid_input.strip() == "" else min(max(money(paid_input), 0), total)
            balance    = money(total - paid)
            if paid <= 0.001:
                payment_status = "Unpaid"
            elif balance <= 0.001:
                payment_status = "Paid"
            else:
                payment_status = "Partially Paid"

            total_bill_paper_cost = money(total_bill_paper_cost)
            # Gross profit for bill = total selling after discount - total paper cost
            bill_profit = money(total - total_bill_paper_cost)

            now_iso = to_utc_iso()
            ist_now = get_ist_now()
            bill_no = "IR" + ist_now.strftime("%y%m%d%H%M%S")

            # Insert Bill record with atomic savepoint to guarantee uniqueness with zero roundtrip check
            cur.execute("SAVEPOINT sp_bill_form_insert")
            try:
                cur.execute(
                    """INSERT INTO bills(bill_no, created_at, customer, payment_method, subtotal, discount, total, paid, balance, payment_status, paper_cost, profit, notes)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (bill_no, now_iso, customer, payment, subtotal, discount, total, paid, balance, payment_status, total_bill_paper_cost, bill_profit, notes)
                )
                bill_id = cur.fetchone()["id"]
                cur.execute("RELEASE SAVEPOINT sp_bill_form_insert")
            except psycopg2.IntegrityError:
                cur.execute("ROLLBACK TO SAVEPOINT sp_bill_form_insert")
                bill_no = f"IR{ist_now.strftime('%y%m%d%H%M%S')}{ist_now.microsecond // 1000:03d}"
                cur.execute(
                    """INSERT INTO bills(bill_no, created_at, customer, payment_method, subtotal, discount, total, paid, balance, payment_status, paper_cost, profit, notes)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (bill_no, now_iso, customer, payment, subtotal, discount, total, paid, balance, payment_status, total_bill_paper_cost, bill_profit, notes)
                )
                bill_id = cur.fetchone()["id"]

            # Record initial payment in bill_payments if paid > 0
            if paid > 0:
                cur.execute("""
                    INSERT INTO bill_payments(bill_id, amount, payment_method, recorded_by, notes, created_at)
                    VALUES(%s, %s, %s, %s, 'Initial bill payment', %s)
                """, (bill_id, paid, payment, 'Admin' if session.get('is_admin') else 'Staff', now_iso))

            # Batch Insert Bill Items
            item_tuples = [
                (bill_id, x["service_name"], x["print_type"], x["paper_size"], x["quantity"], x["pages_per_copy"],
                 x["sides"], x["rate"], x["line_total"], x["paper_sheets"], x["color_units"], x["paper_cost"], x["profit"], x.get("inventory_id"))
                for x in items
            ]
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO bill_items(bill_id, service_name, print_type, paper_size, quantity, pages_per_copy, sides, rate, line_total, paper_sheets, color_units, paper_cost, profit, inventory_id)
                   VALUES %s""",
                item_tuples
            )

            # Batch Automatic Paper Stock Deduction & Ledger Recording
            sheets_by_inv = {}
            for x in items:
                inv_id = x.get("inventory_id")
                sheets_used = x.get("paper_sheets", 0)
                if inv_id and sheets_used > 0:
                    sheets_by_inv[inv_id] = sheets_by_inv.get(inv_id, 0) + sheets_used

            if sheets_by_inv:
                inv_ids = list(sheets_by_inv.keys())
                cur.execute("SELECT id, available_sheets, item_name FROM inventory WHERE id = ANY(%s) FOR UPDATE", (inv_ids,))
                locked_inv = {r['id']: r for r in cur.fetchall()}

                inv_updates = []
                movements = []
                for inv_id, sheets_used in sheets_by_inv.items():
                    if inv_id in locked_inv:
                        new_avail = max(0, locked_inv[inv_id]['available_sheets'] - sheets_used)
                        inv_updates.append((new_avail, now_iso, inv_id))
                        desc_parts = [f"{x['service_name']} ({x['sides']})" for x in items if x.get("inventory_id") == inv_id]
                        desc = f"Billed: {', '.join(desc_parts[:3])}" if desc_parts else "Billed items"
                        movements.append((inv_id, 'SALE', -sheets_used, new_avail, bill_no, desc, now_iso))

                if inv_updates:
                    psycopg2.extras.execute_batch(
                        cur,
                        "UPDATE inventory SET available_sheets=%s, updated_at=%s WHERE id=%s",
                        inv_updates
                    )
                if movements:
                    psycopg2.extras.execute_values(
                        cur,
                        """INSERT INTO stock_movements (item_id, movement_type, quantity, balance_after, reference_id, notes, created_at)
                           VALUES %s""",
                        movements
                    )

        conn.commit()

    return redirect(url_for("receipt", bill_id=bill_id))

@app.route("/receipt/<int:bill_id>")
def receipt(bill_id):
    auto_print = (request.args.get("auto") == "1")
    is_admin = bool(session.get("is_admin"))
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bills WHERE id=%s", (bill_id,))
            bill = cur.fetchone()
            if not bill:
                return "Bill not found", 404
            cur.execute("SELECT * FROM bill_items WHERE bill_id=%s ORDER BY id ASC", (bill_id,))
            items = cur.fetchall()
            cur.execute("SELECT * FROM bill_payments WHERE bill_id=%s ORDER BY id ASC", (bill_id,))
            payments = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS c FROM bill_audit_log WHERE (bill_id=%s OR bill_no=%s) AND action='EDIT'", (bill_id, bill["bill_no"]))
            edit_count = cur.fetchone()["c"]
    return render_template("receipt.html", bill=bill, items=items, payments=payments, auto_print=auto_print, is_admin=is_admin, edit_count=edit_count)

# ── API: Service Catalog Endpoint ──
@app.route("/api/services", methods=["GET"])
@token_required
def api_get_services():
    services = get_cached_services()["active_list"]
    return jsonify({"success": True, "services": services})

# ── API: High-Speed Billing Endpoint (Instant Save & Print / Mobile App) ──
@app.post("/api/create-bill")
@token_required
def create_bill_api():
    try:
        user_data = getattr(request, "current_user", {})
        user_name = user_data.get("name") or "Admin"
        
        data = request.get_json(force=True) or {}
        client_tx_id = (data.get("client_tx_id") or "").strip()
        customer = (data.get("customer") or "Walk-in Customer").strip()
        payment = (data.get("payment_method") or "Cash").strip()
        discount = money(data.get("discount", 0))
        paid_input = str(data.get("paid", "")).strip()
        req_status = (data.get("payment_status") or "").strip()
        action = (data.get("action") or "save_only").strip().lower()
        notes = (data.get("notes") or "").strip()
        raw_items = data.get("items") or []

        # Idempotency check: if client_tx_id was already processed, return existing bill without duplicate creation
        if client_tx_id:
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, bill_no, subtotal, discount, total, paid, balance, payment_status, created_at
                        FROM bills
                        WHERE client_tx_id = %s AND is_deleted = 0
                    """, (client_tx_id,))
                    existing = cur.fetchone()
                    if existing:
                        cur.execute("SELECT job_id, status, thermal_width, attempts FROM print_jobs WHERE bill_id=%s ORDER BY id DESC LIMIT 1", (existing["id"],))
                        pj = cur.fetchone()
                        dash_stats = get_today_dashboard_stats()
                        return jsonify({
                            "ok": True,
                            "success": True,
                            "bill_id": existing["id"],
                            "bill_no": existing["bill_no"],
                            "subtotal": existing["subtotal"],
                            "discount": existing["discount"],
                            "total": existing["total"],
                            "paid": existing["paid"],
                            "balance": existing["balance"],
                            "payment_status": existing["payment_status"],
                            "action": action,
                            "print_job": pj,
                            "receipt_url": url_for("receipt", bill_id=existing["id"]),
                            "today_count": dash_stats["today_count"],
                            "today_total": dash_stats["today_total"],
                            "today_total_formatted": dash_stats["today_total_formatted"],
                            "is_duplicate_prevented": True
                        })

        if not raw_items:
            return jsonify({"success": False, "error": "Cart is empty."}), 400

        items = []
        subtotal = 0.0
        total_bill_paper_cost = 0.0
        cached_services = get_cached_services()

        with db() as conn:
            with conn.cursor() as cur:
                # Pre-fetch active inventory cost lookup
                cur.execute("""
                SELECT id, item_name, size_spec, available_sheets, 
                       ROUND((cost / NULLIF(total_sheets,0))::numeric, 4) AS cost_per_sheet
                FROM inventory
                WHERE is_active = 1
                """)
                inv_rows = cur.fetchall()
                inv_map = {r['id']: float(r['cost_per_sheet'] or 0.0) for r in inv_rows}
                inv_by_name = {r['item_name'].strip().lower(): (r['id'], float(r['cost_per_sheet'] or 0.0)) for r in inv_rows}
                inv_by_size = {}
                for r in inv_rows:
                    key = (r['size_spec'] or '').strip().upper()
                    if key and key not in inv_by_size:
                        inv_by_size[key] = (r['id'], float(r['cost_per_sheet'] or 0.0))

                for it in raw_items:
                    s_id = str(it.get("service_id", "")).strip()
                    try:
                        qty = max(1, int(it.get("qty") or it.get("quantity") or 1))
                        pages_per_copy = max(1, int(it.get("pages") or it.get("pages_per_copy") or 1))
                        rate = money(it.get("rate", 0))
                    except (ValueError, TypeError):
                        continue

                    sides = it.get("sides") or "Single"
                    is_double = sides.lower().startswith("double")

                    service = None
                    if s_id and s_id != 'custom':
                        try:
                            service = cached_services['by_id'].get(int(s_id))
                        except (ValueError, TypeError):
                            pass

                    if not service:
                        s_raw_name = (it.get("service_name") or it.get("name") or "").strip()
                        if s_raw_name:
                            clean_s_name = s_raw_name.lower().replace('—', '-')
                            service = cached_services['by_name'].get(clean_s_name)

                    if service:
                        s_name = service["name"]
                        p_type = service["print_type"]
                        p_size = service["paper_size"]
                        paper_id = service.get("paper_id")
                        sheets_per_unit = service.get("sheets_per_unit", 1)
                    else:
                        s_name = (it.get("service_name") or it.get("name") or "Custom Service").strip()
                        p_type = "service"
                        p_size = "A4"
                        paper_id = None
                        sheets_per_unit = 1

                    # Physical sheets: 1 copy = 1 physical sheet for both single-side and double-side jobs
                    if sheets_per_unit == 0:
                        sheets = 0
                    else:
                        sheets = qty * pages_per_copy

                    # Line total & rate calculation:
                    # Supports universal custom rate override for ALL items and categories
                    is_custom_rate = bool(it.get("is_custom_rate") or it.get("has_custom_rate") or it.get("custom_rate"))
                    user_rate = it.get("rate")
                    has_user_rate = (user_rate is not None and str(user_rate).strip() != "")

                    if has_user_rate:
                        custom_rate_val = money(max(0.0, float(user_rate)))
                        if is_custom_rate:
                            rate = custom_rate_val
                            line_total = money(qty * pages_per_copy * rate)
                        elif service and service.get("extra_copy_rate") is not None and float(service.get("extra_copy_rate") or 0) > 0:
                            first_copy = float(service["double_rate"] if (is_double and service.get("double_rate") is not None) else service["rate"])
                            extra_copy = float(service["extra_copy_rate"])
                            default_total = money(first_copy + max(0, qty - 1) * extra_copy)
                            default_rate = money(default_total / qty)
                            if custom_rate_val != default_rate:
                                rate = custom_rate_val
                                line_total = money(qty * pages_per_copy * rate)
                            else:
                                line_total = default_total
                                rate = default_rate
                        else:
                            standard_unit = float(service["double_rate"] if (service and is_double and service.get("double_rate") is not None) else (service["rate"] if service else 0.0))
                            if custom_rate_val != money(standard_unit) or is_custom_rate:
                                rate = custom_rate_val
                                line_total = money(qty * pages_per_copy * rate)
                            else:
                                rate = money(standard_unit)
                                line_total = money(qty * pages_per_copy * rate)
                    elif it.get("line_total") is not None and str(it.get("line_total")).strip() != "":
                        line_total = money(it.get("line_total"))
                        rate = money(line_total / (qty * pages_per_copy)) if (qty * pages_per_copy) > 0 else 0.0
                    else:
                        unit_rate = float(service["double_rate"] if (service and is_double and service.get("double_rate") is not None) else (service["rate"] if service else 0.0))
                        line_total = money(qty * pages_per_copy * unit_rate)
                        rate = money(unit_rate)

                    color_units = qty * pages_per_copy if p_type in ("color", "photo") else 0

                    unit_cost = 0.0
                    matched_inv_id = paper_id
                    if matched_inv_id and matched_inv_id in inv_map:
                        unit_cost = inv_map[matched_inv_id]
                    elif s_name.lower() in inv_by_name:
                        matched_inv_id, unit_cost = inv_by_name[s_name.lower()]
                    else:
                        size_key = (p_size or '').strip().upper()
                        if size_key in inv_by_size and sheets > 0:
                            matched_inv_id, unit_cost = inv_by_size[size_key]

                    line_paper_cost = money(sheets * unit_cost) if sheets > 0 else 0.0
                    line_profit = money(line_total - line_paper_cost)
                    total_bill_paper_cost += line_paper_cost

                    items.append({
                        "service_name": s_name,
                        "print_type": p_type,
                        "paper_size": p_size,
                        "quantity": qty,
                        "pages_per_copy": pages_per_copy,
                        "sides": sides,
                        "rate": rate,
                        "line_total": line_total,
                        "paper_sheets": sheets,
                        "color_units": color_units,
                        "paper_cost": line_paper_cost,
                        "profit": line_profit,
                        "inventory_id": matched_inv_id
                    })
                    subtotal += line_total

                if not items:
                    return jsonify({"success": False, "error": "No valid items in bill."}), 400

                subtotal = money(subtotal)
                discount = min(max(discount, 0), subtotal)
                total = money(subtotal - discount)
                if req_status.lower() == "unpaid":
                    paid = 0.0
                    balance = total
                    payment_status = "Unpaid"
                elif req_status.lower() == "paid":
                    paid = total
                    balance = 0.0
                    payment_status = "Paid"
                else:
                    if paid_input == "":
                        paid = total
                    else:
                        paid = min(max(money(paid_input), 0), total)
                    balance = money(total - paid)
                    if paid <= 0.001:
                        payment_status = "Unpaid"
                    elif balance <= 0.001:
                        payment_status = "Paid"
                    else:
                        payment_status = "Partially Paid"

                total_bill_paper_cost = money(total_bill_paper_cost)
                bill_profit = money(total - total_bill_paper_cost)

                now_iso = to_utc_iso()
                ist_now = get_ist_now()
                bill_no = "IR" + ist_now.strftime("%y%m%d%H%M%S")

                # Insert bill with atomic savepoint to guarantee uniqueness with zero pre-query latency
                cur.execute("SAVEPOINT sp_bill_insert")
                try:
                    cur.execute(
                        """INSERT INTO bills(bill_no, created_at, customer, payment_method, subtotal, discount, total, paid, balance, payment_status, paper_cost, profit, notes, biller_name, original_created_at, client_tx_id)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (bill_no, now_iso, customer, payment, subtotal, discount, total, paid, balance, payment_status, total_bill_paper_cost, bill_profit, notes, user_name, now_iso, client_tx_id or None)
                    )
                    bill_id = cur.fetchone()["id"]
                    cur.execute("RELEASE SAVEPOINT sp_bill_insert")
                except psycopg2.IntegrityError:
                    cur.execute("ROLLBACK TO SAVEPOINT sp_bill_insert")
                    bill_no = f"IR{ist_now.strftime('%y%m%d%H%M%S')}{ist_now.microsecond // 1000:03d}"
                    cur.execute(
                        """INSERT INTO bills(bill_no, created_at, customer, payment_method, subtotal, discount, total, paid, balance, payment_status, paper_cost, profit, notes, biller_name, original_created_at, client_tx_id)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (bill_no, now_iso, customer, payment, subtotal, discount, total, paid, balance, payment_status, total_bill_paper_cost, bill_profit, notes, user_name, now_iso, client_tx_id or None)
                    )
                    bill_id = cur.fetchone()["id"]

                # Record initial payment in bill_payments if paid > 0
                if paid > 0:
                    cur.execute("""
                        INSERT INTO bill_payments(bill_id, amount, payment_method, recorded_by, notes, created_at)
                        VALUES(%s, %s, %s, %s, 'Initial bill payment', %s)
                    """, (bill_id, paid, payment, user_name, now_iso))

                # High-speed batch insert of bill items (1 execute_values call)
                item_tuples = [
                    (bill_id, x["service_name"], x["print_type"], x["paper_size"], x["quantity"], x["pages_per_copy"],
                     x["sides"], x["rate"], x["line_total"], x["paper_sheets"], x["color_units"], x["paper_cost"], x["profit"], x["inventory_id"])
                    for x in items
                ]
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO bill_items(bill_id, service_name, print_type, paper_size, quantity, pages_per_copy, sides, rate, line_total, paper_sheets, color_units, paper_cost, profit, inventory_id)
                       VALUES %s""",
                    item_tuples
                )

                # High-speed batch inventory deduction & stock movements
                sheets_by_inv = {}
                for x in items:
                    inv_id = x.get("inventory_id")
                    sheets_used = x.get("paper_sheets", 0)
                    if inv_id and sheets_used > 0:
                        sheets_by_inv[inv_id] = sheets_by_inv.get(inv_id, 0) + sheets_used

                if sheets_by_inv:
                    inv_ids = list(sheets_by_inv.keys())
                    cur.execute("SELECT id, available_sheets FROM inventory WHERE id = ANY(%s) FOR UPDATE", (inv_ids,))
                    locked_inv = {r['id']: r['available_sheets'] for r in cur.fetchall()}

                    inv_updates = []
                    movements_to_insert = []
                    for inv_id, sheets_used in sheets_by_inv.items():
                        if inv_id in locked_inv:
                            new_avail = max(0, locked_inv[inv_id] - sheets_used)
                            inv_updates.append((new_avail, now_iso, inv_id))
                            desc_parts = [f"{x['service_name']} ({x['sides']})" for x in items if x.get("inventory_id") == inv_id]
                            desc = f"Billed: {', '.join(desc_parts[:3])}" if desc_parts else "Billed items"
                            movements_to_insert.append((inv_id, 'SALE', -sheets_used, new_avail, bill_no, desc, now_iso, user_name))

                    if inv_updates:
                        psycopg2.extras.execute_batch(
                            cur,
                            "UPDATE inventory SET available_sheets=%s, updated_at=%s WHERE id=%s",
                            inv_updates
                        )
                    if movements_to_insert:
                        psycopg2.extras.execute_values(
                            cur,
                            """INSERT INTO stock_movements (item_id, movement_type, quantity, balance_after, reference_id, notes, created_at, recorded_by)
                               VALUES %s""",
                            movements_to_insert
                        )

                # PC Wi-Fi Print queueing if save_and_print
                print_job_info = None
                if action == "save_and_print":
                    cur.execute("SELECT value FROM app_settings WHERE key='thermal_width'")
                    w_row = cur.fetchone()
                    thermal_width = w_row["value"] if w_row else "80mm"
                    
                    cur.execute("SELECT value FROM app_settings WHERE key='default_printer'")
                    p_row = cur.fetchone()
                    printer_name = p_row["value"] if p_row else "__SYSTEM_DEFAULT__"
                    
                    bill_dict = {
                        "bill_no": bill_no,
                        "created_at": now_iso,
                        "customer": customer,
                        "payment_method": payment,
                        "payment_status": payment_status,
                        "subtotal": subtotal,
                        "discount": discount,
                        "total": total,
                        "paid": paid,
                        "balance": balance
                    }
                    receipt_text = format_thermal_receipt(bill_dict, items, thermal_width=thermal_width, cashier=user_name)
                    job_id = f"PJ{ist_now.strftime('%y%m%d%H%M%S')}_{bill_id}"
                    
                    cur.execute("""
                    INSERT INTO print_jobs (job_id, bill_id, bill_no, status, printer_name, thermal_width, receipt_text, printed_by, created_at, updated_at)
                    VALUES (%s, %s, %s, 'Print Pending', %s, %s, %s, %s, %s, %s)
                    """, (job_id, bill_id, bill_no, printer_name, thermal_width, receipt_text, user_name, now_iso, now_iso))
                    
                    print_job_info = {
                        "job_id": job_id,
                        "status": "Print Pending",
                        "thermal_width": thermal_width,
                        "attempts": 0
                    }

                # Query updated today dashboard figures using index range scan on the same connection
                today_str = get_ist_today_str()
                start_utc_iso, end_utc_iso = ist_dates_to_utc_range(today_str, today_str)
                cur.execute("""
                    SELECT COALESCE(SUM(total), 0) AS today_total,
                           COUNT(*) AS today_count
                    FROM bills 
                    WHERE created_at >= %s AND created_at < %s 
                      AND is_deleted = 0
                """, (start_utc_iso, end_utc_iso))
                dash_row = cur.fetchone()
                today_count = int(dash_row["today_count"] if dash_row else 1)
                today_total = float(dash_row["today_total"] if dash_row else total)

            conn.commit()

        receipt_url = url_for("receipt", bill_id=bill_id)
        return jsonify({
            "ok": True,
            "success": True,
            "bill_id": bill_id,
            "bill_no": bill_no,
            "created_at_utc": now_iso,
            "created_at_ist": format_ist_datetime_str(now_iso),
            "created_date_ist": format_ist_date_str(now_iso),
            "created_time_ist": format_ist_datetime_str(now_iso, fmt="%H:%M:%S"),
            "subtotal": subtotal,
            "discount": discount,
            "total": total,
            "paid": paid,
            "balance": balance,
            "payment_status": payment_status,
            "action": action,
            "print_job": print_job_info,
            "receipt_url": receipt_url,
            "today_count": today_count,
            "today_total": today_total,
            "today_total_formatted": inr(today_total)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

# ── API: Print Job Status & Retry ──
@app.route("/api/print-jobs/<job_id>", methods=["GET"])
@token_required
def api_get_print_job(job_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            SELECT job_id, bill_id, bill_no, status, printer_name, thermal_width, 
                   attempts, error_message, printed_by, created_at, updated_at
            FROM print_jobs WHERE job_id=%s
            """, (job_id,))
            job = cur.fetchone()
            if not job:
                return jsonify({"success": False, "error": "Print job not found."}), 404
    return jsonify({"success": True, "job": job})

@app.route("/api/print-jobs/<job_id>/retry", methods=["POST"])
@token_required
def api_retry_print_job(job_id):
    now = to_utc_iso()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, attempts FROM print_jobs WHERE job_id=%s", (job_id,))
            job = cur.fetchone()
            if not job:
                return jsonify({"success": False, "error": "Print job not found."}), 404
            cur.execute("""
            UPDATE print_jobs
            SET status = 'Print Pending', error_message = '', updated_at = %s
            WHERE job_id = %s
            RETURNING job_id, bill_id, bill_no, status, attempts, error_message, updated_at
            """, (now, job_id))
            updated_job = cur.fetchone()
            conn.commit()
    return jsonify({"success": True, "job": updated_job})

# ── API: Staff Sales Summary (Strictly No Cost or Profit) ──
@app.route("/api/staff/sales", methods=["GET"])
@token_required
def api_staff_sales():
    today_str = get_ist_today_str()
    start_utc_iso, end_utc_iso = ist_dates_to_utc_range(today_str, today_str)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            SELECT COUNT(*) AS count, COALESCE(SUM(total), 0) AS total_sales
            FROM bills
            WHERE is_deleted = 0 
              AND created_at >= %s AND created_at < %s
            """, (start_utc_iso, end_utc_iso))
            row = cur.fetchone()
            today_count = int(row["count"] or 0)
            today_sales = float(row["total_sales"] or 0.0)

            cur.execute("""
            SELECT id, bill_no, created_at, customer, subtotal, discount, total, 
                   paid, balance, payment_status, payment_method, biller_name
            FROM bills
            WHERE is_deleted = 0
            ORDER BY id DESC
            LIMIT 50
            """)
            raw_bills = cur.fetchall()
            bills = []
            for b in raw_bills:
                b_dict = dict(b)
                b_dict["created_at_utc"] = b_dict.get("created_at")
                b_dict["created_at_ist"] = format_ist_datetime_str(b_dict.get("created_at"))
                b_dict["created_date_ist"] = format_ist_date_str(b_dict.get("created_at"))
                b_dict["created_at"] = format_ist_datetime_str(b_dict.get("created_at"))
                bills.append(b_dict)

    return jsonify({
        "success": True,
        "today_date": today_str,
        "today_sales": today_sales,
        "today_bill_count": today_count,
        "bills": bills
    })

# ── API: Staff Stock View (Strictly No Cost or Purchase Price) ──
@app.route("/api/staff/stock", methods=["GET"])
@token_required
def api_staff_stock():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            SELECT id, item_name, category, size_spec, bundles, sheets_per_bundle,
                   total_sheets, available_sheets, reorder_level
            FROM inventory
            WHERE is_active = 1
            ORDER BY category, item_name
            """)
            rows = cur.fetchall()
            items = []
            for r in rows:
                avail = int(r["available_sheets"] or 0)
                reorder = int(r["reorder_level"] or 0)
                items.append({
                    "id": r["id"],
                    "item_name": r["item_name"],
                    "category": r["category"],
                    "size_spec": r["size_spec"],
                    "bundles": r["bundles"],
                    "sheets_per_bundle": r["sheets_per_bundle"],
                    "total_sheets": r["total_sheets"],
                    "available_sheets": avail,
                    "reorder_level": reorder,
                    "is_low_stock": (avail <= reorder)
                })

    return jsonify({"success": True, "items": items})

# ── API: Staff Stock Addition (Staff & Admin) ──
@app.post("/api/staff/stock/add")
@token_required
def api_staff_stock_add():
    try:
        data = request.get_json(force=True) or {}
        item_id = int(data.get("item_id") or 0)
        quantity = int(data.get("quantity") or 0)
        reason = (data.get("reason") or "").strip()

        if item_id <= 0:
            return jsonify({"success": False, "error": "Valid inventory item must be selected."}), 400
        if quantity <= 0:
            return jsonify({"success": False, "error": "Quantity must be greater than zero."}), 400
        if not reason:
            return jsonify({"success": False, "error": "Please provide a reason for adding stock."}), 400

        user = getattr(request, "current_user", {})
        user_name = user.get("name") or "Staff Counter"
        today_iso = get_ist_today_str()

        with db() as conn:
            with conn.cursor() as cur:
                item_name, old_bal, new_bal, change, m_type = process_stock_adjustment(
                    cur, item_id, "ADD", quantity, today_iso, reason, user_name=user_name
                )
            conn.commit()

        return jsonify({
            "success": True,
            "item_id": item_id,
            "item_name": item_name,
            "previous_balance": old_bal,
            "new_balance": new_bal,
            "quantity_added": quantity,
            "message": f"Successfully added {quantity} sheets to '{item_name}'. New balance: {new_bal} sheets."
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

# ── API: PC Print Service Endpoints ──
@app.route("/api/printer/heartbeat", methods=["POST"])
@printer_service_required
def api_printer_heartbeat():
    data = request.get_json(silent=True) or {}
    now = to_utc_iso()
    info = {
        "hostname": (data.get("hostname") or "Unknown").strip(),
        "os": (data.get("os") or "Unknown").strip(),
        "printer_name": (data.get("printer_name") or "").strip(),
        "version": (data.get("version") or "1.0").strip(),
        "last_seen": now
    }
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ('pc_print_service_status', 'online', %s)
            ON CONFLICT (key) DO UPDATE SET value='online', updated_at=EXCLUDED.updated_at
            """, (now,))
            cur.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ('pc_print_service_last_seen', %s, %s)
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at
            """, (now, now))
            cur.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ('pc_print_service_info', %s, %s)
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at
            """, (json.dumps(info), now))
            conn.commit()
    return jsonify({"success": True, "status": "online", "timestamp": now})

@app.route("/api/printer/pending-jobs", methods=["GET"])
@printer_service_required
def api_printer_pending_jobs():
    now = to_utc_iso()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            SELECT id, job_id, bill_id, bill_no, status, printer_name, thermal_width, 
                   receipt_text, attempts, created_at
            FROM print_jobs
            WHERE status = 'Print Pending'
            ORDER BY id ASC
            LIMIT 5
            FOR UPDATE SKIP LOCKED
            """)
            jobs = cur.fetchall()
            for j in jobs:
                cur.execute("""
                UPDATE print_jobs
                SET status = 'Printing', updated_at = %s
                WHERE id = %s
                """, (now, j["id"]))
            conn.commit()
    return jsonify({"success": True, "jobs": jobs})

@app.route("/api/printer/jobs/<job_id>/status", methods=["POST"])
@printer_service_required
def api_printer_update_job_status(job_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if new_status not in ("Printed", "Print Failed", "Print Pending", "Printing"):
        return jsonify({"success": False, "error": "Invalid status."}), 400
    
    error_msg = (data.get("error_message") or data.get("error") or "").strip()
    printer_name = (data.get("printer_name") or "").strip()
    now = to_utc_iso()
    
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, attempts FROM print_jobs WHERE job_id=%s", (job_id,))
            job = cur.fetchone()
            if not job:
                return jsonify({"success": False, "error": "Job not found."}), 404
            
            attempts = job["attempts"] + 1 if new_status in ("Printed", "Print Failed") else job["attempts"]
            update_fields = ["status = %s", "attempts = %s", "updated_at = %s"]
            params = [new_status, attempts, now]
            
            if error_msg:
                update_fields.append("error_message = %s")
                params.append(error_msg)
            elif new_status == "Printed":
                update_fields.append("error_message = ''")
                
            if printer_name:
                update_fields.append("printer_name = %s")
                params.append(printer_name)
                
            params.append(job_id)
            cur.execute(f"UPDATE print_jobs SET {', '.join(update_fields)} WHERE job_id = %s", tuple(params))
            conn.commit()
            
    return jsonify({"success": True, "job_id": job_id, "status": new_status})

@app.route("/api/printer/status", methods=["GET"])
@token_required
def api_printer_status():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT key, value FROM app_settings WHERE key IN ('default_printer', 'thermal_width', 'printer_api_key', 'pc_print_service_last_seen', 'pc_print_service_info')")
            settings = {r["key"]: r["value"] for r in cur.fetchall()}
            
            last_seen_str = settings.get("pc_print_service_last_seen", "")
            is_online = False
            if last_seen_str:
                try:
                    last_seen_dt = to_ist_datetime(last_seen_str)
                    if last_seen_dt and (get_ist_now() - last_seen_dt).total_seconds() <= 35:
                        is_online = True
                except Exception:
                    pass
            
            pc_info = {}
            if settings.get("pc_print_service_info"):
                try:
                    pc_info = json.loads(settings["pc_print_service_info"])
                except Exception:
                    pass
            
            cur.execute("SELECT COUNT(*) AS c FROM print_jobs WHERE status = 'Print Pending'")
            pending_count = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM print_jobs WHERE status = 'Print Failed'")
            failed_count = cur.fetchone()["c"]

    user = getattr(request, "current_user", {})
    is_admin_user = (user.get("role") == "admin")
            
    res_data = {
        "success": True,
        "is_online": is_online,
        "status": "online" if is_online else "offline",
        "last_seen": last_seen_str,
        "default_printer": settings.get("default_printer", "__SYSTEM_DEFAULT__"),
        "thermal_width": settings.get("thermal_width", "80mm"),
        "pc_info": pc_info,
        "pending_count": pending_count,
        "failed_count": failed_count
    }
    if is_admin_user:
        res_data["printer_api_key"] = settings.get("printer_api_key", "iread-print-token-2026")
    return jsonify(res_data)

@app.route("/api/printer/test-print", methods=["POST"])
@admin_api_required
def api_printer_test_print():
    ist_dt = get_ist_now()
    now_iso = to_utc_iso()
    job_id = f"PJ_TEST_{ist_dt.strftime('%y%m%d%H%M%S')}"
    
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM app_settings WHERE key='thermal_width'")
            w_row = cur.fetchone()
            thermal_width = w_row["value"] if w_row else "80mm"
            
            cur.execute("SELECT value FROM app_settings WHERE key='default_printer'")
            p_row = cur.fetchone()
            printer_name = p_row["value"] if p_row else "__SYSTEM_DEFAULT__"
            
            test_bill = {
                "bill_no": "TEST-SLIP",
                "created_at": now_iso,
                "customer": "PC Print Service Test",
                "payment_method": "Wi-Fi Spooler",
                "payment_status": "Verified",
                "subtotal": 0.0,
                "discount": 0.0,
                "total": 0.0,
                "paid": 0.0,
                "balance": 0.0
            }
            test_items = [
                {"service_name": "Wi-Fi Thermal Link", "sides": "Single", "quantity": 1, "rate": 0.0, "line_total": 0.0},
                {"service_name": "Pattern Test OK", "sides": "Single", "quantity": 1, "rate": 0.0, "line_total": 0.0}
            ]
            receipt_text = format_thermal_receipt(test_bill, test_items, thermal_width=thermal_width, cashier="Admin Test")
            
            cur.execute("""
            INSERT INTO print_jobs (job_id, bill_no, status, printer_name, thermal_width, receipt_text, printed_by, created_at, updated_at)
            VALUES (%s, 'TEST-SLIP', 'Print Pending', %s, %s, %s, 'Admin', %s, %s)
            """, (job_id, printer_name, thermal_width, receipt_text, now_iso, now_iso))
            conn.commit()
            
    return jsonify({
        "success": True,
        "job_id": job_id,
        "status": "Print Pending",
        "message": "Test print queued for PC Print Service."
    })

# ── Printer Configuration & Test Route (Admin) ──
@app.route("/printer-settings", methods=["GET", "POST"])
@admin_required
def printer_settings_page():
    with db() as conn:
        with conn.cursor() as cur:
            now = to_utc_iso()
            if request.method == "POST":
                action = request.form.get("action")
                if action == "save_printer":
                    p_name = request.form.get("printer_name", "").strip()
                    p_width = request.form.get("thermal_width", "80mm").strip()
                    cur.execute("""
                    INSERT INTO app_settings (key, value, updated_at) 
                    VALUES ('default_printer', %s, %s)
                    ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at
                    """, (p_name, now))
                    cur.execute("""
                    INSERT INTO app_settings (key, value, updated_at) 
                    VALUES ('thermal_width', %s, %s)
                    ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at
                    """, (p_width, now))
                    conn.commit()
                    flash(f"Printer configuration saved: {p_name} ({p_width}).", "success")
                    return redirect(url_for("printer_settings_page"))

                elif action == "regenerate_api_key":
                    import secrets
                    new_token = f"iread-{secrets.token_hex(12)}"
                    cur.execute("""
                    INSERT INTO app_settings (key, value, updated_at)
                    VALUES ('printer_api_key', %s, %s)
                    ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at
                    """, (new_token, now))
                    conn.commit()
                    flash("New PC Print Service API Token generated successfully.", "success")
                    return redirect(url_for("printer_settings_page"))

                elif action == "test_print_pc":
                    job_id = f"PJ_TEST_{get_ist_now().strftime('%y%m%d%H%M%S')}"
                    cur.execute("SELECT value FROM app_settings WHERE key='thermal_width'")
                    w_row = cur.fetchone()
                    t_width = w_row["value"] if w_row else "80mm"
                    cur.execute("SELECT value FROM app_settings WHERE key='default_printer'")
                    p_row = cur.fetchone()
                    pr_name = p_row["value"] if p_row else "__SYSTEM_DEFAULT__"

                    test_bill = {
                        "bill_no": "TEST-PRINT",
                        "created_at": now,
                        "customer": "Admin Console Test",
                        "payment_method": "PC Wi-Fi Service",
                        "payment_status": "Verified",
                        "subtotal": 0.0,
                        "discount": 0.0,
                        "total": 0.0,
                        "paid": 0.0,
                        "balance": 0.0
                    }
                    test_items = [
                        {"service_name": "Wi-Fi Thermal Printer", "sides": "Single", "quantity": 1, "rate": 0.0, "line_total": 0.0},
                        {"service_name": "Test Pattern OK", "sides": "Single", "quantity": 1, "rate": 0.0, "line_total": 0.0}
                    ]
                    receipt_text = format_thermal_receipt(test_bill, test_items, thermal_width=t_width, cashier="Admin")
                    cur.execute("""
                    INSERT INTO print_jobs (job_id, bill_no, status, printer_name, thermal_width, receipt_text, printed_by, created_at, updated_at)
                    VALUES (%s, 'TEST-PRINT', 'Print Pending', %s, %s, %s, 'Admin', %s, %s)
                    """, (job_id, pr_name, t_width, receipt_text, now, now))
                    conn.commit()
                    flash(f"Test print job queued (Job ID: {job_id}). PC Print Service will process it.", "info")
                    return redirect(url_for("printer_settings_page"))

            cur.execute("SELECT value FROM app_settings WHERE key='default_printer'")
            p_row = cur.fetchone()
            current_printer = p_row['value'] if p_row else '__SYSTEM_DEFAULT__'

            cur.execute("SELECT value FROM app_settings WHERE key='thermal_width'")
            w_row = cur.fetchone()
            thermal_width = w_row['value'] if w_row else '80mm'

            cur.execute("SELECT value FROM app_settings WHERE key='printer_api_key'")
            k_row = cur.fetchone()
            printer_api_key = k_row['value'] if k_row else 'iread-print-token-2026'

            cur.execute("SELECT value FROM app_settings WHERE key='pc_print_service_last_seen'")
            ls_row = cur.fetchone()
            last_seen_str = ls_row['value'] if ls_row else ''

            cur.execute("SELECT value FROM app_settings WHERE key='pc_print_service_info'")
            info_row = cur.fetchone()
            pc_info = {}
            if info_row and info_row['value']:
                try:
                    pc_info = json.loads(info_row['value'])
                except Exception:
                    pass

            is_online = False
            if last_seen_str:
                try:
                    dt = to_ist_datetime(last_seen_str)
                    if dt and (get_ist_now() - dt).total_seconds() <= 35:
                        is_online = True
                except Exception:
                    pass

            cur.execute("SELECT * FROM print_jobs ORDER BY id DESC LIMIT 15")
            recent_jobs = cur.fetchall()

    # Discover available system printers via lpstat (if available on host)
    available_printers = []
    try:
        import subprocess
        out = subprocess.check_output(["lpstat", "-a"], stderr=subprocess.DEVNULL, timeout=2).decode("utf-8")
        for line in out.splitlines():
            parts = line.split()
            if parts:
                available_printers.append(parts[0])
    except Exception:
        pass

    return render_template(
        "printer_settings.html",
        current_printer=current_printer,
        thermal_width=thermal_width,
        available_printers=available_printers,
        printer_api_key=printer_api_key,
        pc_is_online=is_online,
        last_seen_str=last_seen_str,
        pc_info=pc_info,
        recent_jobs=recent_jobs
    )

def get_period_date_range(period, custom_start=None, custom_end=None):
    today = get_ist_today()
    if period == "today":
        return today.isoformat(), today.isoformat(), "Today"
    elif period == "yesterday":
        yest = today - timedelta(days=1)
        return yest.isoformat(), yest.isoformat(), "Yesterday"
    elif period == "last7":
        start = today - timedelta(days=6)
        return start.isoformat(), today.isoformat(), "Last 7 Days"
    elif period == "last30":
        start = today - timedelta(days=29)
        return start.isoformat(), today.isoformat(), "Last 30 Days"
    elif period == "this_month":
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat(), "This Month"
    elif period == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return first_prev.isoformat(), last_prev.isoformat(), "Last Month"
    elif period == "custom" and (custom_start or custom_end):
        s = custom_start or "2000-01-01"
        e = custom_end or today.isoformat()
        return s, e, "Custom Range"
    elif custom_start or custom_end:
        s = custom_start or "2000-01-01"
        e = custom_end or today.isoformat()
        return s, e, "Custom Range"
    return None, None, "All Time"

# ── Bill History (Accessible by Staff & Admin, Confidential Costs Hidden from Staff) ──
@app.route("/history")
def history():
    q = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "all").strip()
    period = request.args.get("period", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    is_admin = bool(session.get("is_admin"))

    start_d, end_d, period_label = get_period_date_range(period, start_date, end_date)
    if start_d and not start_date:
        start_date = start_d
    if end_d and not end_date:
        end_date = end_d

    with db() as conn:
        with conn.cursor() as cur:
            # Lifetime metrics (restricted to Admin in template)
            cur.execute("""
                SELECT COALESCE(SUM(total), 0) AS total_sales,
                       COALESCE(SUM(paid), 0) AS total_collected,
                       COALESCE(SUM(balance), 0) AS total_outstanding,
                       COUNT(CASE WHEN balance > 0.001 THEN 1 END) AS unpaid_count,
                       COUNT(*) AS total_count
                FROM bills
                WHERE is_deleted = 0
            """)
            lifetime_stats = cur.fetchone()

            query = "SELECT * FROM bills WHERE is_deleted = 0"
            params = []

            if q:
                query += " AND (bill_no ILIKE %s OR customer ILIKE %s)"
                params.extend([f"%{q}%", f"%{q}%"])

            if status_filter == "Paid":
                query += " AND payment_status = 'Paid'"
            elif status_filter == "Unpaid":
                query += " AND payment_status = 'Unpaid'"
            elif status_filter == "Partially Paid":
                query += " AND payment_status = 'Partially Paid'"

            start_utc_iso, end_utc_iso = ist_dates_to_utc_range(start_d, end_d)
            if start_utc_iso and end_utc_iso:
                query += " AND created_at >= %s AND created_at < %s"
                params.extend([start_utc_iso, end_utc_iso])
            elif start_utc_iso:
                query += " AND created_at >= %s"
                params.append(start_utc_iso)
            elif end_utc_iso:
                query += " AND created_at < %s"
                params.append(end_utc_iso)

            # Period stats for the filtered period & search
            cur.execute(f"""
                SELECT COUNT(*) AS total_bills,
                       COALESCE(SUM(total), 0) AS total_sales,
                       COALESCE(SUM(paid), 0) AS total_collected,
                       COALESCE(SUM(balance), 0) AS total_outstanding,
                       COUNT(CASE WHEN balance > 0.001 THEN 1 END) AS unpaid_count
                FROM ({query}) filtered_bills
            """, tuple(params))
            period_stats = cur.fetchone()

            cur.execute(query + " ORDER BY id DESC LIMIT 500", tuple(params))
            bills = cur.fetchall()

    return render_template(
        "history.html",
        bills=bills,
        q=q,
        status_filter=status_filter,
        period=period,
        start_date=start_date,
        end_date=end_date,
        period_label=period_label,
        stats=lifetime_stats,
        period_stats=period_stats,
        is_admin=is_admin
    )

# ── API: Collect Bill Payment (Staff & Admin) ──
@app.post("/api/bills/<int:bill_id>/pay")
def collect_bill_payment(bill_id):
    try:
        data = request.get_json(force=True) or {}
        new_amount = money(data.get("amount", 0))
        payment_method = data.get("payment_method") or "Cash"
        notes = (data.get("notes") or "").strip()
        recorded_by = "Admin" if session.get("is_admin") else "Staff"
        now_iso = to_utc_iso()

        if new_amount <= 0:
            return {"success": False, "error": "Payment amount must be greater than zero."}, 400

        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM bills WHERE id=%s AND is_deleted=0 FOR UPDATE", (bill_id,))
                bill = cur.fetchone()
                if not bill:
                    return {"success": False, "error": "Bill not found."}, 404

                cur_balance = money(bill["balance"])
                if new_amount > (cur_balance + 0.01):
                    return {
                        "success": False,
                        "error": f"Payment amount ({inr(new_amount)}) cannot exceed outstanding balance of {inr(cur_balance)}."
                    }, 400

                new_paid = money(bill["paid"] + new_amount)
                new_balance = max(0.0, money(bill["total"] - new_paid))
                new_status = "Paid" if new_balance <= 0.001 else "Partially Paid"

                cur.execute("""
                    UPDATE bills 
                    SET paid=%s, balance=%s, payment_status=%s 
                    WHERE id=%s
                """, (new_paid, new_balance, new_status, bill_id))

                cur.execute("""
                    INSERT INTO bill_payments (bill_id, amount, payment_method, recorded_by, notes, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (bill_id, new_amount, payment_method, recorded_by, notes, now_iso))

            conn.commit()

        return {
            "ok": True,
            "success": True,
            "bill_id": bill_id,
            "paid": new_paid,
            "balance": new_balance,
            "payment_status": new_status,
            "message": f"Payment of {inr(new_amount)} recorded successfully."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400

# ── API: Bill Payments History ──
@app.get("/api/bills/<int:bill_id>/payments")
def get_bill_payments(bill_id):
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM bills WHERE id=%s", (bill_id,))
                bill = cur.fetchone()
                if not bill:
                    return {"success": False, "error": "Bill not found"}, 404

                cur.execute("SELECT * FROM bill_payments WHERE bill_id=%s ORDER BY id ASC", (bill_id,))
                payments = cur.fetchall()
                formatted_payments = []
                for p in payments:
                    pd = dict(p)
                    pd["created_at_utc"] = pd.get("created_at")
                    pd["created_at_ist"] = format_ist_datetime_str(pd.get("created_at"))
                    pd["created_at"] = format_ist_datetime_str(pd.get("created_at"))
                    formatted_payments.append(pd)

        return {
            "success": True,
            "bill": {
                "id": bill["id"],
                "bill_no": bill["bill_no"],
                "total": bill["total"],
                "paid": bill["paid"],
                "balance": bill["balance"],
                "payment_status": bill.get("payment_status", "Paid")
            },
            "payments": formatted_payments
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400

# ── API: Bill Details (Items & Payments for Modal) ──
@app.get("/api/bills/<int:bill_id>/details")
def get_bill_details(bill_id):
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM bills WHERE id=%s", (bill_id,))
                bill = cur.fetchone()
                if not bill:
                    return {"success": False, "error": "Bill not found"}, 404

                cur.execute("SELECT * FROM bill_items WHERE bill_id=%s ORDER BY id ASC", (bill_id,))
                items = cur.fetchall()

                cur.execute("SELECT * FROM bill_payments WHERE bill_id=%s ORDER BY id ASC", (bill_id,))
                payments = cur.fetchall()

                bill_dict = dict(bill)
                bill_dict["created_at_utc"] = bill_dict.get("created_at")
                bill_dict["created_at"] = format_ist_datetime_str(bill_dict.get("created_at"))
                bill_dict["created_at_ist"] = bill_dict["created_at"]
                if bill_dict.get("original_created_at"):
                    bill_dict["original_created_at_ist"] = format_ist_datetime_str(bill_dict["original_created_at"])
                formatted_payments = []
                for p in payments:
                    pd = dict(p)
                    pd["created_at_utc"] = pd.get("created_at")
                    pd["created_at_ist"] = format_ist_datetime_str(pd.get("created_at"))
                    pd["created_at"] = format_ist_datetime_str(pd.get("created_at"))
                    formatted_payments.append(pd)

        return {
            "success": True,
            "bill": bill_dict,
            "items": items,
            "payments": formatted_payments,
            "is_admin": bool(session.get("is_admin"))
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400

# ── API: Delete Bill (Admin only with stock return) ──
@app.post("/api/bills/<int:bill_id>/delete")
@admin_api_required
def delete_bill(bill_id):
    try:
        data = request.get_json(silent=True) or {}
        reason = (data.get("reason") or "Deleted by admin").strip()
        now_iso = to_utc_iso()

        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM bills WHERE id=%s AND is_deleted=0 FOR UPDATE", (bill_id,))
                bill = cur.fetchone()
                if not bill:
                    return {"success": False, "error": "Bill not found or already deleted."}, 404

                cur.execute("SELECT * FROM bill_items WHERE bill_id=%s", (bill_id,))
                items = cur.fetchall()

                # Reconcile inventory stock: return used paper sheets back to inventory
                total_sheets_reversed = 0
                for it in items:
                    sheets = it.get("paper_sheets", 0)
                    if sheets > 0:
                        cur.execute("SELECT id, available_sheets FROM inventory WHERE size_spec ILIKE %s LIMIT 1", (it["paper_size"],))
                        target_inv = cur.fetchone()
                        if target_inv:
                            new_bal = target_inv["available_sheets"] + sheets
                            cur.execute("UPDATE inventory SET available_sheets=%s, updated_at=%s WHERE id=%s", (new_bal, now_iso, target_inv["id"]))
                            cur.execute("""
                            INSERT INTO stock_movements (item_id, movement_type, quantity, balance_after, reference_id, notes, created_at)
                            VALUES (%s, 'RETURN', %s, %s, %s, %s, %s)
                            """, (target_inv["id"], sheets, new_bal, bill["bill_no"], f"Reversed: Bill {bill['bill_no']} deleted", now_iso))
                            total_sheets_reversed += sheets

                # Mark bill as deleted (soft delete preserving financial audit records)
                cur.execute("""
                    UPDATE bills 
                    SET is_deleted=1, notes=notes || %s 
                    WHERE id=%s
                """, (f" [DELETED: {reason}]", bill_id))

                # Log audit record
                audit_details = f"Bill {bill['bill_no']} deleted. Reason: {reason}. Reversed {total_sheets_reversed} physical sheets."
                cur.execute("""
                    INSERT INTO bill_audit_log (bill_id, bill_no, action, performed_by, details, created_at)
                    VALUES (%s, %s, 'DELETE', 'Admin', %s, %s)
                """, (bill_id, bill["bill_no"], audit_details, now_iso))

            conn.commit()

        return {"success": True, "message": f"Bill {bill['bill_no']} successfully deleted and {total_sheets_reversed} sheets returned to stock."}
    except Exception as e:
        return {"success": False, "error": str(e)}, 400

# ── Calculation Helper for Bill Corrections & Previews ──
def calculate_bill_corrections(cur, bill, old_items, data):
    raw_items = data.get("items") or []
    if not raw_items:
        raise ValueError("Bill must contain at least one item.")

    customer = (data.get("customer") or "").strip()
    biller_name = (data.get("biller_name") or "").strip()
    payment_method = data.get("payment_method") or "Cash"
    discount = money(data.get("discount", 0))
    other_charges = money(data.get("other_charges", 0))
    reason = (data.get("reason") or "").strip()
    bill_date = (data.get("bill_date") or "").strip()
    bill_time = (data.get("bill_time") or "").strip()
    new_created_at_input = (data.get("created_at") or "").strip()

    orig_ist_dt = to_ist_datetime(bill.get("created_at"))
    if bill_date:
        if not bill_time and orig_ist_dt:
            time_part = orig_ist_dt.strftime("%H:%M:%S")
        elif bill_time:
            time_part = bill_time if len(bill_time) == 8 else (f"{bill_time}:00" if len(bill_time) == 5 else bill_time)
        else:
            time_part = "12:00:00"
        combined_ist_str = f"{bill_date[:10]} {time_part}"
        try:
            dt_ist = datetime.strptime(combined_ist_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST_TZ)
            new_created_at = dt_ist.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            new_created_at = to_utc_iso(orig_ist_dt)
    elif new_created_at_input:
        try:
            dt_obj = datetime.fromisoformat(new_created_at_input.replace(" ", "T"))
            if dt_obj.tzinfo is None:
                dt_obj = dt_obj.replace(tzinfo=IST_TZ)
            new_created_at = dt_obj.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            new_created_at = to_utc_iso(new_created_at_input)
    else:
        new_created_at = bill["created_at"]

    # Pre-fetch active inventory & services
    cur.execute("""
        SELECT id, item_name, size_spec, available_sheets, 
               ROUND((cost / NULLIF(total_sheets, 0))::numeric, 4) AS cost_per_sheet
        FROM inventory 
        WHERE is_active = 1
        FOR UPDATE
    """)
    inv_rows = cur.fetchall()
    inv_map = {r['id']: dict(r) for r in inv_rows}
    inv_by_name = {r['item_name'].strip().lower(): r['id'] for r in inv_rows}
    inv_by_size = {}
    for r in inv_rows:
        key = (r['size_spec'] or '').strip().upper()
        if key and key not in inv_by_size:
            inv_by_size[key] = r['id']

    cur.execute("SELECT id, name, rate, double_rate, extra_copy_rate, print_type, paper_size, sheets_per_unit, paper_id FROM services")
    services_rows = cur.fetchall()
    serv_by_id = {s['id']: dict(s) for s in services_rows}
    serv_by_name = {s['name'].strip().lower(): dict(s) for s in services_rows}

    # Helper to resolve inventory id for an item
    def resolve_inv_id(s_name, p_size, explicit_inv_id=None, service_id=None):
        if explicit_inv_id and explicit_inv_id in inv_map:
            return explicit_inv_id
        if service_id and service_id in serv_by_id:
            pid = serv_by_id[service_id].get("paper_id")
            if pid and pid in inv_map:
                return pid
        s_obj = serv_by_name.get((s_name or '').strip().lower())
        if s_obj and s_obj.get("paper_id") and s_obj["paper_id"] in inv_map:
            return s_obj["paper_id"]
        if (s_name or '').strip().lower() in inv_by_name:
            return inv_by_name[(s_name or '').strip().lower()]
        size_k = (p_size or '').strip().upper()
        if size_k in inv_by_size:
            return inv_by_size[size_k]
        return None

    # Step 1: Calculate old stock consumed per inventory ID
    orig_stock_by_inv = {}
    for o_it in old_items:
        sheets = o_it.get("paper_sheets", 0)
        if sheets > 0:
            iid = o_it.get("inventory_id") or resolve_inv_id(o_it.get("service_name"), o_it.get("paper_size"))
            if iid:
                orig_stock_by_inv[iid] = orig_stock_by_inv.get(iid, 0) + sheets

    # Step 2: Build new items and calculate new stock consumed per inventory ID
    new_items = []
    new_stock_by_inv = {}
    subtotal = 0.0
    total_paper_cost = 0.0

    for it in raw_items:
        s_name = (it.get("service_name") or it.get("name") or "Service").strip()
        p_type = (it.get("print_type") or it.get("type") or "bw").strip()
        p_size = (it.get("paper_size") or it.get("size") or "A4").strip()
        qty = max(1, int(it.get("quantity") or it.get("qty") or 1))
        pages_per_copy = max(1, int(it.get("pages_per_copy") or it.get("pages") or 1))
        sides = (it.get("sides") or "Single").strip()
        rate = money(it.get("rate", 0))

        s_obj = serv_by_name.get(s_name.lower())
        if not s_obj:
            norm_s_name = s_name.lower().replace("—", "-").replace("–", "-")
            for sn, so in serv_by_name.items():
                if sn.replace("—", "-").replace("–", "-") == norm_s_name:
                    s_obj = so
                    break

        is_double = sides.lower().startswith("double")
        has_custom_rate = bool(it.get("has_custom_rate") or it.get("custom_rate") or it.get("is_custom_rate"))
        user_rate = money(it.get("rate", 0))

        default_tiered_total = 0.0
        default_tiered_rate = 0.0
        if s_obj and s_obj.get("extra_copy_rate") is not None and float(s_obj.get("extra_copy_rate") or 0) > 0:
            first_copy = float(s_obj["double_rate"] if (is_double and s_obj.get("double_rate") is not None) else s_obj["rate"])
            extra_copy = float(s_obj["extra_copy_rate"])
            default_tiered_total = money(first_copy + max(0, qty - 1) * extra_copy)
            default_tiered_rate = money(default_tiered_total / qty)

        if user_rate > 0 and (has_custom_rate or (s_obj and s_obj.get("extra_copy_rate") and user_rate != default_tiered_rate)):
            # Retain saved rate or explicitly edited rate!
            rate = user_rate
            line_total = money(qty * pages_per_copy * rate)
        elif s_obj and s_obj.get("extra_copy_rate") is not None and float(s_obj.get("extra_copy_rate") or 0) > 0:
            line_total = default_tiered_total
            rate = default_tiered_rate
        else:
            if rate <= 0.001 and s_obj:
                rate = s_obj["double_rate"] if (is_double and s_obj.get("double_rate")) else s_obj["rate"]
            line_total = money(qty * pages_per_copy * rate)

        subtotal += line_total

        # Paper sheets calculation: 1 copy = 1 sheet for physical jobs
        if "paper_sheets" in it and it["paper_sheets"] is not None and str(it["paper_sheets"]).strip() != "":
            sheets = max(0, int(it["paper_sheets"]))
        else:
            sheets = 0 if (p_size.lower() == 'digital' or (s_obj and s_obj.get("sheets_per_unit") == 0)) else (qty * pages_per_copy)

        target_inv_id = resolve_inv_id(s_name, p_size, it.get("inventory_id"), it.get("service_id"))
        unit_cost = 0.0
        if target_inv_id and target_inv_id in inv_map:
            unit_cost = float(inv_map[target_inv_id]["cost_per_sheet"] or 0.0)

        line_paper_cost = money(sheets * unit_cost) if sheets > 0 else 0.0
        line_profit = money(line_total - line_paper_cost)
        total_paper_cost += line_paper_cost

        color_units = (qty * pages_per_copy) if p_type in ("color", "photo") else 0

        new_items.append({
            "service_name": s_name,
            "print_type": p_type,
            "paper_size": p_size,
            "quantity": qty,
            "pages_per_copy": pages_per_copy,
            "sides": sides,
            "rate": rate,
            "line_total": line_total,
            "paper_sheets": sheets,
            "color_units": color_units,
            "paper_cost": line_paper_cost,
            "profit": line_profit,
            "inventory_id": target_inv_id
        })

        if target_inv_id and sheets > 0:
            new_stock_by_inv[target_inv_id] = new_stock_by_inv.get(target_inv_id, 0) + sheets

    # Step 3: Stock impact calculation and negative stock validation
    all_affected_inv_ids = set(orig_stock_by_inv.keys()) | set(new_stock_by_inv.keys())
    stock_impacts = []
    has_stock_error = False

    for iid in sorted(all_affected_inv_ids):
        inv_item = inv_map.get(iid)
        inv_name = inv_item["item_name"] if inv_item else f"Paper Item #{iid}"
        cur_avail = inv_item["available_sheets"] if inv_item else 0
        orig_used = orig_stock_by_inv.get(iid, 0)
        new_used = new_stock_by_inv.get(iid, 0)
        net_diff = orig_used - new_used  # > 0 means returning to stock, < 0 means deducting additional
        new_avail = cur_avail + net_diff

        err = None
        if new_avail < 0:
            has_stock_error = True
            err = f"Insufficient stock for '{inv_name}'. Current available: {cur_avail} sheets. Additional required: {abs(net_diff)} sheets. Available after reversing original bill: {cur_avail + orig_used} sheets."

        stock_impacts.append({
            "inventory_id": iid,
            "item_name": inv_name,
            "current_available": cur_avail,
            "original_consumed": orig_used,
            "new_consumed": new_used,
            "net_difference": net_diff,
            "new_available": new_avail,
            "error": err
        })

    # Step 4: Financial recalculations
    subtotal = money(subtotal)
    other_charges = money(max(0.0, other_charges))
    discount = money(min(max(0.0, discount), subtotal + other_charges))
    final_total = money(subtotal + other_charges - discount)
    total_paper_cost = money(total_paper_cost)
    profit = money(final_total - total_paper_cost)

    # Step 5: Payments & Balances
    cur.execute("SELECT COALESCE(SUM(amount), 0) AS paid_sum FROM bill_payments WHERE bill_id = %s", (bill["id"],))
    payments_sum = money(cur.fetchone()["paid_sum"])
    paid_amount = payments_sum if payments_sum > 0 else money(bill.get("paid", 0))

    balance_diff = money(final_total - paid_amount)
    if balance_diff <= 0.001:
        new_balance = 0.0
        excess_amount = money(paid_amount - final_total) if paid_amount > final_total else 0.0
        new_status = "Paid"
    else:
        new_balance = balance_diff
        excess_amount = 0.0
        new_status = "Partially Paid" if paid_amount > 0 else "Unpaid"

    return {
        "customer": customer,
        "biller_name": biller_name,
        "payment_method": payment_method,
        "subtotal": subtotal,
        "other_charges": other_charges,
        "discount": discount,
        "total": final_total,
        "total_paper_cost": total_paper_cost,
        "profit": profit,
        "paid_amount": paid_amount,
        "balance": new_balance,
        "excess_amount": excess_amount,
        "payment_status": new_status,
        "new_created_at": new_created_at,
        "reason": reason,
        "new_items": new_items,
        "stock_impacts": stock_impacts,
        "has_stock_error": has_stock_error
    }


# ── API: Inspect Bill for Editing (Admin only) ──
@app.get("/api/bills/<int:bill_id>/edit-details")
@admin_api_required
def get_bill_edit_details(bill_id):
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM bills WHERE id=%s AND is_deleted=0", (bill_id,))
                bill = cur.fetchone()
                if not bill:
                    return {"success": False, "error": "Bill not found or deleted."}, 404

                cur.execute("SELECT * FROM bill_items WHERE bill_id=%s ORDER BY id ASC", (bill_id,))
                items = cur.fetchall()

                cur.execute("SELECT * FROM bill_payments WHERE bill_id=%s ORDER BY id ASC", (bill_id,))
                payments = cur.fetchall()

                cur.execute("SELECT id, name, rate, double_rate, print_type, paper_size, sheets_per_unit, paper_id FROM services WHERE active=1 ORDER BY name")
                services = cur.fetchall()

                cur.execute("SELECT id, item_name, size_spec, available_sheets, ROUND((cost / NULLIF(total_sheets, 0))::numeric, 4) AS cost_per_sheet FROM inventory WHERE is_active=1 ORDER BY item_name")
                inventory = cur.fetchall()

                cur.execute("SELECT * FROM bill_audit_log WHERE bill_id=%s OR bill_no=%s ORDER BY id DESC", (bill_id, bill["bill_no"]))
                audit_logs = cur.fetchall()

        b_dict = dict(bill)
        b_dict["created_at_utc"] = b_dict.get("created_at")
        b_dict["created_at_ist"] = format_ist_datetime_str(b_dict.get("created_at"), "%Y-%m-%dT%H:%M:%S")
        b_dict["created_date_ist"] = format_ist_date_str(b_dict.get("created_at"))
        b_dict["created_time_ist"] = format_ist_datetime_str(b_dict.get("created_at"), "%H:%M:%S")
        b_dict["original_created_at_ist"] = format_ist_datetime_str(b_dict.get("original_created_at"), "%Y-%m-%dT%H:%M:%S")

        formatted_audit_logs = []
        for a in audit_logs:
            ad = dict(a)
            ad["created_at_ist"] = format_ist_datetime_str(ad.get("created_at"))
            formatted_audit_logs.append(ad)

        return {
            "success": True,
            "bill": b_dict,
            "items": [dict(it) for it in items],
            "payments": [dict(p) for p in payments],
            "services": [dict(s) for s in services],
            "inventory": [dict(i) for i in inventory],
            "audit_logs": formatted_audit_logs
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400


# ── API: Preview Bill Corrections & Confirmation Summary (Admin only) ──
@app.post("/api/bills/<int:bill_id>/edit-preview")
@admin_api_required
def edit_bill_preview(bill_id):
    try:
        data = request.get_json(force=True) or {}
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM bills WHERE id=%s AND is_deleted=0 FOR UPDATE", (bill_id,))
                bill = cur.fetchone()
                if not bill:
                    return {"success": False, "error": "Bill not found or deleted."}, 404

                cur.execute("SELECT * FROM bill_items WHERE bill_id=%s", (bill_id,))
                old_items = cur.fetchall()

                calc = calculate_bill_corrections(cur, bill, old_items, data)

        # Build comparison summary table
        orig_sheets = sum(o.get("paper_sheets", 0) for o in old_items)
        new_sheets = sum(n.get("paper_sheets", 0) for n in calc["new_items"])

        orig_dt = format_ist_datetime_str(bill["created_at"])
        new_dt = format_ist_datetime_str(calc["new_created_at"])

        summary_rows = [
            {
                "field": "Bill Date & Time",
                "original": orig_dt,
                "corrected": new_dt,
                "is_changed": orig_dt != new_dt
            },
            {
                "field": "Customer Name",
                "original": bill["customer"] or "(None)",
                "corrected": calc["customer"] or "(None)",
                "is_changed": (bill["customer"] or "") != calc["customer"]
            },
            {
                "field": "Biller / Staff",
                "original": bill.get("biller_name") or "Staff",
                "corrected": calc["biller_name"] or "Staff",
                "is_changed": (bill.get("biller_name") or "") != calc["biller_name"]
            },
            {
                "field": "Subtotal",
                "original": inr(bill["subtotal"]),
                "corrected": inr(calc["subtotal"]),
                "is_changed": money(bill["subtotal"]) != calc["subtotal"]
            },
            {
                "field": "Other Charges",
                "original": inr(bill.get("other_charges", 0)),
                "corrected": inr(calc["other_charges"]),
                "is_changed": money(bill.get("other_charges", 0)) != calc["other_charges"]
            },
            {
                "field": "Discount",
                "original": inr(bill.get("discount", 0)),
                "corrected": inr(calc["discount"]),
                "is_changed": money(bill.get("discount", 0)) != calc["discount"]
            },
            {
                "field": "Final Bill Amount",
                "original": inr(bill["total"]),
                "corrected": inr(calc["total"]),
                "is_changed": money(bill["total"]) != calc["total"]
            },
            {
                "field": "Paper Sheet Consumption",
                "original": f"{orig_sheets} sheets",
                "corrected": f"{new_sheets} sheets",
                "is_changed": orig_sheets != new_sheets
            },
            {
                "field": "Already Paid (Preserved)",
                "original": inr(calc["paid_amount"]),
                "corrected": inr(calc["paid_amount"]),
                "is_changed": False
            },
            {
                "field": "Outstanding Balance Due",
                "original": inr(bill["balance"]),
                "corrected": inr(calc["balance"]),
                "is_changed": money(bill["balance"]) != calc["balance"]
            }
        ]

        warnings = []
        if calc["excess_amount"] > 0:
            warnings.append(f"Excess payment detected: Bill total (₹{calc['total']}) is less than already collected amount (₹{calc['paid_amount']}). Excess payment of ₹{calc['excess_amount']} requires store reconciliation.")

        if calc["has_stock_error"]:
            for si in calc["stock_impacts"]:
                if si["error"]:
                    warnings.append(si["error"])

        return {
            "success": True,
            "bill_no": bill["bill_no"],
            "summary_rows": summary_rows,
            "stock_impacts": calc["stock_impacts"],
            "warnings": warnings,
            "can_save": not calc["has_stock_error"],
            "excess_amount": calc["excess_amount"],
            "calc": calc
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400


# ── API: Apply Confirmed Bill Corrections (Admin only with rollback) ──
@app.post("/api/bills/<int:bill_id>/edit")
@admin_api_required
def edit_bill(bill_id):
    try:
        data = request.get_json(force=True) or {}
        now_iso = to_utc_iso()
        today_iso = get_ist_today_str()
        user_name = session.get("user") or "Admin"

        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM bills WHERE id=%s AND is_deleted=0 FOR UPDATE", (bill_id,))
                bill = cur.fetchone()
                if not bill:
                    return {"success": False, "error": "Bill not found or deleted."}, 404

                cur.execute("SELECT * FROM bill_items WHERE bill_id=%s ORDER BY id ASC", (bill_id,))
                old_items = cur.fetchall()

                # Calculate corrections & validate stock
                calc = calculate_bill_corrections(cur, bill, old_items, data)
                if calc["has_stock_error"]:
                    errors = [si["error"] for si in calc["stock_impacts"] if si["error"]]
                    conn.rollback()
                    return {"success": False, "error": "; ".join(errors)}, 400

                # Step A: Apply stock inventory adjustments & record in movement ledger
                for si in calc["stock_impacts"]:
                    net_diff = si["net_difference"]
                    iid = si["inventory_id"]
                    new_avail = si["new_available"]
                    cur_avail = si["current_available"]

                    if net_diff != 0:
                        cur.execute("UPDATE inventory SET available_sheets=%s, updated_at=%s WHERE id=%s", (new_avail, now_iso, iid))

                        if net_diff > 0:
                            # Sheets returned to stock
                            m_notes = f"Bill {bill['bill_no']} edit: {net_diff} sheets returned to stock ({calc['reason']})"
                            cur.execute("""
                                INSERT INTO stock_movements (item_id, movement_type, quantity, previous_balance, balance_after, reference_id, notes, recorded_by, movement_date, created_at)
                                VALUES (%s, 'RETURN', %s, %s, %s, %s, %s, %s, %s, %s)
                            """, (iid, net_diff, cur_avail, new_avail, bill["bill_no"], m_notes, user_name, today_iso, now_iso))
                        else:
                            # Additional sheets consumed
                            m_notes = f"Bill {bill['bill_no']} edit: {abs(net_diff)} additional sheets consumed ({calc['reason']})"
                            cur.execute("""
                                INSERT INTO stock_movements (item_id, movement_type, quantity, previous_balance, balance_after, reference_id, notes, recorded_by, movement_date, created_at)
                                VALUES (%s, 'SALE', %s, %s, %s, %s, %s, %s, %s, %s)
                            """, (iid, net_diff, cur_avail, new_avail, bill["bill_no"], m_notes, user_name, today_iso, now_iso))

                # Step B: Delete old items & insert corrected items
                cur.execute("DELETE FROM bill_items WHERE bill_id=%s", (bill_id,))
                for x in calc["new_items"]:
                    cur.execute("""
                        INSERT INTO bill_items (bill_id, service_name, print_type, paper_size, quantity, pages_per_copy, sides, rate, line_total, paper_sheets, color_units, paper_cost, profit, inventory_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (bill_id, x["service_name"], x["print_type"], x["paper_size"], x["quantity"], x["pages_per_copy"],
                          x["sides"], x["rate"], x["line_total"], x["paper_sheets"], x["color_units"], x["paper_cost"], x["profit"], x["inventory_id"]))

                # Step C: Detect changed fields for audit log
                changed_fields = []
                if (calc["new_created_at"] or "")[:19] != (bill["created_at"] or "")[:19]:
                    changed_fields.append("date/time")
                if calc["customer"] != (bill.get("customer") or ""):
                    changed_fields.append("customer")
                if calc["biller_name"] != (bill.get("biller_name") or ""):
                    changed_fields.append("biller")
                if calc["subtotal"] != money(bill["subtotal"]):
                    changed_fields.append("subtotal")
                if calc["other_charges"] != money(bill.get("other_charges", 0)):
                    changed_fields.append("other_charges")
                if calc["discount"] != money(bill.get("discount", 0)):
                    changed_fields.append("discount")
                if calc["total"] != money(bill["total"]):
                    changed_fields.append("total")
                if calc["balance"] != money(bill["balance"]):
                    changed_fields.append("balance")
                if calc["payment_status"] != (bill.get("payment_status") or "Paid"):
                    changed_fields.append("payment_status")

                orig_total_sheets = sum(o.get("paper_sheets", 0) for o in old_items)
                new_total_sheets = sum(n["paper_sheets"] for n in calc["new_items"])
                if orig_total_sheets != new_total_sheets or len(old_items) != len(calc["new_items"]):
                    changed_fields.append("items/sheets")

                orig_created_at = bill.get("original_created_at") or bill["created_at"]

                # Step D: Update bill master record
                cur.execute("""
                    UPDATE bills
                    SET customer=%s,
                        biller_name=%s,
                        payment_method=%s,
                        subtotal=%s,
                        discount=%s,
                        other_charges=%s,
                        total=%s,
                        paid=%s,
                        balance=%s,
                        paper_cost=%s,
                        profit=%s,
                        payment_status=%s,
                        created_at=%s,
                        original_created_at=%s
                    WHERE id=%s
                """, (calc["customer"], calc["biller_name"], calc["payment_method"], calc["subtotal"],
                      calc["discount"], calc["other_charges"], calc["total"], calc["paid_amount"],
                      calc["balance"], calc["total_paper_cost"], calc["profit"], calc["payment_status"],
                      calc["new_created_at"], orig_created_at, bill_id))

                # Step E: Store audit snapshot
                orig_snapshot = {
                    "bill_no": bill["bill_no"],
                    "created_at": bill["created_at"],
                    "created_at_ist": format_ist_datetime_str(bill["created_at"]),
                    "customer": bill["customer"],
                    "biller_name": bill.get("biller_name", ""),
                    "payment_method": bill["payment_method"],
                    "subtotal": bill["subtotal"],
                    "discount": bill.get("discount", 0),
                    "other_charges": bill.get("other_charges", 0),
                    "total": bill["total"],
                    "paid": calc["paid_amount"],
                    "balance": bill["balance"],
                    "paper_cost": bill.get("paper_cost", 0),
                    "profit": bill.get("profit", 0),
                    "payment_status": bill.get("payment_status", "Paid"),
                    "items": [dict(o) for o in old_items]
                }
                new_snapshot = {
                    "bill_no": bill["bill_no"],
                    "created_at": calc["new_created_at"],
                    "created_at_ist": format_ist_datetime_str(calc["new_created_at"]),
                    "customer": calc["customer"],
                    "biller_name": calc["biller_name"],
                    "payment_method": calc["payment_method"],
                    "subtotal": calc["subtotal"],
                    "discount": calc["discount"],
                    "other_charges": calc["other_charges"],
                    "total": calc["total"],
                    "paid": calc["paid_amount"],
                    "balance": calc["balance"],
                    "excess_amount": calc["excess_amount"],
                    "paper_cost": calc["total_paper_cost"],
                    "profit": calc["profit"],
                    "payment_status": calc["payment_status"],
                    "items": calc["new_items"],
                    "stock_impacts": calc["stock_impacts"]
                }

                audit_details = f"Bill {bill['bill_no']} edited by {user_name}. Reason: {calc['reason']}. Total: ₹{bill['total']} -> ₹{calc['total']}."
                if (calc["new_created_at"] or "")[:19] != (bill["created_at"] or "")[:19]:
                    orig_ist_disp = format_ist_datetime_str(bill["created_at"])
                    new_ist_disp = format_ist_datetime_str(calc["new_created_at"])
                    audit_details += f" Date: {orig_ist_disp} -> {new_ist_disp}."

                cur.execute("""
                    INSERT INTO bill_audit_log (
                        bill_id, bill_no, action, performed_by, details, created_at,
                        original_values, updated_values, fields_changed, reason, original_created_at
                    )
                    VALUES (%s, %s, 'EDIT', %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    bill["id"], bill["bill_no"], user_name, audit_details, now_iso,
                    json.dumps(orig_snapshot, default=str),
                    json.dumps(new_snapshot, default=str),
                    ", ".join(changed_fields) if changed_fields else "minor corrections",
                    calc["reason"],
                    orig_created_at
                ))

            conn.commit()

        return {
            "success": True,
            "message": f"Bill {bill['bill_no']} successfully updated and stock reconciled.",
            "bill_no": bill["bill_no"]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400


# ── API: Edit Bill Date Only (Admin only, preserves items, stock & payments) ──
@app.post("/api/bills/<int:bill_id>/edit-date")
@admin_api_required
def edit_bill_date_api(bill_id):
    try:
        data = request.get_json(force=True) or {}
        new_date = (data.get("bill_date") or data.get("date") or "").strip()
        new_time = (data.get("bill_time") or data.get("time") or "").strip()
        reason = (data.get("reason") or "Bill date correction by admin").strip()
        user_name = session.get("user") or getattr(request, "current_user", {}).get("name") or "Admin"
        now_iso = to_utc_iso()

        if not new_date:
            return {"success": False, "error": "New bill date is required (YYYY-MM-DD)."}, 400

        try:
            datetime.strptime(new_date[:10], "%Y-%m-%d")
        except ValueError:
            return {"success": False, "error": "Invalid date format. Expected YYYY-MM-DD."}, 400

        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM bills WHERE id=%s AND is_deleted=0 FOR UPDATE", (bill_id,))
                bill = cur.fetchone()
                if not bill:
                    return {"success": False, "error": "Bill not found or deleted."}, 404

                orig_created_at = bill["created_at"]
                orig_ist_dt = to_ist_datetime(orig_created_at)
                orig_ist_str = format_ist_datetime_str(orig_created_at)
                orig_date_ist = format_ist_date_str(orig_created_at)

                # Preserve original IST time of day if only date is passed
                if not new_time and orig_ist_dt:
                    time_part = orig_ist_dt.strftime("%H:%M:%S")
                elif new_time:
                    clean_time = new_time.strip()
                    time_part = clean_time if len(clean_time) == 8 else (f"{clean_time}:00" if len(clean_time) == 5 else clean_time)
                else:
                    time_part = "12:00:00"

                combined_ist_str = f"{new_date[:10]} {time_part}"
                new_ist_dt = datetime.strptime(combined_ist_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST_TZ)
                new_created_at_utc = new_ist_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                new_ist_str = format_ist_datetime_str(new_created_at_utc)
                new_date_ist = format_ist_date_str(new_created_at_utc)

                orig_master_created_at = bill.get("original_created_at") or orig_created_at

                # Update only bills.created_at and original_created_at
                cur.execute("""
                    UPDATE bills
                    SET created_at = %s,
                        original_created_at = %s
                    WHERE id = %s
                """, (new_created_at_utc, orig_master_created_at, bill_id))

                # Audit log entry with action 'DATE_EDIT'
                audit_details = f"Bill {bill['bill_no']} date corrected from {orig_ist_str} to {new_ist_str} by {user_name}. Reason: {reason}"
                cur.execute("""
                    INSERT INTO bill_audit_log (
                        bill_id, bill_no, action, performed_by, details, created_at,
                        original_values, updated_values, fields_changed, reason, original_created_at
                    )
                    VALUES (%s, %s, 'DATE_EDIT', %s, %s, %s, %s, %s, 'date', %s, %s)
                """, (
                    bill["id"], bill["bill_no"], user_name, audit_details, now_iso,
                    json.dumps({"created_at": orig_created_at, "created_at_ist": orig_ist_str, "date_ist": orig_date_ist}),
                    json.dumps({"created_at": new_created_at_utc, "created_at_ist": new_ist_str, "date_ist": new_date_ist}),
                    reason,
                    orig_master_created_at
                ))

            conn.commit()

        return {
            "success": True,
            "message": f"Bill {bill['bill_no']} date successfully corrected to {new_ist_str}.",
            "bill_id": bill["id"],
            "bill_no": bill["bill_no"],
            "previous_created_at_utc": orig_created_at,
            "previous_created_at_ist": orig_ist_str,
            "new_created_at_utc": new_created_at_utc,
            "new_created_at_ist": new_ist_str
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400


# ── API: View Edit & Audit History for a Bill ──
@app.get("/api/bills/<int:bill_id>/audit")
@admin_api_required
def get_bill_audit(bill_id):
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT bill_no, original_created_at, created_at FROM bills WHERE id=%s", (bill_id,))
                bill = cur.fetchone()
                if not bill:
                    return {"success": False, "error": "Bill not found"}, 404

                cur.execute("""
                    SELECT id, bill_id, bill_no, action, performed_by, details, created_at,
                           fields_changed, reason, original_created_at, original_values, updated_values
                    FROM bill_audit_log 
                    WHERE bill_id=%s OR bill_no=%s 
                    ORDER BY id DESC
                """, (bill_id, bill["bill_no"]))
                logs = cur.fetchall()

        parsed_logs = []
        for r in logs:
            row_dict = dict(r)
            try:
                row_dict["original_values_parsed"] = json.loads(row_dict.get("original_values") or "{}")
            except Exception:
                row_dict["original_values_parsed"] = {}
            try:
                row_dict["updated_values_parsed"] = json.loads(row_dict.get("updated_values") or "{}")
            except Exception:
                row_dict["updated_values_parsed"] = {}
            parsed_logs.append(row_dict)

        return {
            "success": True,
            "bill_no": bill["bill_no"],
            "original_created_at": bill.get("original_created_at") or bill["created_at"],
            "current_created_at": bill["created_at"],
            "logs": parsed_logs
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400

# ── API: Record Supplier Purchase Payment (Admin only) ──
@app.post("/api/purchases/<int:purchase_id>/pay")
@admin_api_required
def pay_supplier_purchase(purchase_id):
    try:
        data = request.get_json(force=True) or {}
        new_amount = money(data.get("amount", 0))
        payment_method = data.get("payment_method") or "Cash"
        payment_date = data.get("payment_date") or get_ist_today_str()
        notes = (data.get("notes") or "").strip()
        recorded_by = "Admin"
        now_iso = to_utc_iso()

        if new_amount <= 0:
            return {"success": False, "error": "Payment amount must be greater than zero."}, 400

        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM purchases WHERE id=%s FOR UPDATE", (purchase_id,))
                purch = cur.fetchone()
                if not purch:
                    return {"success": False, "error": "Purchase not found."}, 404

                cur_balance = money(purch["balance_amount"])
                if new_amount > (cur_balance + 0.01):
                    return {"success": False, "error": f"Payment amount ({inr(new_amount)}) cannot exceed outstanding supplier balance of {inr(cur_balance)}."}, 400

                new_paid = money(purch["paid_amount"] + new_amount)
                new_balance = max(0.0, money(purch["total_amount"] - new_paid))
                new_status = "Paid" if new_balance <= 0.001 else "Partially Paid"

                cur.execute("""
                    UPDATE purchases 
                    SET paid_amount=%s, balance_amount=%s, payment_status=%s 
                    WHERE id=%s
                """, (new_paid, new_balance, new_status, purchase_id))

                cur.execute("""
                    INSERT INTO purchase_payments (purchase_id, amount, payment_date, payment_method, recorded_by, notes, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (purchase_id, new_amount, payment_date, payment_method, recorded_by, notes, now_iso))

            conn.commit()

        return {
            "success": True,
            "purchase_id": purchase_id,
            "paid": new_paid,
            "balance": new_balance,
            "payment_status": new_status,
            "message": f"Supplier payment of {inr(new_amount)} recorded."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400

# ── API: Get Supplier Purchase Payments (Admin only) ──
@app.get("/api/purchases/<int:purchase_id>/payments")
@admin_api_required
def get_purchase_payments(purchase_id):
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM purchases WHERE id=%s", (purchase_id,))
                purch = cur.fetchone()
                if not purch:
                    return {"success": False, "error": "Purchase not found"}, 404

                cur.execute("SELECT * FROM purchase_payments WHERE purchase_id=%s ORDER BY id ASC", (purchase_id,))
                payments = cur.fetchall()

        return {"success": True, "purchase": purch, "payments": payments}
    except Exception as e:
        return {"success": False, "error": str(e)}, 400

# ── API: Create Supplier Purchase (Multi-Item) (Admin only) ──
@app.post("/api/purchases")
@app.post("/api/purchases/create")
@admin_api_required
def api_create_purchase():
    try:
        data = request.get_json(force=True) if request.is_json else request.form.to_dict()
        if "items_json" in data and isinstance(data["items_json"], str):
            data["items"] = json.loads(data["items_json"])

        is_admin = bool(session.get("is_admin") or session.get("role") == "admin")
        user_name = "Admin" if is_admin else (session.get("user") or "Staff")

        with db() as conn:
            with conn.cursor() as cur:
                p_id, b_no, total, paid, bal, status = process_create_purchase(cur, data, is_admin, biller_default=user_name)
            conn.commit()

        if not request.is_json:
            flash(f"Recorded supplier purchase invoice '{b_no}' (Total: {inr(total)}).", "success")
            return redirect(url_for("inventory_page"))

        return {
            "success": True,
            "purchase_id": p_id,
            "bill_number": b_no,
            "total_amount": total,
            "paid_amount": paid,
            "balance_amount": bal,
            "payment_status": status,
            "message": f"Supplier purchase bill '{b_no}' recorded successfully."
        }
    except Exception as e:
        if not request.is_json:
            flash(f"Error creating purchase: {e}", "error")
            return redirect(url_for("inventory_page"))
        return {"success": False, "error": str(e)}, 400

# ── API: Get Full Supplier Purchase Details (Admin only) ──
@app.get("/api/purchases/<int:purchase_id>/details")
@admin_api_required
def api_get_purchase_details(purchase_id):
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM purchases WHERE id=%s", (purchase_id,))
                p = cur.fetchone()
                if not p:
                    return {"success": False, "error": "Purchase bill not found."}, 404

                items = get_purchase_items_breakdown(cur, purchase_id)

                cur.execute("SELECT * FROM purchase_payments WHERE purchase_id=%s ORDER BY id ASC", (purchase_id,))
                payments = cur.fetchall()

                cur.execute("SELECT * FROM purchase_returns WHERE purchase_id=%s ORDER BY id DESC", (purchase_id,))
                returns = cur.fetchall()

                cur.execute("SELECT * FROM purchase_audit_log WHERE purchase_id=%s ORDER BY id DESC", (purchase_id,))
                audit_logs = cur.fetchall()

        return {
            "success": True,
            "purchase": dict(p),
            "items": items,
            "payments": [dict(pm) for pm in payments],
            "returns": [dict(ret) for ret in returns],
            "audit_logs": [dict(al) for al in audit_logs]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400

# ── API: Return Paper Stock to Supplier (Admin only) ──
@app.post("/api/purchases/<int:purchase_id>/return")
@admin_api_required
def api_return_purchase_item(purchase_id):
    try:
        data = request.get_json(force=True) if request.is_json else request.form.to_dict()
        purchase_item_id = int(data.get("purchase_item_id") or 0)
        return_qty = int(data.get("return_quantity") or data.get("quantity") or 0)
        return_date = data.get("return_date") or get_ist_today_str()
        reason = (data.get("reason") or "Returned unsold paper stock to supplier").strip()
        notes = (data.get("notes") or "").strip()
        user_name = "Admin"

        if purchase_item_id <= 0:
            return {"success": False, "error": "Valid purchase item must be selected for return."}, 400
        if return_qty <= 0:
            return {"success": False, "error": "Return quantity must be greater than zero."}, 400

        with db() as conn:
            with conn.cursor() as cur:
                res = process_return_purchase_item(
                    cur, purchase_id, purchase_item_id, return_qty,
                    return_date=return_date, reason=reason, notes=notes, user_name=user_name
                )
            conn.commit()

        if not request.is_json:
            flash(f"Returned {return_qty} sheets of {res['item_name']} (Refund/Credit: {inr(res['return_amount'])}).", "success")
            return redirect(url_for("inventory_page"))

        return {
            "success": True,
            "message": f"Successfully returned {return_qty} sheets of {res['item_name']} (Value: {inr(res['return_amount'])}).",
            **res
        }
    except Exception as e:
        if not request.is_json:
            flash(f"Error returning stock: {e}", "error")
            return redirect(url_for("inventory_page"))
        return {"success": False, "error": str(e)}, 400

# ── API: Audit Double-Sided Photocopy/Print Paper Consumption (Admin only) ──
@app.get("/api/inventory/audit-double-sided")
@admin_api_required
def api_audit_double_sided():
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT bi.id AS item_id, bi.bill_id, b.bill_no AS bill_number, b.created_at,
                           bi.service_name, bi.paper_size, bi.sides, bi.quantity,
                           bi.paper_sheets, bi.rate, bi.paper_cost, bi.profit
                    FROM bill_items bi
                    JOIN bills b ON bi.bill_id = b.id
                    WHERE bi.sides ILIKE '%double%'
                      AND bi.paper_size NOT ILIKE '%digital%'
                      AND bi.paper_sheets < bi.quantity
                    ORDER BY bi.id DESC
                """)
                discrepancies = cur.fetchall()

                by_size = {}
                total_underdeducted = 0
                for d in discrepancies:
                    diff = d["quantity"] - d["paper_sheets"]
                    total_underdeducted += diff
                    sz = (d["paper_size"] or "A4").upper()
                    by_size[sz] = by_size.get(sz, 0) + diff

        return {
            "success": True,
            "affected_items_count": len(discrepancies),
            "total_underdeducted_sheets": total_underdeducted,
            "summary_by_size": by_size,
            "discrepancies": [dict(d) for d in discrepancies[:100]]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400


@app.post("/api/inventory/reconcile-double-sided")
@admin_api_required
def api_reconcile_double_sided():
    try:
        user_name = "Admin"
        now = to_utc_iso()
        reconciled_items = 0
        reconciled_sheets = 0

        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT bi.id, bi.bill_id, b.bill_no AS bill_number, bi.service_name, bi.paper_size,
                           bi.quantity, bi.paper_sheets, bi.rate, bi.line_total
                    FROM bill_items bi
                    JOIN bills b ON bi.bill_id = b.id
                    WHERE bi.sides ILIKE '%double%'
                      AND bi.paper_size NOT ILIKE '%digital%'
                      AND bi.paper_sheets < bi.quantity
                    ORDER BY bi.id ASC
                    FOR UPDATE
                """)
                rows = cur.fetchall()

                cur.execute("SELECT id, size_spec, available_sheets, cost_per_sheet FROM inventory WHERE is_deleted=0")
                inv_list = cur.fetchall()
                inv_by_size = {}
                for r in inv_list:
                    k = (r["size_spec"] or "").strip().upper()
                    if k and k not in inv_by_size:
                        inv_by_size[k] = r

                for r in rows:
                    diff = r["quantity"] - r["paper_sheets"]
                    if diff <= 0:
                        continue

                    size_key = (r["paper_size"] or "A4").strip().upper()
                    inv_match = inv_by_size.get(size_key)
                    unit_cost = float(inv_match["cost_per_sheet"] or 0.0) if inv_match else 0.0

                    if inv_match:
                        cur.execute("SELECT available_sheets FROM inventory WHERE id=%s FOR UPDATE", (inv_match["id"],))
                        cur_avail = cur.fetchone()["available_sheets"]
                        new_avail = max(0, cur_avail - diff)
                        cur.execute("UPDATE inventory SET available_sheets=%s, updated_at=%s WHERE id=%s", (new_avail, now, inv_match["id"]))

                        cur.execute("""
                            INSERT INTO stock_movements (item_id, movement_type, quantity, previous_balance, balance_after, reference_id, notes, recorded_by, movement_date, created_at)
                            VALUES (%s, 'AUDIT_RECONCILE', %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (inv_match["id"], -diff, cur_avail, new_avail, r["bill_number"], f"Reconciled double-sided sheets for bill #{r['bill_number']} ({r['paper_sheets']} -> {r['quantity']})", user_name, now[:10], now))

                    new_sheets = r["quantity"]
                    new_paper_cost = round(new_sheets * unit_cost, 2)
                    new_profit = round(float(r["line_total"]) - new_paper_cost, 2)
                    cur.execute("""
                        UPDATE bill_items
                        SET paper_sheets=%s, paper_cost=%s, profit=%s
                        WHERE id=%s
                    """, (new_sheets, new_paper_cost, new_profit, r["id"]))

                    reconciled_items += 1
                    reconciled_sheets += diff

                cur.execute("""
                    UPDATE bills b
                    SET paper_cost = sub.total_pc,
                        profit = b.total - sub.total_pc
                    FROM (
                        SELECT bill_id, COALESCE(SUM(paper_cost), 0) AS total_pc
                        FROM bill_items
                        GROUP BY bill_id
                    ) sub
                    WHERE b.id = sub.bill_id
                """)

            conn.commit()

        return {
            "success": True,
            "reconciled_items_count": reconciled_items,
            "reconciled_sheets_total": reconciled_sheets,
            "message": f"Successfully reconciled {reconciled_sheets} sheets across {reconciled_items} double-sided line items."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400

# ── API: Edit Supplier Purchase (Admin only with stock reconciliation) ──
@app.post("/api/purchases/<int:purchase_id>/edit")
@admin_api_required
def api_edit_purchase(purchase_id):
    try:
        data = request.get_json(force=True) if request.is_json else request.form.to_dict()
        if "items_json" in data and isinstance(data["items_json"], str):
            data["items"] = json.loads(data["items_json"])

        user_name = "Admin"
        with db() as conn:
            with conn.cursor() as cur:
                p_id, b_no, total, paid, bal, status = process_edit_purchase(cur, purchase_id, data, user_name=user_name)
            conn.commit()

        if not request.is_json:
            flash(f"Updated supplier purchase '{b_no}' (New Total: {inr(total)}).", "success")
            return redirect(url_for("inventory_page"))

        return {
            "success": True,
            "purchase_id": p_id,
            "bill_number": b_no,
            "total_amount": total,
            "paid_amount": paid,
            "balance_amount": bal,
            "payment_status": status,
            "message": f"Supplier purchase '{b_no}' updated and stock reconciled successfully."
        }
    except Exception as e:
        if not request.is_json:
            flash(f"Error editing purchase: {e}", "error")
            return redirect(url_for("inventory_page"))
        return {"success": False, "error": str(e)}, 400

# ── API: Delete Supplier Purchase (Admin only with stock reversal) ──
@app.post("/api/purchases/<int:purchase_id>/delete")
@admin_api_required
def api_delete_purchase(purchase_id):
    try:
        data = request.get_json(force=True) if request.is_json else request.form.to_dict()
        reason = (data.get("reason") or "Admin cancellation").strip()
        user_name = "Admin"

        with db() as conn:
            with conn.cursor() as cur:
                b_no = process_delete_purchase(cur, purchase_id, reason=reason, user_name=user_name)
            conn.commit()

        if not request.is_json:
            flash(f"Supplier purchase '{b_no}' deleted and stock reversed.", "success")
            return redirect(url_for("inventory_page"))

        return {
            "success": True,
            "bill_number": b_no,
            "message": f"Supplier purchase '{b_no}' deleted and stock reversed successfully."
        }
    except Exception as e:
        if not request.is_json:
            flash(f"Error deleting purchase: {e}", "error")
            return redirect(url_for("inventory_page"))
        return {"success": False, "error": str(e)}, 400

# ── API: Manual Stock Adjustment (Admin only) ──
@app.post("/api/inventory/adjust")
@admin_api_required
def api_adjust_inventory():
    try:
        data = request.get_json(force=True) if request.is_json else request.form.to_dict()
        item_id = int(data.get("item_id"))
        adj_type = data.get("adj_type")
        quantity = int(data.get("sheets_change") or data.get("quantity", 0))
        adj_date = data.get("adj_date") or get_ist_today_str()
        reason = (data.get("reason") or "").strip()
        user_name = "Admin"

        with db() as conn:
            with conn.cursor() as cur:
                i_name, old_bal, new_bal, change, m_type = process_stock_adjustment(
                    cur, item_id, adj_type, quantity, adj_date, reason, user_name=user_name
                )
            conn.commit()

        if not request.is_json:
            flash(f"Manual stock adjustment for '{i_name}': {change:+d} sheets (New balance: {new_bal}).", "success")
            return redirect(url_for("inventory_page"))

        return {
            "success": True,
            "item_name": i_name,
            "previous_balance": old_bal,
            "new_balance": new_bal,
            "quantity_change": change,
            "movement_type": m_type,
            "message": f"Stock adjusted for '{i_name}': {change:+d} sheets (New balance: {new_bal})."
        }
    except Exception as e:
        if not request.is_json:
            flash(f"Error adjusting stock: {e}", "error")
            return redirect(url_for("inventory_page"))
        return {"success": False, "error": str(e)}, 400

# ── API: Inspect Inventory Item for Removal (Admin only) ──
@app.get("/api/inventory/<int:item_id>/removal-info")
@admin_api_required
def api_inventory_removal_info(item_id):
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, item_name, category, size_spec, available_sheets, total_sheets, cost, is_active FROM inventory WHERE id = %s", (item_id,))
                item = cur.fetchone()
                if not item:
                    return {"success": False, "error": "Item not found."}, 404

                cur.execute("SELECT COUNT(*) AS c, COALESCE(SUM(quantity), 0) AS total_purchased FROM purchase_items WHERE item_id = %s", (item_id,))
                p_info = cur.fetchone()
                purch_c = p_info["c"]
                total_purchased = p_info["total_purchased"]

                cur.execute("SELECT COUNT(*) AS c FROM stock_movements WHERE item_id = %s", (item_id,))
                mov_c = cur.fetchone()["c"]

                cur.execute("SELECT COUNT(*) AS c FROM purchase_returns WHERE item_id = %s", (item_id,))
                ret_c = cur.fetchone()["c"]

                cur.execute("SELECT id, name FROM services WHERE paper_id = %s", (item_id,))
                services = [s["name"] for s in cur.fetchall()]

                total_tx = purch_c + mov_c + ret_c
                can_delete_permanently = (total_tx == 0 and len(services) == 0)

                return {
                    "success": True,
                    "item": dict(item),
                    "can_delete_permanently": can_delete_permanently,
                    "has_transactions": total_tx > 0,
                    "purchases_count": purch_c,
                    "total_purchased_sheets": total_purchased,
                    "movements_count": mov_c,
                    "returns_count": ret_c,
                    "linked_services": services,
                    "available_sheets": item["available_sheets"] or 0
                }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400

# ── API: Safe Remove / Archive Inventory Item (Admin only) ──
@app.post("/api/inventory/<int:item_id>/remove")
@admin_api_required
def api_inventory_remove(item_id):
    try:
        data = request.get_json(force=True) if request.is_json else request.form.to_dict()
        reason = (data.get("reason") or "Manual removal by Admin").strip()
        stock_treatment = (data.get("stock_treatment") or "zero_out").strip()
        user_name = "Admin"

        with db() as conn:
            with conn.cursor() as cur:
                msg = process_remove_inventory_item(cur, item_id, reason, stock_treatment, user_name)
            conn.commit()

        if not request.is_json:
            flash(msg, "success")
            return redirect(url_for("inventory_page"))

        return {"success": True, "message": msg}
    except Exception as e:
        if not request.is_json:
            flash(f"Error removing item: {e}", "error")
            return redirect(url_for("inventory_page"))
        return {"success": False, "error": str(e)}, 400

# ── API: Reactivate / Restore Inventory Item (Admin only) ──
@app.post("/api/inventory/<int:item_id>/reactivate")
@admin_api_required
def api_inventory_reactivate(item_id):
    try:
        user_name = "Admin"
        with db() as conn:
            with conn.cursor() as cur:
                msg = process_reactivate_inventory_item(cur, item_id, user_name)
            conn.commit()

        if not request.is_json:
            flash(msg, "success")
            return redirect(url_for("inventory_page"))

        return {"success": True, "message": msg}
    except Exception as e:
        if not request.is_json:
            flash(f"Error reactivating item: {e}", "error")
            return redirect(url_for("inventory_page"))
        return {"success": False, "error": str(e)}, 400

# ── Report Period Helper ──
def parse_report_period(args):
    """
    Parses reporting period from request args and returns:
    (period, start_date, end_date, selected_date, selected_month, nav_info, header_title)
    All dates are strings 'YYYY-MM-DD' aligned to Asia/Kolkata timezone.
    """
    period = args.get("period", "daily").lower()
    today_str = get_ist_today_str()
    today_d = get_ist_today()

    if period == "weekly":
        ref_str = args.get("date", today_str)
        try:
            ref_d = datetime.strptime(ref_str, "%Y-%m-%d").date()
        except Exception:
            ref_d = today_d
        
        # Monday to Sunday of the selected week
        start_d = ref_d - timedelta(days=ref_d.weekday())
        end_d = start_d + timedelta(days=6)
        start_date = start_d.strftime("%Y-%m-%d")
        end_date = end_d.strftime("%Y-%m-%d")
        
        prev_date = (start_d - timedelta(days=7)).strftime("%Y-%m-%d")
        next_date = (start_d + timedelta(days=7)).strftime("%Y-%m-%d")
        header_title = f"Week of {start_d.strftime('%d %b %Y')} – {end_d.strftime('%d %b %Y')}"
        nav_info = {
            "prev_url": url_for("reports", period="weekly", date=prev_date),
            "next_url": url_for("reports", period="weekly", date=next_date),
            "current_ref": start_date,
            "is_current": (start_d <= today_d <= end_d)
        }
        selected_date = ref_d.strftime("%Y-%m-%d")
        selected_month = start_d.strftime("%Y-%m")

    elif period == "monthly":
        month_str = args.get("month", today_d.strftime("%Y-%m"))
        try:
            parts = month_str.split("-")
            year, m_num = int(parts[0]), int(parts[1])
            start_d = date(year, m_num, 1)
        except Exception:
            year, m_num = today_d.year, today_d.month
            start_d = date(year, m_num, 1)
        
        _, num_days = calendar.monthrange(year, m_num)
        end_d = date(year, m_num, num_days)
        start_date = start_d.strftime("%Y-%m-%d")
        end_date = end_d.strftime("%Y-%m-%d")

        prev_m_d = start_d - timedelta(days=1)
        next_m_d = end_d + timedelta(days=1)
        prev_month = prev_m_d.strftime("%Y-%m")
        next_month = next_m_d.strftime("%Y-%m")

        header_title = f"Monthly Report: {start_d.strftime('%B %Y')}"
        nav_info = {
            "prev_url": url_for("reports", period="monthly", month=prev_month),
            "next_url": url_for("reports", period="monthly", month=next_month),
            "current_ref": start_d.strftime("%Y-%m"),
            "is_current": (start_d.year == today_d.year and start_d.month == today_d.month)
        }
        selected_date = today_str
        selected_month = start_d.strftime("%Y-%m")

    elif period == "custom":
        s_str = args.get("start_date", today_str)
        e_str = args.get("end_date", today_str)
        try:
            s_d = datetime.strptime(s_str, "%Y-%m-%d").date()
            e_d = datetime.strptime(e_str, "%Y-%m-%d").date()
            if s_d > e_d:
                s_d, e_d = e_d, s_d
        except Exception:
            s_d, e_d = today_d, today_d

        start_date = s_d.strftime("%Y-%m-%d")
        end_date = e_d.strftime("%Y-%m-%d")
        header_title = f"Custom Range: {s_d.strftime('%d %b %Y')} to {e_d.strftime('%d %b %Y')}"
        nav_info = {}
        selected_date = today_str
        selected_month = s_d.strftime("%Y-%m")

    else:
        period = "daily"
        date_str = args.get("date", today_str)
        try:
            cur_d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            cur_d = today_d
        
        start_date = cur_d.strftime("%Y-%m-%d")
        end_date = cur_d.strftime("%Y-%m-%d")
        prev_date = (cur_d - timedelta(days=1)).strftime("%Y-%m-%d")
        next_date = (cur_d + timedelta(days=1)).strftime("%Y-%m-%d")

        header_title = f"Daily Report: {cur_d.strftime('%d %b %Y (%A)')}"
        nav_info = {
            "prev_url": url_for("reports", period="daily", date=prev_date),
            "next_url": url_for("reports", period="daily", date=next_date),
            "current_ref": start_date,
            "is_current": (cur_d == today_d)
        }
        selected_date = start_date
        selected_month = cur_d.strftime("%Y-%m")

    return period, start_date, end_date, selected_date, selected_month, nav_info, header_title

# ── Admin Protected Reports & Profit Dashboard ──
@app.route("/reports")
@admin_required
def reports():
    period, start_date, end_date, selected_date, selected_month, nav_info, header_title = parse_report_period(request.args)
    is_admin = bool(session.get("is_admin"))
    start_utc_iso, end_utc_iso = ist_dates_to_utc_range(start_date, end_date)

    with db() as conn:
        with conn.cursor() as cur:
            # Summary (Bills count, Sales, Paper Cost, Profit)
            cur.execute("""
                SELECT COUNT(*) AS bills, 
                       COALESCE(SUM(subtotal),0) AS subtotal,
                       COALESCE(SUM(discount),0) AS discount, 
                       COALESCE(SUM(total),0) AS total,
                       COALESCE(SUM(paid),0) AS paid, 
                       COALESCE(SUM(balance),0) AS balance,
                       COALESCE(SUM(paper_cost),0) AS paper_cost,
                       COALESCE(SUM(profit),0) AS profit
                FROM bills 
                WHERE created_at >= %s AND created_at < %s 
                  AND is_deleted=0
            """, (start_utc_iso, end_utc_iso))
            summary = cur.fetchone()

            # Physical Paper sheets & units usage
            cur.execute("""
                SELECT COALESCE(SUM(i.paper_sheets),0) AS sheets,
                       COALESCE(SUM(i.color_units),0) AS color_units,
                       COALESCE(SUM(CASE WHEN i.print_type='bw' THEN i.quantity*i.pages_per_copy ELSE 0 END),0) AS bw_units,
                       COALESCE(SUM(CASE WHEN i.print_type NOT IN ('bw', 'color', 'photo') THEN i.quantity ELSE 0 END),0) AS other_units,
                       COALESCE(SUM(i.paper_cost),0) AS paper_cost
                FROM bill_items i JOIN bills b ON b.id=i.bill_id
                WHERE b.created_at >= %s AND b.created_at < %s 
                  AND b.is_deleted=0
            """, (start_utc_iso, end_utc_iso))
            usage = cur.fetchone()

            # Payment Methods Breakdown from bill_payments
            cur.execute("""
                SELECT bp.payment_method, COUNT(*) AS count, COALESCE(SUM(bp.amount),0) AS amount,
                       COALESCE(SUM(bp.amount),0) AS paid
                FROM bill_payments bp 
                JOIN bills b ON b.id=bp.bill_id
                WHERE bp.created_at >= %s AND bp.created_at < %s 
                  AND b.is_deleted=0 
                GROUP BY bp.payment_method
                ORDER BY amount DESC
            """, (start_utc_iso, end_utc_iso))
            payment_rows = cur.fetchall()
            if not payment_rows:
                # Fallback to bills table
                cur.execute("""
                    SELECT payment_method, COUNT(*) AS count, COALESCE(SUM(total),0) AS amount,
                           COALESCE(SUM(paid),0) AS paid
                    FROM bills 
                    WHERE created_at >= %s AND created_at < %s 
                      AND is_deleted=0 
                    GROUP BY payment_method
                    ORDER BY amount DESC
                """, (start_utc_iso, end_utc_iso))
                payment_rows = cur.fetchall()

            # Maintenance expenses for period
            cur.execute("""
                SELECT expense_date, category, title, amount 
                FROM maintenance_expenses 
                WHERE expense_date BETWEEN %s AND %s
                ORDER BY expense_date DESC
            """, (start_date, end_date))
            maintenance_rows = cur.fetchall()
            maintenance_total = sum(r['amount'] for r in maintenance_rows)

            # Net Profit = Billing Gross Profit - Maintenance Expenses
            net_profit = money(summary['profit'] - maintenance_total)

            # Service Performance with Profit Margin
            cur.execute("""
                SELECT i.service_name, i.print_type,
                       SUM(i.quantity*i.pages_per_copy) AS units, 
                       SUM(i.paper_sheets) AS sheets,
                       SUM(i.line_total) AS amount,
                       SUM(i.paper_cost) AS paper_cost,
                       SUM(i.profit) AS profit
                FROM bill_items i JOIN bills b ON b.id=i.bill_id
                WHERE b.created_at >= %s AND b.created_at < %s 
                  AND b.is_deleted=0
                GROUP BY i.service_name, i.print_type ORDER BY amount DESC
            """, (start_utc_iso, end_utc_iso))
            top_items = cur.fetchall()

            # Daily Breakdown Table (for Weekly, Monthly, Custom Range)
            daily_breakdown = []
            if period in ("weekly", "monthly", "custom"):
                # If weekly: show all 7 days of the week; if monthly/custom: show active days
                active_filter = "" if period == "weekly" else "WHERE COALESCE(db.bills_count, 0) > 0 OR COALESCE(dm.maint_amount, 0) > 0"
                cur.execute(f"""
                    WITH daily_bills AS (
                        SELECT 
                            to_char(created_at::timestamptz AT TIME ZONE 'Asia/Kolkata', 'YYYY-MM-DD') AS day_str,
                            COUNT(*) AS bills_count,
                            COALESCE(SUM(total), 0) AS gross_sales,
                            COALESCE(SUM(paid), 0) AS collected,
                            COALESCE(SUM(paper_cost), 0) AS paper_cost,
                            COALESCE(SUM(profit), 0) AS gross_profit
                        FROM bills
                        WHERE created_at >= %s AND created_at < %s
                          AND is_deleted = 0
                        GROUP BY 1
                    ),
                    daily_items AS (
                        SELECT 
                            to_char(b.created_at::timestamptz AT TIME ZONE 'Asia/Kolkata', 'YYYY-MM-DD') AS day_str,
                            COALESCE(SUM(i.paper_sheets), 0) AS paper_sheets
                        FROM bill_items i
                        JOIN bills b ON b.id = i.bill_id
                        WHERE b.created_at >= %s AND b.created_at < %s
                          AND b.is_deleted = 0
                        GROUP BY 1
                    ),
                    daily_maint AS (
                        SELECT 
                            expense_date AS day_str,
                            COALESCE(SUM(amount), 0) AS maint_amount
                        FROM maintenance_expenses
                        WHERE expense_date BETWEEN %s AND %s
                        GROUP BY 1
                    )
                    SELECT 
                        to_char(d.dt, 'YYYY-MM-DD') AS date_str,
                        to_char(d.dt, 'DD/MM/YYYY') AS date_formatted,
                        to_char(d.dt, 'Dy') AS day_name,
                        COALESCE(db.bills_count, 0) AS bills_count,
                        COALESCE(db.gross_sales, 0) AS gross_sales,
                        COALESCE(db.collected, 0) AS collected,
                        COALESCE(di.paper_sheets, 0) AS paper_sheets,
                        COALESCE(dm.maint_amount, 0) AS maint_amount,
                        COALESCE(db.gross_profit, 0) - COALESCE(dm.maint_amount, 0) AS net_profit
                    FROM generate_series(%s::date, %s::date, '1 day'::interval) d(dt)
                    LEFT JOIN daily_bills db ON db.day_str = to_char(d.dt, 'YYYY-MM-DD')
                    LEFT JOIN daily_items di ON di.day_str = to_char(d.dt, 'YYYY-MM-DD')
                    LEFT JOIN daily_maint dm ON dm.day_str = to_char(d.dt, 'YYYY-MM-DD')
                    {active_filter}
                    ORDER BY d.dt DESC
                """, (start_utc_iso, end_utc_iso, start_utc_iso, end_utc_iso, start_date, end_date, start_date, end_date))
                daily_breakdown = cur.fetchall()

    return render_template(
        "reports.html",
        period=period,
        start_date=start_date,
        end_date=end_date,
        selected_date=selected_date,
        selected_month=selected_month,
        nav_info=nav_info,
        header_title=header_title,
        summary=summary,
        usage=usage,
        payment_rows=payment_rows,
        maintenance_rows=maintenance_rows,
        maintenance_total=maintenance_total,
        net_profit=net_profit,
        top_items=top_items,
        daily_breakdown=daily_breakdown,
        is_admin=is_admin,
        today=get_ist_today_str()
    )

# ── CSV Export Route for Selected Report Period ──
@app.route("/reports/export")
@admin_required
def export_reports_csv():
    period, start_date, end_date, selected_date, selected_month, nav_info, header_title = parse_report_period(request.args)
    is_admin = bool(session.get("is_admin"))
    start_utc_iso, end_utc_iso = ist_dates_to_utc_range(start_date, end_date)

    with db() as conn:
        with conn.cursor() as cur:
            # Summary
            cur.execute("""
                SELECT COUNT(*) AS bills, 
                       COALESCE(SUM(subtotal),0) AS subtotal,
                       COALESCE(SUM(discount),0) AS discount, 
                       COALESCE(SUM(total),0) AS total,
                       COALESCE(SUM(paid),0) AS paid, 
                       COALESCE(SUM(balance),0) AS balance,
                       COALESCE(SUM(paper_cost),0) AS paper_cost,
                       COALESCE(SUM(profit),0) AS profit
                FROM bills 
                WHERE created_at >= %s AND created_at < %s 
                  AND is_deleted=0
            """, (start_utc_iso, end_utc_iso))
            summary = cur.fetchone()

            # Paper usage
            cur.execute("""
                SELECT COALESCE(SUM(i.paper_sheets),0) AS sheets,
                       COALESCE(SUM(i.color_units),0) AS color_units,
                       COALESCE(SUM(CASE WHEN i.print_type='bw' THEN i.quantity*i.pages_per_copy ELSE 0 END),0) AS bw_units,
                       COALESCE(SUM(CASE WHEN i.print_type NOT IN ('bw', 'color', 'photo') THEN i.quantity ELSE 0 END),0) AS other_units,
                       COALESCE(SUM(i.paper_cost),0) AS paper_cost
                FROM bill_items i JOIN bills b ON b.id=i.bill_id
                WHERE b.created_at >= %s AND b.created_at < %s 
                  AND b.is_deleted=0
            """, (start_utc_iso, end_utc_iso))
            usage = cur.fetchone()

            # Payments
            cur.execute("""
                SELECT bp.payment_method, COUNT(*) AS count, COALESCE(SUM(bp.amount),0) AS amount
                FROM bill_payments bp 
                JOIN bills b ON b.id=bp.bill_id
                WHERE bp.created_at >= %s AND bp.created_at < %s 
                  AND b.is_deleted=0 
                GROUP BY bp.payment_method
                ORDER BY amount DESC
            """, (start_utc_iso, end_utc_iso))
            payment_rows = cur.fetchall()
            if not payment_rows:
                cur.execute("""
                    SELECT payment_method, COUNT(*) AS count, COALESCE(SUM(total),0) AS amount
                    FROM bills 
                    WHERE created_at >= %s AND created_at < %s 
                      AND is_deleted=0 
                    GROUP BY payment_method
                    ORDER BY amount DESC
                """, (start_utc_iso, end_utc_iso))
                payment_rows = cur.fetchall()

            # Maintenance
            cur.execute("""
                SELECT expense_date, category, title, amount 
                FROM maintenance_expenses 
                WHERE expense_date BETWEEN %s AND %s
                ORDER BY expense_date DESC
            """, (start_date, end_date))
            maintenance_rows = cur.fetchall()
            maintenance_total = sum(r['amount'] for r in maintenance_rows)
            net_profit = money(summary['profit'] - maintenance_total)

            # Daily breakdown
            cur.execute("""
                WITH daily_bills AS (
                    SELECT 
                        to_char(created_at::timestamptz AT TIME ZONE 'Asia/Kolkata', 'YYYY-MM-DD') AS day_str,
                        COUNT(*) AS bills_count,
                        COALESCE(SUM(total), 0) AS gross_sales,
                        COALESCE(SUM(paid), 0) AS collected,
                        COALESCE(SUM(paper_cost), 0) AS paper_cost,
                        COALESCE(SUM(profit), 0) AS gross_profit
                    FROM bills
                    WHERE created_at >= %s AND created_at < %s
                      AND is_deleted = 0
                    GROUP BY 1
                ),
                daily_items AS (
                    SELECT 
                        to_char(b.created_at::timestamptz AT TIME ZONE 'Asia/Kolkata', 'YYYY-MM-DD') AS day_str,
                        COALESCE(SUM(i.paper_sheets), 0) AS paper_sheets
                    FROM bill_items i
                    JOIN bills b ON b.id = i.bill_id
                    WHERE b.created_at >= %s AND b.created_at < %s
                      AND b.is_deleted = 0
                    GROUP BY 1
                ),
                daily_maint AS (
                    SELECT 
                        expense_date AS day_str,
                        COALESCE(SUM(amount), 0) AS maint_amount
                    FROM maintenance_expenses
                    WHERE expense_date BETWEEN %s AND %s
                    GROUP BY 1
                )
                SELECT 
                    to_char(d.dt, 'YYYY-MM-DD') AS date_str,
                    to_char(d.dt, 'DD/MM/YYYY') AS date_formatted,
                    to_char(d.dt, 'Dy') AS day_name,
                    COALESCE(db.bills_count, 0) AS bills_count,
                    COALESCE(db.gross_sales, 0) AS gross_sales,
                    COALESCE(db.collected, 0) AS collected,
                    COALESCE(di.paper_sheets, 0) AS paper_sheets,
                    COALESCE(dm.maint_amount, 0) AS maint_amount,
                    COALESCE(db.gross_profit, 0) - COALESCE(dm.maint_amount, 0) AS net_profit
                FROM generate_series(%s::date, %s::date, '1 day'::interval) d(dt)
                LEFT JOIN daily_bills db ON db.day_str = to_char(d.dt, 'YYYY-MM-DD')
                LEFT JOIN daily_items di ON di.day_str = to_char(d.dt, 'YYYY-MM-DD')
                LEFT JOIN daily_maint dm ON dm.day_str = to_char(d.dt, 'YYYY-MM-DD')
                ORDER BY d.dt DESC
            """, (start_utc_iso, end_utc_iso, start_utc_iso, end_utc_iso, start_date, end_date, start_date, end_date))
            daily_breakdown = cur.fetchall()

            # Service Performance
            cur.execute("""
                SELECT i.service_name, i.print_type,
                       SUM(i.quantity*i.pages_per_copy) AS units, 
                       SUM(i.paper_sheets) AS sheets,
                       SUM(i.line_total) AS amount,
                       SUM(i.paper_cost) AS paper_cost,
                       SUM(i.profit) AS profit
                FROM bill_items i JOIN bills b ON b.id=i.bill_id
                WHERE b.created_at >= %s AND b.created_at < %s 
                  AND b.is_deleted=0
                GROUP BY i.service_name, i.print_type ORDER BY amount DESC
            """, (start_utc_iso, end_utc_iso))
            top_items = cur.fetchall()

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Title & Metadata
    writer.writerow(["IREAD BILLING APP - SHOP PERFORMANCE REPORT"])
    writer.writerow(["Period", period.upper()])
    writer.writerow(["Date Range", f"{start_date} to {end_date}"])
    writer.writerow(["Generated At (IST)", get_ist_now().strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow([])

    # Financial Summary
    writer.writerow(["FINANCIAL SUMMARY"])
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Bills Generated", summary["bills"]])
    writer.writerow(["Total Subtotal (INR)", f"{summary['subtotal']:.2f}"])
    writer.writerow(["Total Discount (INR)", f"{summary['discount']:.2f}"])
    writer.writerow(["Gross Sales (INR)", f"{summary['total']:.2f}"])
    writer.writerow(["Amount Collected (INR)", f"{summary['paid']:.2f}"])
    writer.writerow(["Balance Due (INR)", f"{summary['balance']:.2f}"])
    if is_admin:
        writer.writerow(["Estimated Paper Cost (INR)", f"{summary['paper_cost']:.2f}"])
        writer.writerow(["Billing Gross Profit (INR)", f"{summary['profit']:.2f}"])
        writer.writerow(["Maintenance Expenses (INR)", f"{maintenance_total:.2f}"])
        writer.writerow(["Net Profit (INR)", f"{net_profit:.2f}"])
    writer.writerow(["Paper Sheets Used", usage["sheets"]])
    writer.writerow(["B&W Units", usage["bw_units"]])
    writer.writerow(["Colour Units", usage["color_units"]])
    writer.writerow([])

    # Payment Methods
    writer.writerow(["PAYMENT METHODS BREAKDOWN"])
    writer.writerow(["Method", "Transactions", "Amount (INR)"])
    for p in payment_rows:
        writer.writerow([p["payment_method"], p["count"], f"{p['amount']:.2f}"])
    writer.writerow([])

    # Daily Breakdown Table
    writer.writerow(["DAILY BREAKDOWN"])
    daily_headers = ["Date", "Day", "Bills Count", "Gross Sales (INR)", "Collected (INR)", "Paper Sheets"]
    if is_admin:
        daily_headers.extend(["Maintenance (INR)", "Net Profit (INR)"])
    writer.writerow(daily_headers)
    for d in daily_breakdown:
        if d["bills_count"] > 0 or d["maint_amount"] > 0 or period == "weekly":
            row = [d["date_formatted"], d["day_name"], d["bills_count"], f"{d['gross_sales']:.2f}", f"{d['collected']:.2f}", d["paper_sheets"]]
            if is_admin:
                row.extend([f"{d['maint_amount']:.2f}", f"{d['net_profit']:.2f}"])
            writer.writerow(row)
    writer.writerow([])

    # Service Performance
    writer.writerow(["SERVICE PERFORMANCE BREAKDOWN"])
    svc_headers = ["Service Name", "Category", "Units Billed", "Sheets Consumed", "Total Sales (INR)"]
    if is_admin:
        svc_headers.extend(["Paper Cost (INR)", "Gross Profit (INR)", "Profit Margin %"])
    writer.writerow(svc_headers)
    for s in top_items:
        margin_pct = f"{(s['profit'] / s['amount'] * 100):.1f}%" if s['amount'] > 0 else "0%"
        row = [s["service_name"], s["print_type"].upper(), s["units"], s["sheets"], f"{s['amount']:.2f}"]
        if is_admin:
            row.extend([f"{s['paper_cost']:.2f}", f"{s['profit']:.2f}", margin_pct])
        writer.writerow(row)

    csv_data = output.getvalue()
    filename = f"iread_report_{period}_{start_date}_to_{end_date}.csv"
    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ── Price List & Items Config (Admin only) ──
@app.route("/services", methods=["GET", "POST"])
@admin_required
def services():
    with db() as conn:
        with conn.cursor() as cur:
            if request.method == "POST":
                action = request.form.get("action")

                if action == "add":
                    name = request.form.get("name", "").strip()
                    try:
                        rate = money(request.form.get("rate", 0))
                        double_rate_val = request.form.get("double_rate", "").strip()
                        double_rate = money(double_rate_val) if double_rate_val else None
                        extra_copy_val = request.form.get("extra_copy_rate", "").strip()
                        extra_copy_rate = money(extra_copy_val) if extra_copy_val else None
                        print_type = request.form.get("print_type", "bw")
                        paper_size = request.form.get("paper_size", "A4").strip() or "A4"
                        sheets_per_unit = max(0, int(request.form.get("sheets_per_unit", 1)))
                        paper_id_val = request.form.get("paper_id", "").strip()
                        paper_id = int(paper_id_val) if paper_id_val else None

                        if not name or rate < 0:
                            raise ValueError("Invalid name or rate.")

                        cur.execute(
                            """INSERT INTO services(name, rate, double_rate, extra_copy_rate, print_type, paper_size, sheets_per_unit, paper_id, active) 
                               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,1)""",
                            (name, rate, double_rate, extra_copy_rate, print_type, paper_size, sheets_per_unit, paper_id)
                        )
                        conn.commit()
                        flash("Service added.", "success")
                    except psycopg2.errors.UniqueViolation:
                        conn.rollback()
                        flash("A service with that name already exists.", "error")
                    except ValueError as e:
                        flash(f"Check the service details: {e}", "error")

                elif action == "update":
                    ids = request.form.getlist("service_id[]")
                    names = request.form.getlist("service_name[]")
                    rates = request.form.getlist("service_rate[]")
                    double_rates = request.form.getlist("service_double_rate[]")
                    extra_copy_rates = request.form.getlist("service_extra_copy_rate[]")
                    types = request.form.getlist("service_type[]")
                    sizes = request.form.getlist("service_size[]")
                    paper_ids = request.form.getlist("service_paper_id[]")
                    updated_count = 0

                    for i in range(len(ids)):
                        try:
                            sid = int(ids[i])
                            clean_name = names[i].strip()
                            clean_rate = max(0, money(rates[i]))
                            d_val = double_rates[i].strip() if i < len(double_rates) else ""
                            clean_double_rate = money(d_val) if d_val else None
                            e_val = extra_copy_rates[i].strip() if i < len(extra_copy_rates) else ""
                            clean_extra_rate = money(e_val) if e_val else None
                            clean_type = types[i].strip() if types[i] else "bw"
                            clean_size = sizes[i].strip() if sizes[i] else "A4"
                            p_id_str = paper_ids[i].strip() if i < len(paper_ids) else ""
                            p_id = int(p_id_str) if p_id_str else None

                            if clean_name:
                                cur.execute("""
                                    UPDATE services 
                                    SET name=%s, rate=%s, double_rate=%s, extra_copy_rate=%s, print_type=%s, paper_size=%s, paper_id=%s
                                    WHERE id=%s
                                """, (clean_name, clean_rate, clean_double_rate, clean_extra_rate, clean_type, clean_size, p_id, sid))
                                updated_count += 1

                                if sid == 52 or ("print b&w" in clean_name.lower() and "a4" in clean_name.lower()):
                                    now_ts = to_utc_iso()
                                    cur.execute("""
                                        INSERT INTO app_settings (key, value, updated_at)
                                        VALUES 
                                            ('pricing_rule_print_bw_a4_single', %s, %s),
                                            ('pricing_rule_print_bw_a4_double', %s, %s),
                                            ('pricing_rule_print_bw_a4_extra', %s, %s)
                                        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at
                                    """, (str(clean_rate), now_ts, str(clean_double_rate or clean_rate), now_ts, str(clean_extra_rate or 0), now_ts))
                        except Exception as e:
                            print(f"Error updating service: {e}")

                    conn.commit()
                    flash(f"Updated {updated_count} item(s).", "success")

                elif action == "delete":
                    try:
                        sid = int(request.form.get("service_id"))
                        cur.execute("DELETE FROM services WHERE id=%s", (sid,))
                        conn.commit()
                        flash("Item removed successfully.", "success")
                    except Exception as e:
                        conn.rollback()
                        flash(f"Error removing item: {e}", "error")

                elif action == "toggle":
                    sid = int(request.form.get("service_id"))
                    cur.execute("UPDATE services SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=%s", (sid,))
                    conn.commit()
                    flash("Service visibility updated.", "success")

                invalidate_services_cache()
                return redirect(url_for("services"))

            # Active items for services page
            cur.execute("""
            SELECT s.*, i.item_name AS linked_paper_name
            FROM services s
            LEFT JOIN inventory i ON s.paper_id = i.id
            ORDER BY s.active DESC, s.print_type, s.name
            """)
            services_rows = cur.fetchall()

            # All available active papers for mapping dropdown
            cur.execute("SELECT id, item_name, size_spec FROM inventory WHERE is_active = 1 ORDER BY item_name")
            papers = cur.fetchall()

    return render_template("services.html", services=services_rows, papers=papers)

@app.route("/export.csv")
@admin_required
def export_csv():
    import csv, io
    q = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "all").strip()
    period = request.args.get("period", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    start_d, end_d, _ = get_period_date_range(period, start_date, end_date)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Bill No", "Date/Time", "Customer", "Payment Method", "Status", "Subtotal", "Discount", "Total", "Paid", "Balance", "Paper Cost", "Gross Profit"])
    with db() as conn:
        with conn.cursor() as cur:
            query = "SELECT bill_no,created_at,customer,payment_method,payment_status,subtotal,discount,total,paid,balance,paper_cost,profit FROM bills WHERE is_deleted=0"
            params = []
            if q:
                query += " AND (bill_no ILIKE %s OR customer ILIKE %s)"
                params.extend([f"%{q}%", f"%{q}%"])
            if status_filter in ("Paid", "Unpaid", "Partially Paid"):
                query += " AND payment_status = %s"
                params.append(status_filter)
            start_utc_iso, end_utc_iso = ist_dates_to_utc_range(start_d, end_d)
            if start_utc_iso and end_utc_iso:
                query += " AND created_at >= %s AND created_at < %s"
                params.extend([start_utc_iso, end_utc_iso])
            elif start_utc_iso:
                query += " AND created_at >= %s"
                params.append(start_utc_iso)
            elif end_utc_iso:
                query += " AND created_at < %s"
                params.append(end_utc_iso)
            query += " ORDER BY id DESC"
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            formatted_rows = []
            for r in rows:
                r_vals = list(r.values())
                if len(r_vals) > 1 and r_vals[1]:
                    r_vals[1] = format_ist_datetime_str(r_vals[1])
                formatted_rows.append(r_vals)
            writer.writerows(formatted_rows)
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=iread_bills.csv"
    return response

@app.route("/backup")
@admin_required
def backup():
    return "<h2>PostgreSQL Database</h2><p>Data is stored on Aiven cloud PostgreSQL. Use the <a href='/export.csv'>Export CSV</a> option to download a backup.</p><p><a href='/'>Back to billing</a></p>"

if __name__ == "__main__":
    init_db()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5001))
    print(f"Iread Print Billing is running at http://{host}:{port} (LAN: http://192.168.1.131:{port})")
    app.run(host=host, port=port, debug=False)
