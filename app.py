from flask import Flask, render_template, request, redirect, url_for, flash, make_response
import psycopg2
import psycopg2.extras
from pathlib import Path
from datetime import datetime, date
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

APP_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-local-secret-key")

# For Vercel WSGI
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
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn

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

@app.route("/")
def index():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM services WHERE active=1 ORDER BY name")
            services = cur.fetchall()
            today = date.today().isoformat()
            cur.execute("SELECT COALESCE(SUM(total),0) FROM bills WHERE substr(created_at,1,10)=%s", (today,))
            today_total = cur.fetchone()['coalesce']
            cur.execute("SELECT COUNT(*) FROM bills WHERE substr(created_at,1,10)=%s", (today,))
            today_count = cur.fetchone()['count']
    return render_template("index.html", services=services, today_total=today_total, today_count=today_count)

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
            # Avoid bill_no collision
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

@app.route("/history")
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
                FROM bills WHERE substr(b.created_at,1,10)=%s GROUP BY payment_method
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
                        paper_size     = request.form.get("paper_size", "A4")
                        sheets_per_unit = max(1, int(request.form.get("sheets_per_unit", 1)))
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
                    for sid, rate in zip(request.form.getlist("service_id[]"), request.form.getlist("service_rate[]")):
                        try:
                            cur.execute("UPDATE services SET rate=%s WHERE id=%s", (max(0, money(rate)), int(sid)))
                        except ValueError:
                            pass
                    conn.commit()
                    flash("Rates updated.", "success")

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
def backup():
    return "<h2>PostgreSQL Database</h2><p>Data is stored on Aiven cloud PostgreSQL. Use the <a href='/export.csv'>Export CSV</a> option to download a backup.</p><p><a href='/'>Back to billing</a></p>"

if __name__ == "__main__":
    init_db()
    print("Iread Print Billing is running at http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
