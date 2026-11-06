from flask import Flask, render_template, request, redirect, url_for, flash, make_response, session
import psycopg2
import psycopg2.extras
from pathlib import Path
from datetime import datetime, date
import os
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "iread@123")

APP_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    static_folder=str(APP_DIR / "static"),
    template_folder=str(APP_DIR / "templates"),
)
app.secret_key = os.environ.get("SECRET_KEY", "iread-print-billing-secret-key-2026")
app.debug = False

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

def db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

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
                    updated_at TEXT NOT NULL
                );
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

                -- Migrations for Payment Status, Direct Printing & Audit
                ALTER TABLE bills ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'Paid';
                ALTER TABLE bills ADD COLUMN IF NOT EXISTS is_deleted INTEGER NOT NULL DEFAULT 0;

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

                -- Backfill purchase_items from existing purchases if not already backfilled
                INSERT INTO purchase_items (purchase_id, item_id, item_name, category, quantity, unit_cost, line_total, created_at)
                SELECT p.id, p.item_id, p.item_name, p.category, p.total_sheets, 
                       CASE WHEN p.total_sheets > 0 THEN (p.total_amount::numeric / p.total_sheets)::real ELSE 0 END, 
                       p.total_amount, p.created_at
                FROM purchases p
                WHERE p.item_name IS NOT NULL AND p.item_name != ''
                  AND NOT EXISTS (SELECT 1 FROM purchase_items pi WHERE pi.purchase_id = p.id);
                """)

                # Seed essential paper stock if empty
                cur.execute("SELECT COUNT(*) AS c FROM inventory")
                if cur.fetchone()["c"] == 0:
                    now_iso = datetime.now().isoformat(timespec="seconds")
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
            conn.commit()
    except Exception as e:
        print(f"init_db skipped or failed: {e}")

def money(v):
    return round(float(v or 0), 2)

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

# ── Auth Routes ──
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Welcome back, Admin!", "success")
            next_url = request.args.get("next") or url_for("reports")
            return redirect(next_url)
        else:
            flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("is_admin", None)
    flash("Logged out successfully.", "success")
    return redirect(url_for("index"))

# ── Desktop / Install App Route ──
@app.route("/install")
def install_page():
    return render_template("install.html")

# ── Paper & Stock Inventory Helper Functions ──

def process_create_purchase(cur, data, is_admin, biller_default="Staff"):
    now = datetime.now().isoformat(timespec="seconds")
    supplier_name = (data.get("supplier_name") or "").strip()
    bill_number = (data.get("bill_number") or "").strip()
    purchase_date = data.get("purchase_date") or date.today().isoformat()
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


def process_edit_purchase(cur, purchase_id, data, user_name="Admin"):
    now = datetime.now().isoformat(timespec="seconds")
    cur.execute("SELECT * FROM purchases WHERE id=%s AND is_deleted=0 FOR UPDATE", (purchase_id,))
    purchase = cur.fetchone()
    if not purchase:
        raise ValueError("Purchase bill not found or already deleted.")

    cur.execute("SELECT * FROM purchase_items WHERE purchase_id=%s", (purchase_id,))
    old_items = cur.fetchall()

    supplier_name = (data.get("supplier_name") or purchase["supplier_name"]).strip()
    bill_number = (data.get("bill_number") or purchase["bill_number"]).strip()
    purchase_date = data.get("purchase_date") or purchase["purchase_date"]
    biller_name = (data.get("biller_name") or purchase["biller_name"]).strip()
    notes = (data.get("notes") or "").strip()
    raw_new_items = data.get("items") or []

    if not raw_new_items:
        raise ValueError("Purchase must contain at least one item.")

    parsed_new_items = []
    new_total_amount = 0.0
    new_total_sheets = 0
    for it in raw_new_items:
        i_name = (it.get("item_name") or "").strip()
        if not i_name:
            continue
        cat = (it.get("category") or "Paper").strip()
        size = (it.get("size_spec") or "A4").strip()
        qty = max(1, int(it.get("quantity") or it.get("qty") or 0))
        unit_cost = max(0.0, float(it.get("unit_cost") or it.get("rate") or 0))
        line_total = round(qty * unit_cost, 2)
        new_total_amount += line_total
        new_total_sheets += qty
        parsed_new_items.append({
            "item_name": i_name,
            "category": cat,
            "size_spec": size,
            "quantity": qty,
            "unit_cost": unit_cost,
            "line_total": line_total
        })

    if not parsed_new_items:
        raise ValueError("At least one valid paper item with name and quantity is required.")

    # Check consumed stock constraint:
    for old_it in old_items:
        i_id = old_it.get("item_id")
        if i_id:
            cur.execute("SELECT item_name, available_sheets FROM inventory WHERE id=%s FOR UPDATE", (i_id,))
            inv = cur.fetchone()
            if inv:
                matching_new = next((n for n in parsed_new_items if n["item_name"].lower() == inv["item_name"].lower()), None)
                new_qty = matching_new["quantity"] if matching_new else 0
                net_reduction = old_it["quantity"] - new_qty
                if net_reduction > 0 and inv["available_sheets"] < net_reduction:
                    raise ValueError(
                        f"Cannot edit purchase: {net_reduction - inv['available_sheets']} sheets of '{inv['item_name']}' have already been consumed in billing. "
                        f"Reversing this purchase would cause a negative stock balance (Available: {inv['available_sheets']} sheets, Reduction: {net_reduction} sheets)."
                    )

    # Reversal of old items from inventory
    for old_it in old_items:
        i_id = old_it.get("item_id")
        if i_id:
            cur.execute("SELECT id, available_sheets, total_sheets, cost FROM inventory WHERE id=%s FOR UPDATE", (i_id,))
            inv = cur.fetchone()
            if inv:
                prev_bal = inv["available_sheets"]
                new_avail = max(0, prev_bal - old_it["quantity"])
                new_tot = max(0, inv["total_sheets"] - old_it["quantity"])
                new_cost = max(0.0, round(inv["cost"] - old_it["line_total"], 2))
                cur.execute("UPDATE inventory SET available_sheets=%s, total_sheets=%s, cost=%s, updated_at=%s WHERE id=%s", (new_avail, new_tot, new_cost, now, i_id))
                cur.execute("""
                INSERT INTO stock_movements (item_id, movement_type, quantity, previous_balance, balance_after, reference_id, notes, recorded_by, movement_date, created_at)
                VALUES (%s, 'PURCHASE_REVISE_REVERSAL', %s, %s, %s, %s, 'Edit purchase reversal', %s, %s, %s)
                """, (i_id, -old_it["quantity"], prev_bal, new_avail, bill_number, user_name, purchase_date, now))

    # Delete old purchase items
    cur.execute("DELETE FROM purchase_items WHERE purchase_id=%s", (purchase_id,))

    # Insert new purchase items and apply to inventory
    for it in parsed_new_items:
        cur.execute("SELECT id, total_sheets, available_sheets, cost FROM inventory WHERE item_name ILIKE %s AND size_spec ILIKE %s", (it["item_name"], it["size_spec"]))
        existing = cur.fetchone()
        if not existing:
            cur.execute("SELECT id, total_sheets, available_sheets, cost FROM inventory WHERE item_name ILIKE %s", (it["item_name"],))
            existing = cur.fetchone()

        if existing:
            item_id = existing["id"]
            prev_bal = existing["available_sheets"]
            new_avail = prev_bal + it["quantity"]
            new_tot = existing["total_sheets"] + it["quantity"]
            new_cost = round(existing["cost"] + it["line_total"], 2)
            cur.execute("UPDATE inventory SET available_sheets=%s, total_sheets=%s, cost=%s, updated_at=%s WHERE id=%s", (new_avail, new_tot, new_cost, now, item_id))
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
        VALUES (%s, 'PURCHASE_REVISE_ADD', %s, %s, %s, %s, 'Edit purchase addition', %s, %s, %s)
        """, (item_id, it["quantity"], prev_bal, new_avail, bill_number, user_name, purchase_date, now))

    # Recalculate totals and status
    new_total_amount = round(new_total_amount, 2)
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

    new_balance = max(0.0, round(new_total_amount - total_paid_recorded, 2))
    if total_paid_recorded >= new_total_amount and new_total_amount > 0:
        new_status = "Paid"
    elif total_paid_recorded <= 0.001:
        new_status = "Unpaid"
    else:
        new_status = "Partially Paid"

    summary_name = parsed_new_items[0]["item_name"]
    if len(parsed_new_items) > 1:
        summary_name = f"{len(parsed_new_items)} items ({parsed_new_items[0]['item_name']}, +{len(parsed_new_items)-1} more)"

    cur.execute("""
    UPDATE purchases 
    SET supplier_name=%s, bill_number=%s, purchase_date=%s, biller_name=%s,
        item_name=%s, total_sheets=%s, total_amount=%s, paid_amount=%s, balance_amount=%s,
        payment_status=%s, notes=%s
    WHERE id=%s
    """, (supplier_name, bill_number, purchase_date, biller_name, summary_name, new_total_sheets, new_total_amount, total_paid_recorded, new_balance, new_status, notes, purchase_id))

    cur.execute("""
    INSERT INTO purchase_audit_log (purchase_id, bill_number, action, performed_by, details, created_at)
    VALUES (%s, %s, 'EDIT', %s, %s, %s)
    """, (purchase_id, bill_number, user_name, f"Edited purchase {bill_number}: Total changed from ₹{purchase['total_amount']} to ₹{new_total_amount}.", now))

    return purchase_id, bill_number, new_total_amount, total_paid_recorded, new_balance, new_status


def process_delete_purchase(cur, purchase_id, reason="Admin deletion", user_name="Admin"):
    now = datetime.now().isoformat(timespec="seconds")
    cur.execute("SELECT * FROM purchases WHERE id=%s AND is_deleted=0 FOR UPDATE", (purchase_id,))
    purchase = cur.fetchone()
    if not purchase:
        raise ValueError("Purchase bill not found or already deleted.")

    cur.execute("SELECT * FROM purchase_items WHERE purchase_id=%s", (purchase_id,))
    items = cur.fetchall()

    # Check consumed stock constraint
    for it in items:
        i_id = it.get("item_id")
        if i_id:
            cur.execute("SELECT item_name, available_sheets FROM inventory WHERE id=%s FOR UPDATE", (i_id,))
            inv = cur.fetchone()
            if inv:
                if inv["available_sheets"] < it["quantity"]:
                    consumed = it["quantity"] - inv["available_sheets"]
                    raise ValueError(
                        f"Cannot delete purchase: {consumed} sheets of '{inv['item_name']}' have already been consumed in billing. "
                        f"Reversing this purchase would cause a negative stock balance (Available: {inv['available_sheets']} sheets, Purchase quantity: {it['quantity']} sheets)."
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
                new_cost = max(0.0, round(inv["cost"] - it["line_total"], 2))
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
    now = datetime.now().isoformat(timespec="seconds")
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
                now = datetime.now().isoformat(timespec="seconds")

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
                            "purchase_date": request.form.get("purchase_date") or date.today().isoformat(),
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
                        adj_date = request.form.get("adj_date") or date.today().isoformat()
                        reason = request.form.get("reason", "").strip()

                        i_name, old_bal, new_bal, change, m_type = process_stock_adjustment(
                            cur, item_id, adj_type, quantity, adj_date, reason, user_name=user_name
                        )
                        conn.commit()
                        flash(f"Manual stock adjustment for '{i_name}': {change:+d} sheets (New balance: {new_bal}).", "success")
                    except Exception as e:
                        conn.rollback()
                        flash(f"Error adjusting stock: {e}", "error")

                # Action: Delete stock item (Admin only)
                elif action == "delete":
                    if not is_admin:
                        flash("Admin login required to delete stock items.", "error")
                        return redirect(url_for("login", next=request.path))
                    try:
                        item_id = int(request.form.get("item_id"))
                        cur.execute("DELETE FROM inventory WHERE id=%s", (item_id,))
                        conn.commit()
                        flash("Inventory entry removed.", "success")
                    except Exception as e:
                        conn.rollback()
                        flash(f"Error removing entry: {e}", "error")

                return redirect(url_for("inventory_page"))

            # Fetch inventory items with calculated sheet cost
            cur.execute("""
            SELECT id, category, item_name, size_spec, bundles, sheets_per_bundle, total_sheets, available_sheets, reorder_level, cost, notes, updated_at,
                   ROUND((cost / NULLIF(total_sheets, 0))::numeric, 3) AS cost_per_sheet
            FROM inventory 
            ORDER BY category, item_name
            """)
            items = cur.fetchall()
            for r in items:
                r['cost_per_sheet'] = float(r['cost_per_sheet'] or 0.0)

            total_items = len(items)
            total_available_sheets = sum(row.get("available_sheets", 0) for row in items)
            total_valuation = sum(row.get("available_sheets", 0) * row.get("cost_per_sheet", 0.0) for row in items)
            low_stock_items = [r for r in items if r.get('available_sheets', 0) <= r.get('reorder_level', 100)]

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
                   COALESCE(SUM(paid_amount), 0) AS total_paid_supplier,
                   COALESCE(SUM(balance_amount), 0) AS total_supplier_balance,
                   COUNT(CASE WHEN balance_amount > 0.001 THEN 1 END) AS pending_purchases_count
            FROM purchases
            WHERE is_deleted = 0
            """)
            purchase_stats = cur.fetchone()

    return render_template(
        "inventory.html",
        inventory=items,
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
                    expense_date = request.form.get("expense_date") or date.today().isoformat()
                    technician_or_vendor = request.form.get("technician_or_vendor", "").strip()
                    notes = request.form.get("notes", "").strip()
                    created_at = datetime.now().isoformat(timespec="seconds")

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

    return render_template("maintenance.html", expenses=rows, total_count=total_count, total_expense=total_expense, today=date.today().isoformat())

# ── Billing Route (Fast Touch POS) ──
@app.route("/")
def index():
    if not DATABASE_URL:
        return "DATABASE_URL environment variable is missing.", 500
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM services WHERE active=1 ORDER BY print_type, name")
                services = cur.fetchall()
                today = date.today().isoformat()
                cur.execute("SELECT COALESCE(SUM(total),0) AS today_total FROM bills WHERE substr(created_at,1,10)=%s AND is_deleted=0", (today,))
                row = cur.fetchone()
                today_total = row['today_total'] if row else 0
                cur.execute("SELECT COUNT(*) AS today_count FROM bills WHERE substr(created_at,1,10)=%s AND is_deleted=0", (today,))
                row = cur.fetchone()
                today_count = row['today_count'] if row else 0
        return render_template("index.html", services=services, today_total=today_total, today_count=today_count)
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

    with db() as conn:
        with conn.cursor() as cur:
            # Build sheet cost lookup from current inventory
            cur.execute("""
            SELECT id, item_name, size_spec, available_sheets, 
                   ROUND((cost / NULLIF(total_sheets,0))::numeric, 4) AS cost_per_sheet
            FROM inventory
            """)
            inv_rows = cur.fetchall()
            inv_map = {r['id']: float(r['cost_per_sheet'] or 0.0) for r in inv_rows}
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
                    cur.execute("SELECT * FROM services WHERE id=%s", (service_id_int,))
                    service = cur.fetchone()

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

                # Physical sheets calculation: 1 physical sheet for 2 double-sided pages
                if sheets_per_unit == 0:
                    sheets = 0
                elif is_double:
                    sheets = qty * ((pages_per_copy + 1) // 2)
                else:
                    sheets = qty * pages_per_copy

                line_total = money(qty * pages_per_copy * rate)
                color_units = qty * pages_per_copy if p_type in ("color", "photo") else 0

                # Determine cost per sheet from inventory
                unit_cost = 0.0
                matched_inventory_id = paper_id
                if matched_inventory_id and matched_inventory_id in inv_map:
                    unit_cost = inv_map[matched_inventory_id]
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

            now_iso = datetime.now().isoformat(timespec="seconds")
            bill_no = "IR" + datetime.now().strftime("%y%m%d%H%M%S")

            # Avoid bill_no collisions
            original = bill_no
            suffix   = 1
            cur.execute("SELECT 1 FROM bills WHERE bill_no=%s", (bill_no,))
            while cur.fetchone():
                bill_no = f"{original}{suffix}"
                suffix += 1
                cur.execute("SELECT 1 FROM bills WHERE bill_no=%s", (bill_no,))

            # Insert Bill record with payment_status, paper_cost and profit
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

            # Insert Bill Items
            for x in items:
                cur.execute(
                    """INSERT INTO bill_items(bill_id, service_name, print_type, paper_size, quantity, pages_per_copy, sides, rate, line_total, paper_sheets, color_units, paper_cost, profit)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (bill_id, x["service_name"], x["print_type"], x["paper_size"], x["quantity"], x["pages_per_copy"],
                     x["sides"], x["rate"], x["line_total"], x["paper_sheets"], x["color_units"], x["paper_cost"], x["profit"])
                )

                # Automatic Paper Stock Deduction & Ledger Recording
                inv_id = x.get("inventory_id")
                sheets_used = x.get("paper_sheets", 0)
                if inv_id and sheets_used > 0:
                    cur.execute("SELECT available_sheets, item_name FROM inventory WHERE id=%s FOR UPDATE", (inv_id,))
                    inv_row = cur.fetchone()
                    if inv_row:
                        new_avail = max(0, inv_row['available_sheets'] - sheets_used)
                        cur.execute("UPDATE inventory SET available_sheets=%s, updated_at=%s WHERE id=%s", (new_avail, now_iso, inv_id))
                        cur.execute("""
                        INSERT INTO stock_movements (item_id, movement_type, quantity, balance_after, reference_id, notes, created_at)
                        VALUES (%s, 'SALE', %s, %s, %s, %s, %s)
                        """, (inv_id, -sheets_used, new_avail, bill_no, f"Billed: {x['service_name']} ({x['sides']})", now_iso))

        conn.commit()

    return redirect(url_for("receipt", bill_id=bill_id))

@app.route("/receipt/<int:bill_id>")
def receipt(bill_id):
    auto_print = (request.args.get("auto") == "1")
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bills WHERE id=%s", (bill_id,))
            bill = cur.fetchone()
            cur.execute("SELECT * FROM bill_items WHERE bill_id=%s", (bill_id,))
            items = cur.fetchall()
    if not bill:
        return "Bill not found", 404
    return render_template("receipt.html", bill=bill, items=items, auto_print=auto_print)

# ── API: High-Speed Billing Endpoint (Instant Save & Print) ──
@app.post("/api/create-bill")
def create_bill_api():
    try:
        data = request.get_json(force=True) or {}
        customer = (data.get("customer") or "").strip()
        payment = data.get("payment_method") or "Cash"
        discount = money(data.get("discount", 0))
        paid_input = str(data.get("paid", "")).strip()
        req_status = (data.get("payment_status") or "").strip()
        notes = (data.get("notes") or "").strip()
        raw_items = data.get("items") or []

        if not raw_items:
            return {"success": False, "error": "Cart is empty."}, 400

        items = []
        subtotal = 0.0
        total_bill_paper_cost = 0.0

        with db() as conn:
            with conn.cursor() as cur:
                # Pre-fetch inventory cost lookup
                cur.execute("""
                SELECT id, item_name, size_spec, available_sheets, 
                       ROUND((cost / NULLIF(total_sheets,0))::numeric, 4) AS cost_per_sheet
                FROM inventory
                """)
                inv_rows = cur.fetchall()
                inv_map = {r['id']: float(r['cost_per_sheet'] or 0.0) for r in inv_rows}
                inv_by_size = {}
                for r in inv_rows:
                    key = (r['size_spec'] or '').strip().upper()
                    if key and key not in inv_by_size:
                        inv_by_size[key] = (r['id'], float(r['cost_per_sheet'] or 0.0))

                for it in raw_items:
                    s_id = str(it.get("service_id", "")).strip()
                    try:
                        qty = max(1, int(it.get("qty", 1)))
                        pages_per_copy = max(1, int(it.get("pages", 1))) if it.get("pages") else 1
                        rate = money(it.get("rate", 0))
                    except (ValueError, TypeError):
                        continue

                    sides = it.get("sides") or "Single"
                    is_double = sides.lower().startswith("double")

                    service = None
                    if s_id and s_id != 'custom':
                        try:
                            cur.execute("SELECT * FROM services WHERE id=%s", (int(s_id),))
                            service = cur.fetchone()
                        except (ValueError, TypeError):
                            pass

                    if service:
                        s_name = service["name"]
                        p_type = service["print_type"]
                        p_size = service["paper_size"]
                        paper_id = service.get("paper_id")
                        sheets_per_unit = service.get("sheets_per_unit", 1)
                    else:
                        s_name = (it.get("name") or "Custom Service").strip()
                        p_type = "service"
                        p_size = "A4"
                        paper_id = None
                        sheets_per_unit = 1

                    # Physical sheets: Single = 1 sheet per copy, Double = 1 sheet per 2 copies (ceil(qty/2))
                    if sheets_per_unit == 0:
                        sheets = 0
                    elif is_double:
                        sheets = (qty + 1) // 2
                    else:
                        sheets = qty

                    line_total = money(qty * rate)
                    color_units = qty if p_type in ("color", "photo") else 0

                    unit_cost = 0.0
                    matched_inv_id = paper_id
                    if matched_inv_id and matched_inv_id in inv_map:
                        unit_cost = inv_map[matched_inv_id]
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
                        "pages_per_copy": 1,
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
                    return {"success": False, "error": "No valid items in bill."}, 400

                subtotal = money(subtotal)
                discount = min(max(discount, 0), subtotal)
                total = money(subtotal - discount)
                if paid_input == "":
                    paid = total
                else:
                    paid = min(max(money(paid_input), 0), total)
                balance = money(total - paid)

                if req_status:
                    payment_status = req_status
                else:
                    if paid <= 0.001:
                        payment_status = "Unpaid"
                    elif balance <= 0.001:
                        payment_status = "Paid"
                    else:
                        payment_status = "Partially Paid"

                total_bill_paper_cost = money(total_bill_paper_cost)
                bill_profit = money(total - total_bill_paper_cost)

                now_iso = datetime.now().isoformat(timespec="seconds")
                bill_no = "IR" + datetime.now().strftime("%y%m%d%H%M%S")

                original = bill_no
                suffix = 1
                cur.execute("SELECT 1 FROM bills WHERE bill_no=%s", (bill_no,))
                while cur.fetchone():
                    bill_no = f"{original}{suffix}"
                    suffix += 1
                    cur.execute("SELECT 1 FROM bills WHERE bill_no=%s", (bill_no,))

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

                for x in items:
                    cur.execute(
                        """INSERT INTO bill_items(bill_id, service_name, print_type, paper_size, quantity, pages_per_copy, sides, rate, line_total, paper_sheets, color_units, paper_cost, profit)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (bill_id, x["service_name"], x["print_type"], x["paper_size"], x["quantity"], x["pages_per_copy"],
                         x["sides"], x["rate"], x["line_total"], x["paper_sheets"], x["color_units"], x["paper_cost"], x["profit"])
                    )

                    inv_id = x.get("inventory_id")
                    sheets_used = x.get("paper_sheets", 0)
                    if inv_id and sheets_used > 0:
                        cur.execute("SELECT available_sheets FROM inventory WHERE id=%s FOR UPDATE", (inv_id,))
                        inv_row = cur.fetchone()
                        if inv_row:
                            new_avail = max(0, inv_row['available_sheets'] - sheets_used)
                            cur.execute("UPDATE inventory SET available_sheets=%s, updated_at=%s WHERE id=%s", (new_avail, now_iso, inv_id))
                            cur.execute("""
                            INSERT INTO stock_movements (item_id, movement_type, quantity, balance_after, reference_id, notes, created_at)
                            VALUES (%s, 'SALE', %s, %s, %s, %s, %s)
                            """, (inv_id, -sheets_used, new_avail, bill_no, f"Billed: {x['service_name']} ({x['sides']})", now_iso))

            conn.commit()

        receipt_url = url_for("receipt", bill_id=bill_id)
        return {
            "success": True,
            "bill_id": bill_id,
            "bill_no": bill_no,
            "total": total,
            "paid": paid,
            "balance": balance,
            "payment_status": payment_status,
            "receipt_url": receipt_url
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

# ── Printer Configuration & Test Route (Admin) ──
@app.route("/printer-settings", methods=["GET", "POST"])
@admin_required
def printer_settings_page():
    with db() as conn:
        with conn.cursor() as cur:
            if request.method == "POST":
                action = request.form.get("action")
                now = datetime.now().isoformat(timespec="seconds")
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

            cur.execute("SELECT value FROM app_settings WHERE key='default_printer'")
            p_row = cur.fetchone()
            current_printer = p_row['value'] if p_row else '__SYSTEM_DEFAULT__'

            cur.execute("SELECT value FROM app_settings WHERE key='thermal_width'")
            w_row = cur.fetchone()
            thermal_width = w_row['value'] if w_row else '80mm'

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
        available_printers=available_printers
    )

# ── Bill History (Accessible by Staff & Admin, Confidential Costs Hidden from Staff) ──
@app.route("/history")
def history():
    q = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "all").strip()
    is_admin = bool(session.get("is_admin"))

    with db() as conn:
        with conn.cursor() as cur:
            # Summary metrics (restricted to Admin in template)
            cur.execute("""
                SELECT COALESCE(SUM(total), 0) AS total_sales,
                       COALESCE(SUM(paid), 0) AS total_collected,
                       COALESCE(SUM(balance), 0) AS total_outstanding,
                       COUNT(CASE WHEN balance > 0.001 THEN 1 END) AS unpaid_count,
                       COUNT(*) AS total_count
                FROM bills
                WHERE is_deleted = 0
            """)
            stats = cur.fetchone()

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

            query += " ORDER BY id DESC LIMIT 200"
            cur.execute(query, tuple(params))
            bills = cur.fetchall()

    return render_template(
        "history.html",
        bills=bills,
        q=q,
        status_filter=status_filter,
        stats=stats,
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
        now_iso = datetime.now().isoformat(timespec="seconds")

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
            "success": True,
            "bill_id": bill_id,
            "paid": new_paid,
            "balance": new_balance,
            "payment_status": new_status,
            "message": f"Payment of {inr(new_amount)} recorded successfully."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

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
            "payments": payments
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

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

        return {
            "success": True,
            "bill": bill,
            "items": items,
            "payments": payments,
            "is_admin": bool(session.get("is_admin"))
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

# ── API: Delete Bill (Admin only with stock return) ──
@app.post("/api/bills/<int:bill_id>/delete")
@admin_required
def delete_bill(bill_id):
    try:
        data = request.get_json(silent=True) or {}
        reason = (data.get("reason") or "Deleted by admin").strip()
        now_iso = datetime.now().isoformat(timespec="seconds")

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
        return {"success": False, "error": str(e)}, 500

# ── API: Edit Bill (Admin only with stock reconciliation) ──
@app.post("/api/bills/<int:bill_id>/edit")
@admin_required
def edit_bill(bill_id):
    try:
        data = request.get_json(force=True) or {}
        customer = (data.get("customer") or "").strip()
        payment_method = data.get("payment_method") or "Cash"
        discount = money(data.get("discount", 0))
        notes = (data.get("notes") or "").strip()
        raw_items = data.get("items") or []
        now_iso = datetime.now().isoformat(timespec="seconds")

        if not raw_items:
            return {"success": False, "error": "Bill must contain at least one item."}, 400

        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM bills WHERE id=%s AND is_deleted=0 FOR UPDATE", (bill_id,))
                bill = cur.fetchone()
                if not bill:
                    return {"success": False, "error": "Bill not found."}, 404

                cur.execute("SELECT * FROM bill_items WHERE bill_id=%s", (bill_id,))
                old_items = cur.fetchall()

                # Step A: Return old items' sheets to inventory
                for o_it in old_items:
                    sheets = o_it.get("paper_sheets", 0)
                    if sheets > 0:
                        cur.execute("SELECT id, available_sheets FROM inventory WHERE size_spec ILIKE %s LIMIT 1", (o_it["paper_size"],))
                        inv_row = cur.fetchone()
                        if inv_row:
                            new_avail = inv_row["available_sheets"] + sheets
                            cur.execute("UPDATE inventory SET available_sheets=%s, updated_at=%s WHERE id=%s", (new_avail, now_iso, inv_row["id"]))
                            cur.execute("""
                            INSERT INTO stock_movements (item_id, movement_type, quantity, balance_after, reference_id, notes, created_at)
                            VALUES (%s, 'RETURN', %s, %s, %s, 'Edit reversal', %s)
                            """, (inv_row["id"], sheets, new_avail, bill["bill_no"], now_iso))

                # Step B: Delete old bill items
                cur.execute("DELETE FROM bill_items WHERE bill_id=%s", (bill_id,))

                # Step C: Re-calculate new items, sheets, costs, totals
                cur.execute("""
                SELECT id, item_name, size_spec, available_sheets, 
                       ROUND((cost / NULLIF(total_sheets,0))::numeric, 4) AS cost_per_sheet
                FROM inventory
                """)
                inv_rows = cur.fetchall()
                inv_by_size = { (r['size_spec'] or '').strip().upper(): (r['id'], float(r['cost_per_sheet'] or 0.0)) for r in inv_rows }

                subtotal = 0.0
                total_paper_cost = 0.0

                for it in raw_items:
                    s_name = (it.get("name") or "Service").strip()
                    p_type = (it.get("type") or "bw").strip()
                    p_size = (it.get("size") or "A4").strip()
                    qty = max(1, int(it.get("qty", 1)))
                    sides = it.get("sides") or "Single"
                    rate = money(it.get("rate", 0))
                    line_total = money(qty * rate)

                    is_double = sides.lower().startswith("double")
                    sheets = ((qty + 1) // 2) if is_double else qty

                    unit_cost = 0.0
                    target_inv_id = None
                    size_key = p_size.upper()
                    if size_key in inv_by_size and sheets > 0:
                        target_inv_id, unit_cost = inv_by_size[size_key]

                    line_paper_cost = money(sheets * unit_cost) if sheets > 0 else 0.0
                    line_profit = money(line_total - line_paper_cost)
                    total_paper_cost += line_paper_cost
                    subtotal += line_total

                    cur.execute("""
                        INSERT INTO bill_items (bill_id, service_name, print_type, paper_size, quantity, pages_per_copy, sides, rate, line_total, paper_sheets, color_units, paper_cost, profit)
                        VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s, 0, %s, %s)
                    """, (bill_id, s_name, p_type, p_size, qty, sides, rate, line_total, sheets, line_paper_cost, line_profit))

                    # Deduct new sheets from inventory
                    if target_inv_id and sheets > 0:
                        cur.execute("SELECT available_sheets FROM inventory WHERE id=%s FOR UPDATE", (target_inv_id,))
                        inv_now = cur.fetchone()
                        if inv_now:
                            new_avail = max(0, inv_now["available_sheets"] - sheets)
                            cur.execute("UPDATE inventory SET available_sheets=%s, updated_at=%s WHERE id=%s", (new_avail, now_iso, target_inv_id))
                            cur.execute("""
                            INSERT INTO stock_movements (item_id, movement_type, quantity, balance_after, reference_id, notes, created_at)
                            VALUES (%s, 'SALE', %s, %s, %s, 'Edit deduction', %s)
                            """, (target_inv_id, -sheets, new_avail, bill["bill_no"], now_iso))

                subtotal = money(subtotal)
                discount = min(max(discount, 0), subtotal)
                total = money(subtotal - discount)
                total_paper_cost = money(total_paper_cost)
                profit = money(total - total_paper_cost)

                cur_paid = money(bill["paid"])
                new_balance = max(0.0, money(total - cur_paid))
                if cur_paid <= 0:
                    new_status = "Unpaid"
                elif new_balance <= 0.001:
                    new_status = "Paid"
                else:
                    new_status = "Partially Paid"

                cur.execute("""
                    UPDATE bills 
                    SET customer=%s, payment_method=%s, subtotal=%s, discount=%s, total=%s, balance=%s,
                        paper_cost=%s, profit=%s, payment_status=%s, notes=%s
                    WHERE id=%s
                """, (customer, payment_method, subtotal, discount, total, new_balance, total_paper_cost, profit, new_status, notes, bill_id))

                audit_details = f"Bill {bill['bill_no']} edited. New Total: ₹{total}, Balance: ₹{new_balance}, Status: {new_status}."
                cur.execute("""
                    INSERT INTO bill_audit_log (bill_id, bill_no, action, performed_by, details, created_at)
                    VALUES (%s, %s, 'EDIT', 'Admin', %s, %s)
                """, (bill_id, bill["bill_no"], audit_details, now_iso))

            conn.commit()

        return {"success": True, "message": f"Bill {bill['bill_no']} updated successfully."}
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

# ── API: Record Supplier Purchase Payment (Admin only) ──
@app.post("/api/purchases/<int:purchase_id>/pay")
@admin_required
def pay_supplier_purchase(purchase_id):
    try:
        data = request.get_json(force=True) or {}
        new_amount = money(data.get("amount", 0))
        payment_method = data.get("payment_method") or "Cash"
        payment_date = data.get("payment_date") or date.today().isoformat()
        notes = (data.get("notes") or "").strip()
        recorded_by = "Admin"
        now_iso = datetime.now().isoformat(timespec="seconds")

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
        return {"success": False, "error": str(e)}, 500

# ── API: Get Supplier Purchase Payments ──
@app.get("/api/purchases/<int:purchase_id>/payments")
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
        return {"success": False, "error": str(e)}, 500

# ── API: Create Supplier Purchase (Multi-Item) ──
@app.post("/api/purchases/create")
def api_create_purchase():
    try:
        data = request.get_json(force=True) if request.is_json else request.form.to_dict()
        if "items_json" in data and isinstance(data["items_json"], str):
            data["items"] = json.loads(data["items_json"])

        is_admin = bool(session.get("is_admin"))
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

# ── API: Get Full Supplier Purchase Details (Items, Payments & Audit) ──
@app.get("/api/purchases/<int:purchase_id>/details")
def api_get_purchase_details(purchase_id):
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM purchases WHERE id=%s", (purchase_id,))
                p = cur.fetchone()
                if not p:
                    return {"success": False, "error": "Purchase bill not found."}, 404

                cur.execute("SELECT * FROM purchase_items WHERE purchase_id=%s ORDER BY id ASC", (purchase_id,))
                items = cur.fetchall()

                cur.execute("SELECT * FROM purchase_payments WHERE purchase_id=%s ORDER BY id ASC", (purchase_id,))
                payments = cur.fetchall()

                cur.execute("SELECT * FROM purchase_audit_log WHERE purchase_id=%s ORDER BY id DESC", (purchase_id,))
                audit_logs = cur.fetchall()

        return {
            "success": True,
            "purchase": dict(p),
            "items": [dict(it) for it in items],
            "payments": [dict(pm) for pm in payments],
            "audit_logs": [dict(al) for al in audit_logs]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

# ── API: Edit Supplier Purchase (Admin only with stock reconciliation) ──
@app.post("/api/purchases/<int:purchase_id>/edit")
@admin_required
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
@admin_required
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
@admin_required
def api_adjust_inventory():
    try:
        data = request.get_json(force=True) if request.is_json else request.form.to_dict()
        item_id = int(data.get("item_id"))
        adj_type = data.get("adj_type")
        quantity = int(data.get("sheets_change") or data.get("quantity", 0))
        adj_date = data.get("adj_date") or date.today().isoformat()
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

# ── Admin Protected Reports & Profit Dashboard ──
@app.route("/reports")
@admin_required
def reports():
    selected_date = request.args.get("date", date.today().isoformat())
    is_admin = bool(session.get("is_admin"))

    with db() as conn:
        with conn.cursor() as cur:
            # Daily Summary (Sales, Paper Cost, Profit)
            cur.execute("""
                SELECT COUNT(*) AS bills, 
                       COALESCE(SUM(subtotal),0) AS subtotal,
                       COALESCE(SUM(discount),0) AS discount, 
                       COALESCE(SUM(total),0) AS total,
                       COALESCE(SUM(paid),0) AS paid, 
                       COALESCE(SUM(balance),0) AS balance,
                       COALESCE(SUM(paper_cost),0) AS paper_cost,
                       COALESCE(SUM(profit),0) AS profit
                FROM bills WHERE substr(created_at,1,10)=%s AND is_deleted=0
            """, (selected_date,))
            summary = cur.fetchone()

            # Physical Paper sheets & units usage
            cur.execute("""
                SELECT COALESCE(SUM(i.paper_sheets),0) AS sheets,
                       COALESCE(SUM(i.color_units),0) AS color_units,
                       COALESCE(SUM(CASE WHEN i.print_type='bw' THEN i.quantity*i.pages_per_copy ELSE 0 END),0) AS bw_units,
                       COALESCE(SUM(i.paper_cost),0) AS paper_cost
                FROM bill_items i JOIN bills b ON b.id=i.bill_id
                WHERE substr(b.created_at,1,10)=%s AND b.is_deleted=0
            """, (selected_date,))
            usage = cur.fetchone()

            # Payment Methods Breakdown
            cur.execute("""
                SELECT payment_method, COUNT(*) AS count, COALESCE(SUM(total),0) AS amount,
                       COALESCE(SUM(paid),0) AS paid
                FROM bills WHERE substr(created_at,1,10)=%s AND is_deleted=0 GROUP BY payment_method
            """, (selected_date,))
            payment_rows = cur.fetchall()

            # Maintenance expenses for selected date
            cur.execute("""
                SELECT category, title, amount 
                FROM maintenance_expenses 
                WHERE expense_date=%s
            """, (selected_date,))
            maintenance_rows = cur.fetchall()
            maintenance_total = sum(r['amount'] for r in maintenance_rows)

            # Net Profit = Billing Gross Profit - Daily Operating/Maintenance Expenses
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
                WHERE substr(b.created_at,1,10)=%s AND b.is_deleted=0
                GROUP BY i.service_name, i.print_type ORDER BY amount DESC
            """, (selected_date,))
            top_items = cur.fetchall()

    return render_template(
        "reports.html",
        selected_date=selected_date,
        summary=summary,
        usage=usage,
        payment_rows=payment_rows,
        maintenance_rows=maintenance_rows,
        maintenance_total=maintenance_total,
        net_profit=net_profit,
        top_items=top_items,
        is_admin=is_admin,
        today=date.today().isoformat()
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
                        print_type = request.form.get("print_type", "bw")
                        paper_size = request.form.get("paper_size", "A4").strip() or "A4"
                        sheets_per_unit = max(0, int(request.form.get("sheets_per_unit", 1)))
                        paper_id_val = request.form.get("paper_id", "").strip()
                        paper_id = int(paper_id_val) if paper_id_val else None

                        if not name or rate < 0:
                            raise ValueError("Invalid name or rate.")

                        cur.execute(
                            """INSERT INTO services(name, rate, double_rate, print_type, paper_size, sheets_per_unit, paper_id, active) 
                               VALUES(%s,%s,%s,%s,%s,%s,%s,1)""",
                            (name, rate, double_rate, print_type, paper_size, sheets_per_unit, paper_id)
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
                            clean_type = types[i].strip() if types[i] else "bw"
                            clean_size = sizes[i].strip() if sizes[i] else "A4"
                            p_id_str = paper_ids[i].strip() if i < len(paper_ids) else ""
                            p_id = int(p_id_str) if p_id_str else None

                            if clean_name:
                                cur.execute("""
                                    UPDATE services 
                                    SET name=%s, rate=%s, double_rate=%s, print_type=%s, paper_size=%s, paper_id=%s
                                    WHERE id=%s
                                """, (clean_name, clean_rate, clean_double_rate, clean_type, clean_size, p_id, sid))
                                updated_count += 1
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

                return redirect(url_for("services"))

            # Active items for services page
            cur.execute("""
            SELECT s.*, i.item_name AS linked_paper_name
            FROM services s
            LEFT JOIN inventory i ON s.paper_id = i.id
            ORDER BY s.active DESC, s.print_type, s.name
            """)
            services_rows = cur.fetchall()

            # All available papers for mapping dropdown
            cur.execute("SELECT id, item_name, size_spec FROM inventory ORDER BY item_name")
            papers = cur.fetchall()

    return render_template("services.html", services=services_rows, papers=papers)

@app.route("/export.csv")
@admin_required
def export_csv():
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Bill No", "Date/Time", "Customer", "Payment Method", "Status", "Subtotal", "Discount", "Total", "Paid", "Balance", "Paper Cost", "Gross Profit"])
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT bill_no,created_at,customer,payment_method,payment_status,subtotal,discount,total,paid,balance,paper_cost,profit FROM bills WHERE is_deleted=0 ORDER BY id DESC")
            rows = cur.fetchall()
            writer.writerows([tuple(r.values()) for r in rows])
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
    print("Iread Print Billing is running at http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
