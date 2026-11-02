import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")

print("Connecting to PostgreSQL...")
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

print("Creating tables...")
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

print("Seeding default services...")
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

for svc in DEFAULT_SERVICES:
    cur.execute("""
        INSERT INTO services (name, rate, print_type, paper_size, sheets_per_unit)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (name) DO NOTHING
    """, svc)

cur.execute("SELECT COUNT(*) FROM services")
count = cur.fetchone()[0]
print(f"Services in DB: {count}")

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = [t[0] for t in cur.fetchall()]
print(f"Tables created: {tables}")

cur.close()
conn.close()
print("\n✅ PostgreSQL database ready!")
