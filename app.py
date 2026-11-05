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
                """)
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

# ── Paper & Lamination Stock Inventory ──
@app.route("/inventory", methods=["GET", "POST"])
def inventory_page():
    if not DATABASE_URL:
        return "DATABASE_URL missing", 500
    is_admin = bool(session.get("is_admin"))
    with db() as conn:
        with conn.cursor() as cur:
            if request.method == "POST":
                action = request.form.get("action")
                now = datetime.now().isoformat(timespec="seconds")

                # Action: Add New Stock / Purchase
                if action == "add":
                    category = request.form.get("category", "Paper").strip()
                    item_name = request.form.get("item_name", "").strip()
                    size_spec = request.form.get("size_spec", "").strip()
                    try:
                        bundles = max(1, int(request.form.get("bundles", 1)))
                        sheets_per_bundle = max(1, int(request.form.get("sheets_per_bundle", 500)))
                        added_sheets = bundles * sheets_per_bundle
                        cost = max(0.0, money(request.form.get("cost", 0))) if is_admin else 0.0
                        reorder_level = max(10, int(request.form.get("reorder_level", 100)))
                        notes = request.form.get("notes", "").strip()

                        if not item_name:
                            raise ValueError("Item name cannot be empty")

                        # Check if paper with this name already exists
                        cur.execute("SELECT id, total_sheets, available_sheets, cost FROM inventory WHERE item_name ILIKE %s", (item_name,))
                        existing = cur.fetchone()
                        if existing:
                            new_total = existing['total_sheets'] + added_sheets
                            new_avail = existing['available_sheets'] + added_sheets
                            new_cost = existing['cost'] + cost
                            cur.execute("""
                            UPDATE inventory 
                            SET total_sheets=%s, available_sheets=%s, cost=%s, bundles=bundles+%s, updated_at=%s, notes=%s
                            WHERE id=%s
                            """, (new_total, new_avail, new_cost, bundles, now, notes or existing.get('notes',''), existing['id']))
                            item_id = existing['id']
                            bal = new_avail
                        else:
                            cur.execute("""
                            INSERT INTO inventory (category, item_name, size_spec, bundles, sheets_per_bundle, total_sheets, available_sheets, reorder_level, cost, notes, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING id
                            """, (category, item_name, size_spec, bundles, sheets_per_bundle, added_sheets, added_sheets, reorder_level, cost, notes, now))
                            item_id = cur.fetchone()['id']
                            bal = added_sheets

                        # Log to stock ledger
                        cur.execute("""
                        INSERT INTO stock_movements (item_id, movement_type, quantity, balance_after, reference_id, notes, created_at)
                        VALUES (%s, 'PURCHASE', %s, %s, %s, %s, %s)
                        """, (item_id, added_sheets, bal, notes or 'Stock Purchase', f"{bundles} ream(s)", now))

                        conn.commit()
                        flash(f"Recorded stock addition: +{added_sheets} sheets of '{item_name}'.", "success")
                    except Exception as e:
                        conn.rollback()
                        flash(f"Error adding stock entry: {e}", "error")

                # Action: Manual Stock Adjustment (Admin only)
                elif action == "adjust":
                    if not is_admin:
                        flash("Admin login required to adjust stock.", "error")
                        return redirect(url_for("login", next=request.path))
                    try:
                        item_id = int(request.form.get("item_id"))
                        adj_type = request.form.get("adj_type", "DAMAGE")
                        sheets_change = int(request.form.get("sheets_change", 0))
                        reason = request.form.get("reason", "").strip()

                        if sheets_change == 0:
                            raise ValueError("Sheets change cannot be zero.")

                        cur.execute("SELECT item_name, available_sheets FROM inventory WHERE id=%s", (item_id,))
                        inv = cur.fetchone()
                        if not inv:
                            raise ValueError("Item not found.")

                        new_bal = inv['available_sheets'] + sheets_change
                        if new_bal < 0:
                            raise ValueError(f"Insufficient stock. Available is only {inv['available_sheets']} sheets.")

                        cur.execute("UPDATE inventory SET available_sheets=%s, updated_at=%s WHERE id=%s", (new_bal, now, item_id))
                        cur.execute("""
                        INSERT INTO stock_movements (item_id, movement_type, quantity, balance_after, reference_id, notes, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (item_id, adj_type, sheets_change, new_bal, reason, f"Manual {adj_type}", now))

                        conn.commit()
                        flash(f"Stock adjusted for '{inv['item_name']}': {sheets_change:+d} sheets (New balance: {new_bal}).", "success")
                    except Exception as e:
                        conn.rollback()
                        flash(f"Error adjusting stock: {e}", "error")

                # Action: Delete (Admin only)
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

                # Action: Update (Admin only)
                elif action == "update":
                    if not is_admin:
                        flash("Admin login required to edit stock items.", "error")
                        return redirect(url_for("login", next=request.path))
                    try:
                        item_id = int(request.form.get("item_id"))
                        category = request.form.get("category", "Paper").strip()
                        item_name = request.form.get("item_name", "").strip()
                        size_spec = request.form.get("size_spec", "").strip()
                        available_sheets = max(0, int(request.form.get("available_sheets", 0)))
                        cost = max(0.0, money(request.form.get("cost", 0)))
                        reorder_level = max(10, int(request.form.get("reorder_level", 100)))
                        notes = request.form.get("notes", "").strip()

                        if not item_name:
                            raise ValueError("Item name cannot be empty")

                        cur.execute("""
                        UPDATE inventory 
                        SET category=%s, item_name=%s, size_spec=%s, available_sheets=%s, cost=%s, reorder_level=%s, notes=%s, updated_at=%s
                        WHERE id=%s
                        """, (category, item_name, size_spec, available_sheets, cost, reorder_level, notes, now, item_id))
                        conn.commit()
                        flash(f"Updated inventory item '{item_name}'.", "success")
                    except Exception as e:
                        conn.rollback()
                        flash(f"Error updating stock entry: {e}", "error")

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

            # Fetch recent stock movements for ledger
            cur.execute("""
            SELECT sm.created_at, sm.movement_type, sm.quantity, sm.balance_after, sm.reference_id, sm.notes, i.item_name
            FROM stock_movements sm
            JOIN inventory i ON sm.item_id = i.id
            ORDER BY sm.id DESC
            LIMIT 50
            """)
            movements = cur.fetchall()

    return render_template(
        "inventory.html",
        inventory=items,
        movements=movements,
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
                cur.execute("SELECT COALESCE(SUM(total),0) AS today_total FROM bills WHERE substr(created_at,1,10)=%s", (today,))
                row = cur.fetchone()
                today_total = row['today_total'] if row else 0
                cur.execute("SELECT COUNT(*) AS today_count FROM bills WHERE substr(created_at,1,10)=%s", (today,))
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

            # Insert Bill record with paper_cost and profit
            cur.execute(
                """INSERT INTO bills(bill_no, created_at, customer, payment_method, subtotal, discount, total, paid, balance, paper_cost, profit, notes)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (bill_no, now_iso, customer, payment, subtotal, discount, total, paid, balance, total_bill_paper_cost, bill_profit, notes)
            )
            bill_id = cur.fetchone()["id"]

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
                        pages_per_copy = max(1, int(it.get("pages", 1)))
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

                    # Physical sheets
                    if sheets_per_unit == 0:
                        sheets = 0
                    elif is_double:
                        sheets = qty * ((pages_per_copy + 1) // 2)
                    else:
                        sheets = qty * pages_per_copy

                    line_total = money(qty * pages_per_copy * rate)
                    color_units = qty * pages_per_copy if p_type in ("color", "photo") else 0

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
                    return {"success": False, "error": "No valid items in bill."}, 400

                subtotal = money(subtotal)
                discount = min(max(discount, 0), subtotal)
                total = money(subtotal - discount)
                paid = total if paid_input == "" else min(max(money(paid_input), 0), total)
                balance = money(total - paid)
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
                    """INSERT INTO bills(bill_no, created_at, customer, payment_method, subtotal, discount, total, paid, balance, paper_cost, profit, notes)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (bill_no, now_iso, customer, payment, subtotal, discount, total, paid, balance, total_bill_paper_cost, bill_profit, notes)
                )
                bill_id = cur.fetchone()["id"]

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

# ── Admin Protected Reports & Profit Dashboard ──
@app.route("/history")
@admin_required
def history():
    q = request.args.get("q", "").strip()
    with db() as conn:
        with conn.cursor() as cur:
            if q:
                cur.execute(
                    "SELECT * FROM bills WHERE bill_no ILIKE %s OR customer ILIKE %s ORDER BY id DESC LIMIT 200",
                    (f"%{q}%", f"%{q}%")
                )
            else:
                cur.execute("SELECT * FROM bills ORDER BY id DESC LIMIT 200")
            bills = cur.fetchall()
    return render_template("history.html", bills=bills, q=q, is_admin=bool(session.get("is_admin")))

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
                FROM bills WHERE substr(created_at,1,10)=%s
            """, (selected_date,))
            summary = cur.fetchone()

            # Physical Paper sheets & units usage
            cur.execute("""
                SELECT COALESCE(SUM(i.paper_sheets),0) AS sheets,
                       COALESCE(SUM(i.color_units),0) AS color_units,
                       COALESCE(SUM(CASE WHEN i.print_type='bw' THEN i.quantity*i.pages_per_copy ELSE 0 END),0) AS bw_units,
                       COALESCE(SUM(i.paper_cost),0) AS paper_cost
                FROM bill_items i JOIN bills b ON b.id=i.bill_id
                WHERE substr(b.created_at,1,10)=%s
            """, (selected_date,))
            usage = cur.fetchone()

            # Payment Methods Breakdown
            cur.execute("""
                SELECT payment_method, COUNT(*) AS count, COALESCE(SUM(total),0) AS amount,
                       COALESCE(SUM(paid),0) AS paid
                FROM bills WHERE substr(created_at,1,10)=%s GROUP BY payment_method
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
                WHERE substr(b.created_at,1,10)=%s
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
    writer.writerow(["Bill No", "Date/Time", "Customer", "Payment", "Subtotal", "Discount", "Total", "Paid", "Balance", "Paper Cost", "Gross Profit"])
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT bill_no,created_at,customer,payment_method,subtotal,discount,total,paid,balance,paper_cost,profit FROM bills ORDER BY id DESC")
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
