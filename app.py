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

DEFAULT_SERVICES = [
    ('Photostat B&W — A4 single side', 2.00, 'bw', 'A4', 1),
    ('Photostat B&W — A4 double side', 3.00, 'bw', 'A4', 1),
    ('Photostat B&W — Legal single side', 3.00, 'bw', 'Legal', 1),
    ('Photostat B&W — Legal double side', 4.00, 'bw', 'Legal', 1),
    ('Photostat B&W — A3 single side', 5.00, 'bw', 'A3', 1),
    ('Photostat B&W — A3 double side', 7.00, 'bw', 'A3', 1),
    ('Photostat Colour — A4 single side', 8.00, 'color', 'A4', 1),
    ('Photostat Colour — A4 double side', 14.00, 'color', 'A4', 1),
    ('Photostat Colour — Legal single side', 10.00, 'color', 'Legal', 1),
    ('Photostat Colour — Legal double side', 18.00, 'color', 'Legal', 1),
    ('Photostat Colour — A3 single side', 15.00, 'color', 'A3', 1),
    ('Photostat Colour — A3 double side', 25.00, 'color', 'A3', 1),
    ('Scanning — per page', 2.00, 'service', 'Digital', 0),
    ('Sending — email/upload', 5.00, 'service', 'Digital', 0),
    ('Print B&W — A4 single side — first page', 3.00, 'bw', 'A4', 1),
    ('Print B&W — A4 single side — each extra page', 1.00, 'bw', 'A4', 1),
    ('Print B&W — A4 double side — first sheet / up to 2 pages', 4.00, 'bw', 'A4', 1),
    ('Print B&W — A4 double side — each extra sheet', 2.00, 'bw', 'A4', 1),
    ('Print B&W — Legal single side', 4.00, 'bw', 'Legal', 1),
    ('Print B&W — Legal double side', 5.00, 'bw', 'Legal', 1),
    ('Print B&W — A3 single side', 6.00, 'bw', 'A3', 1),
    ('Print B&W — A3 double side', 9.00, 'bw', 'A3', 1),
    ('Print Colour — A4 single side', 10.00, 'color', 'A4', 1),
    ('Print Colour — A4 double side', 18.00, 'color', 'A4', 1),
    ('Print Colour — A3 single side', 18.00, 'color', 'A3', 1),
    ('Print Colour — A3 double side', 25.00, 'color', 'A3', 1),
    ('Photo Paper — A4 130 gsm', 15.00, 'photo', 'A4', 1),
    ('Photo Paper — A4 220 gsm', 20.00, 'photo', 'A4', 1),
    ('Photo Paper — A3 220 gsm', 25.00, 'photo', 'A3', 1),
    ('Laser 12x18 — 220 gsm', 20.00, 'photo', '12x18', 1),
    ('Laser 12x18 — 130 gsm', 15.00, 'photo', '12x18', 1),
    ('Laser 12x18 — waterproof', 25.00, 'photo', '12x18', 1),
    ('Laser 12x18 — sticker sheet', 20.00, 'photo', '12x18', 1),
    ('Laser 12x18 — waterproof sticker', 25.00, 'photo', '12x18', 1),
    ('Lamination — ID card', 5.00, 'service', 'ID card', 0),
    ('Lamination — RC book', 5.00, 'service', 'RC book', 0),
    ('Lamination — A4', 10.00, 'service', 'A4', 0),
    ('Lamination — Legal', 15.00, 'service', 'Legal', 0),
    ('Lamination — A3', 25.00, 'service', 'A3', 0),
    ('Frame setting — Mini', 5.00, 'service', 'Mini', 0),
    ('Frame setting — 4x4', 8.00, 'service', '4x4', 0),
    ('Frame setting — A5', 10.00, 'service', 'A5', 0),
    ('Frame setting — A4', 15.00, 'service', 'A4', 0),
    ('Frame setting — A3', 25.00, 'service', 'A3', 0),
    ('Polaroids — 12x18 printing', 25.00, 'photo', '12x18', 1),
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
                CREATE TABLE IF NOT EXISTS services (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    rate REAL NOT NULL DEFAULT 0,
                    print_type TEXT NOT NULL DEFAULT 'bw',
                    paper_size TEXT NOT NULL DEFAULT 'A4',
                    sheets_per_unit INTEGER NOT NULL DEFAULT 1,
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
                    color_units INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS inventory (
                    id SERIAL PRIMARY KEY,
                    category TEXT NOT NULL DEFAULT 'Paper',
                    item_name TEXT NOT NULL,
                    size_spec TEXT DEFAULT '',
                    bundles INTEGER NOT NULL DEFAULT 1,
                    sheets_per_bundle INTEGER NOT NULL DEFAULT 500,
                    total_sheets INTEGER NOT NULL DEFAULT 500,
                    cost REAL NOT NULL DEFAULT 0,
                    notes TEXT DEFAULT '',
                    updated_at TEXT NOT NULL
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
                cur.execute("SELECT name FROM services")
                existing = {row['name'] for row in cur.fetchall()}
                for service in DEFAULT_SERVICES:
                    if service[0] not in existing:
                        cur.execute(
                            "INSERT INTO services(name,rate,print_type,paper_size,sheets_per_unit,active) VALUES(%s,%s,%s,%s,%s,1)",
                            service
                        )
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
            next_url = request.args.get("next") or url_for("services")
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

# ── Paper & Lamination Stock Inventory (Staff accessible) ──
@app.route("/inventory", methods=["GET", "POST"])
def inventory_page():
    if not DATABASE_URL:
        return "DATABASE_URL missing", 500
    with db() as conn:
        with conn.cursor() as cur:
            # Ensure table exists in case init_db hasn't run yet
            cur.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id SERIAL PRIMARY KEY,
                category TEXT NOT NULL DEFAULT 'Paper',
                item_name TEXT NOT NULL,
                size_spec TEXT DEFAULT '',
                bundles INTEGER NOT NULL DEFAULT 1,
                sheets_per_bundle INTEGER NOT NULL DEFAULT 500,
                total_sheets INTEGER NOT NULL DEFAULT 500,
                cost REAL NOT NULL DEFAULT 0,
                notes TEXT DEFAULT '',
                updated_at TEXT NOT NULL
            );
            """)
            if request.method == "POST":
                action = request.form.get("action")
                if action == "add":
                    category = request.form.get("category", "Paper").strip()
                    item_name = request.form.get("item_name", "").strip()
                    size_spec = request.form.get("size_spec", "").strip()
                    try:
                        bundles = max(1, int(request.form.get("bundles", 1)))
                        sheets_per_bundle = max(1, int(request.form.get("sheets_per_bundle", 500)))
                        total_sheets = bundles * sheets_per_bundle
                        cost = max(0.0, money(request.form.get("cost", 0)))
                        notes = request.form.get("notes", "").strip()
                        updated_at = datetime.now().isoformat(timespec="seconds")

                        if not item_name:
                            raise ValueError("Item name cannot be empty")

                        cur.execute("""
                        INSERT INTO inventory (category, item_name, size_spec, bundles, sheets_per_bundle, total_sheets, cost, notes, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (category, item_name, size_spec, bundles, sheets_per_bundle, total_sheets, cost, notes, updated_at))
                        conn.commit()
                        flash(f"Added {bundles} bundle(s) ({total_sheets} sheets) of '{item_name}'.", "success")
                    except Exception as e:
                        conn.rollback()
                        flash(f"Error adding stock entry: {e}", "error")

                elif action == "delete":
                    try:
                        item_id = int(request.form.get("item_id"))
                        cur.execute("DELETE FROM inventory WHERE id=%s", (item_id,))
                        conn.commit()
                        flash("Inventory entry removed.", "success")
                    except Exception as e:
                        conn.rollback()
                        flash(f"Error removing entry: {e}", "error")

                return redirect(url_for("inventory_page"))

            cur.execute("SELECT * FROM inventory ORDER BY id DESC")
            items = cur.fetchall()

            total_items = len(items)
            total_sheets = sum(row.get("total_sheets", 0) for row in items)
            total_cost = sum(row.get("cost", 0.0) for row in items)

    return render_template("inventory.html", inventory=items, total_items=total_items, total_sheets=total_sheets, total_cost=total_cost)

# ── Maintenance & Expenses (Drum, Ink, Repair, Other) ──
@app.route("/maintenance", methods=["GET", "POST"])
def maintenance_page():
    if not DATABASE_URL:
        return "DATABASE_URL missing", 500
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
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

# ── Billing Route (Public / Fast POS) ──
@app.route("/")
def index():
    if not DATABASE_URL:
        return "DATABASE_URL environment variable is missing. Please set it in Vercel Project Settings -> Environment Variables.", 500
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM services WHERE active=1 ORDER BY name")
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
    for i, service_id in enumerate(names):
        if not service_id:
            continue
        try:
            qty            = int(quantities[i])
            pages_per_copy = max(1, int(pages[i] or 1))
            rate           = money(rates[i])
            service_id_int = int(service_id)
        except (ValueError, IndexError):
            continue
        if qty <= 0:
            continue
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM services WHERE id=%s AND active=1", (service_id_int,))
                service = cur.fetchone()
        if not service:
            continue
        sides      = sides_list[i] if i < len(sides_list) else "Single"
        line_total = money(qty * pages_per_copy * rate)
        color_units = qty * pages_per_copy if service["print_type"] in ("color", "photo") else 0
        if service["sheets_per_unit"] == 0:
            sheets = 0
        elif sides.lower().startswith("double"):
            sheets = qty * ((pages_per_copy + 1) // 2)
        else:
            sheets = qty * pages_per_copy
        items.append({
            "service_name": service["name"], "print_type": service["print_type"],
            "paper_size": service["paper_size"], "quantity": qty,
            "pages_per_copy": pages_per_copy, "sides": sides, "rate": rate,
            "line_total": line_total, "paper_sheets": sheets, "color_units": color_units
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
    created_at = datetime.now().isoformat(timespec="seconds")
    bill_no    = "IR" + datetime.now().strftime("%y%m%d%H%M%S")

    with db() as conn:
        with conn.cursor() as cur:
            original = bill_no
            suffix   = 1
            cur.execute("SELECT 1 FROM bills WHERE bill_no=%s", (bill_no,))
            while cur.fetchone():
                bill_no = f"{original}{suffix}"
                suffix += 1
                cur.execute("SELECT 1 FROM bills WHERE bill_no=%s", (bill_no,))

            cur.execute(
                """INSERT INTO bills(bill_no,created_at,customer,payment_method,subtotal,discount,total,paid,balance,notes)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (bill_no, created_at, customer, payment, subtotal, discount, total, paid, balance, notes)
            )
            bill_id = cur.fetchone()["id"]

            psycopg2.extras.execute_batch(cur,
                """INSERT INTO bill_items(bill_id,service_name,print_type,paper_size,quantity,pages_per_copy,sides,rate,line_total,paper_sheets,color_units)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [(bill_id, x["service_name"], x["print_type"], x["paper_size"], x["quantity"], x["pages_per_copy"],
                  x["sides"], x["rate"], x["line_total"], x["paper_sheets"], x["color_units"]) for x in items]
            )
        conn.commit()
    return redirect(url_for("receipt", bill_id=bill_id))

@app.route("/receipt/<int:bill_id>")
def receipt(bill_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bills WHERE id=%s", (bill_id,))
            bill = cur.fetchone()
            cur.execute("SELECT * FROM bill_items WHERE bill_id=%s", (bill_id,))
            items = cur.fetchall()
    if not bill:
        return "Bill not found", 404
    return render_template("receipt.html", bill=bill, items=items)

# ── Admin Protected Routes ──
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
    return render_template("history.html", bills=bills, q=q)

@app.route("/reports")
@admin_required
def reports():
    selected_date = request.args.get("date", date.today().isoformat())
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS bills, COALESCE(SUM(subtotal),0) AS subtotal,
                       COALESCE(SUM(discount),0) AS discount, COALESCE(SUM(total),0) AS total,
                       COALESCE(SUM(paid),0) AS paid, COALESCE(SUM(balance),0) AS balance
                FROM bills WHERE substr(created_at,1,10)=%s
            """, (selected_date,))
            summary = cur.fetchone()

            cur.execute("""
                SELECT COALESCE(SUM(i.paper_sheets),0) AS sheets,
                       COALESCE(SUM(i.color_units),0) AS color_units,
                       COALESCE(SUM(CASE WHEN i.print_type='bw' THEN i.quantity*i.pages_per_copy ELSE 0 END),0) AS bw_units
                FROM bill_items i JOIN bills b ON b.id=i.bill_id
                WHERE substr(b.created_at,1,10)=%s
            """, (selected_date,))
            usage = cur.fetchone()

            cur.execute("""
                SELECT payment_method, COUNT(*) AS count, COALESCE(SUM(total),0) AS amount,
                       COALESCE(SUM(paid),0) AS paid
                FROM bills WHERE substr(created_at,1,10)=%s GROUP BY payment_method
            """, (selected_date,))
            payment_rows = cur.fetchall()

            cur.execute("""
                SELECT service_name, SUM(quantity*pages_per_copy) AS units, SUM(line_total) AS amount
                FROM bill_items i JOIN bills b ON b.id=i.bill_id
                WHERE substr(b.created_at,1,10)=%s
                GROUP BY service_name ORDER BY amount DESC
            """, (selected_date,))
            top_items = cur.fetchall()

    return render_template("reports.html", selected_date=selected_date, summary=summary,
                           usage=usage, payment_rows=payment_rows, top_items=top_items)

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
                        rate           = money(request.form.get("rate", 0))
                        print_type     = request.form.get("print_type", "bw")
                        paper_size     = request.form.get("paper_size", "A4").strip() or "A4"
                        sheets_per_unit = max(0, int(request.form.get("sheets_per_unit", 1)))
                        if not name or rate < 0:
                            raise ValueError()
                        cur.execute(
                            "INSERT INTO services(name,rate,print_type,paper_size,sheets_per_unit,active) VALUES(%s,%s,%s,%s,%s,1)",
                            (name, rate, print_type, paper_size, sheets_per_unit)
                        )
                        conn.commit()
                        flash("Service added.", "success")
                    except psycopg2.errors.UniqueViolation:
                        conn.rollback()
                        flash("A service with that name already exists.", "error")
                    except ValueError:
                        flash("Check the service name, rate and sheet count.", "error")

                elif action == "update":
                    ids   = request.form.getlist("service_id[]")
                    names = request.form.getlist("service_name[]")
                    rates = request.form.getlist("service_rate[]")
                    types = request.form.getlist("service_type[]")
                    sizes = request.form.getlist("service_size[]")
                    updated_count = 0
                    for sid, name, rate, ptype, psize in zip(ids, names, rates, types, sizes):
                        try:
                            clean_name = name.strip()
                            clean_rate = max(0, money(rate))
                            clean_type = ptype.strip() if ptype else "bw"
                            clean_size = psize.strip() if psize else "A4"
                            if clean_name:
                                cur.execute(
                                    "UPDATE services SET name=%s, rate=%s, print_type=%s, paper_size=%s WHERE id=%s",
                                    (clean_name, clean_rate, clean_type, clean_size, int(sid))
                                )
                                updated_count += 1
                        except Exception as e:
                            print(f"Error updating service {sid}: {e}")
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

            cur.execute("SELECT * FROM services ORDER BY active DESC, name")
            rows = cur.fetchall()
    return render_template("services.html", services=rows)

@app.route("/export.csv")
@admin_required
def export_csv():
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Bill No", "Date/Time", "Customer", "Payment", "Subtotal", "Discount", "Total", "Paid", "Balance"])
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT bill_no,created_at,customer,payment_method,subtotal,discount,total,paid,balance FROM bills ORDER BY id DESC")
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
