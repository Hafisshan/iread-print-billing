from flask import Flask, render_template, request, redirect, url_for, flash, make_response, session
import psycopg2
import psycopg2.extras
from pathlib import Path
from datetime import datetime, date, timedelta
import os
import json
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
    now = datetime.now().isoformat(timespec="seconds")
    return_date = return_date or date.today().isoformat()
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
    now = datetime.now().isoformat(timespec="seconds")
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
    now = datetime.now().isoformat(timespec="seconds")
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
    now_iso = datetime.now().isoformat(timespec="seconds")
    today_iso = date.today().isoformat()

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
    now_iso = datetime.now().isoformat(timespec="seconds")
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

            # Active items for metrics and datalist
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

                    # Physical sheets: 1 copy = 1 physical sheet for both single-side and double-side jobs
                    if sheets_per_unit == 0:
                        sheets = 0
                    else:
                        sheets = qty

                    line_total = money(qty * rate)
                    color_units = qty if p_type in ("color", "photo") else 0

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
        return {"success": False, "error": str(e)}, 400

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

def get_period_date_range(period, custom_start=None, custom_end=None):
    today = date.today()
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

            if start_d and end_d:
                query += " AND SUBSTRING(created_at, 1, 10) >= %s AND SUBSTRING(created_at, 1, 10) <= %s"
                params.extend([start_d, end_d])
            elif start_d:
                query += " AND SUBSTRING(created_at, 1, 10) >= %s"
                params.append(start_d)
            elif end_d:
                query += " AND SUBSTRING(created_at, 1, 10) <= %s"
                params.append(end_d)

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

        return {
            "success": True,
            "bill": bill,
            "items": items,
            "payments": payments,
            "is_admin": bool(session.get("is_admin"))
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400

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
    new_created_at = (data.get("created_at") or bill["created_at"]).strip()

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

    cur.execute("SELECT id, name, rate, double_rate, print_type, paper_size, sheets_per_unit, paper_id FROM services")
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
        if rate <= 0.001 and s_obj:
            is_double = sides.lower().startswith("double")
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
@admin_required
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

        return {
            "success": True,
            "bill": dict(bill),
            "items": [dict(it) for it in items],
            "payments": [dict(p) for p in payments],
            "services": [dict(s) for s in services],
            "inventory": [dict(i) for i in inventory],
            "audit_logs": [dict(a) for a in audit_logs]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}, 400


# ── API: Preview Bill Corrections & Confirmation Summary (Admin only) ──
@app.post("/api/bills/<int:bill_id>/edit-preview")
@admin_required
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

        orig_dt = bill["created_at"][:19].replace("T", " ")
        new_dt = calc["new_created_at"][:19].replace("T", " ")

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
@admin_required
def edit_bill(bill_id):
    try:
        data = request.get_json(force=True) or {}
        now_iso = datetime.now().isoformat(timespec="seconds")
        today_iso = date.today().isoformat()
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
                    audit_details += f" Date: {bill['created_at'][:19]} -> {calc['new_created_at'][:19]}."

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


# ── API: View Edit & Audit History for a Bill ──
@app.get("/api/bills/<int:bill_id>/audit")
@admin_required
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
        return {"success": False, "error": str(e)}, 400

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
        return {"success": False, "error": str(e)}, 400

# ── API: Create Supplier Purchase (Multi-Item) ──
@app.post("/api/purchases")
@app.post("/api/purchases/create")
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
@admin_required
def api_return_purchase_item(purchase_id):
    try:
        data = request.get_json(force=True) if request.is_json else request.form.to_dict()
        purchase_item_id = int(data.get("purchase_item_id") or 0)
        return_qty = int(data.get("return_quantity") or data.get("quantity") or 0)
        return_date = data.get("return_date") or date.today().isoformat()
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

# ── API: Audit Double-Sided Photocopy/Print Paper Consumption ──
@app.get("/api/inventory/audit-double-sided")
@admin_required
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
@admin_required
def api_reconcile_double_sided():
    try:
        user_name = "Admin"
        now = datetime.now().isoformat(timespec="seconds")
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

# ── API: Inspect Inventory Item for Removal (Admin only) ──
@app.get("/api/inventory/<int:item_id>/removal-info")
@admin_required
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
@admin_required
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
@admin_required
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
            if start_d and end_d:
                query += " AND SUBSTRING(created_at, 1, 10) >= %s AND SUBSTRING(created_at, 1, 10) <= %s"
                params.extend([start_d, end_d])
            elif start_d:
                query += " AND SUBSTRING(created_at, 1, 10) >= %s"
                params.append(start_d)
            elif end_d:
                query += " AND SUBSTRING(created_at, 1, 10) <= %s"
                params.append(end_d)
            query += " ORDER BY id DESC"
            cur.execute(query, tuple(params))
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
