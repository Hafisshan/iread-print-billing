# Iread Billing App — Android Mobile Application & PC Wi-Fi Thermal Print Integration

## 1. Executive Summary
This project successfully extends the existing **Iread Billing App** with two enterprise-grade components:
1. **Native Staff Android Mobile App (`mobile_app/`)**: Developed using React Native, Expo, and TypeScript. Staff can log in, select services with Single/Double side pricing and Print B&W A4 tiered rules, manage cart items, apply discounts, choose Petpooja-style Paid/Unpaid statuses, and trigger instant wireless thermal prints with real-time feedback.
2. **PC-Based Wi-Fi Thermal Printer Integration (`pc_print_service/`)**: A cross-platform daemon running on the Counter PC attached to the USB thermal printer (80mm/58mm). It receives jobs queued by mobile phones over the shop Wi-Fi / LAN and spools receipts directly without needing USB OTG cables or Bluetooth pairing on phones.
3. **Strict Role Separation & Backend Security**: Staff users cannot access financial profit metrics, cannot alter stock movements, cannot access supplier purchase costs, and cannot edit/delete historical bills.

---

## 2. Architecture & Data Flow

```
+-------------------------------------------------------------+
|             STAFF ANDROID MOBILE APP (Expo TS)             |
|  - Fast Touch Catalog         - Copies & Single/Double Side |
|  - Print B&W A4 Tiered Calc   - Petpooja Paid/Unpaid Status |
|  - Real-time Print Polling    - Read-Only Stock & Sales     |
+-------------------------------------------------------------+
                              │
                    Wi-Fi / LAN (JSON REST API)
                              │
                              ▼
+-------------------------------------------------------------+
|              IREAD BACKEND SERVER (app.py)                  |
|  - Token Auth (HMAC-SHA256)   - Role Separation Decorators  |
|  - Paper Stock Deduction      - Print Job Queue Management  |
|  - PostgreSQL Database        - Audit & Ledger Tracking     |
+-------------------------------------------------------------+
                              │
                    Polling & Heartbeat (every 2s)
                              │
                              ▼
+-------------------------------------------------------------+
|             COUNTER PC PRINT SERVICE (Python)               |
|  - Background Daemon          - macOS CUPS / Windows Spooler|
|  - Heartbeat & Auto-Reconnect - Idempotent Job Spooling     |
+-------------------------------------------------------------+
                              │
                    Direct Local USB Cable
                              │
                              ▼
+-------------------------------------------------------------+
|          PHYSICAL THERMAL PRINTER (80mm / 58mm)             |
|  - Automatic ESC/POS Paper Cut & High-Speed Receipt Print   |
+-------------------------------------------------------------+
```

---

## 3. Credentials & Access Matrix

| Role | Username | Password | Permitted Actions | Restricted / Prohibited Actions |
|---|---|---|---|---|
| **Staff** | `staff` | `iread@staff123` | • Mobile billing<br>• Save Only & Save and Print<br>• Real-time print retry<br>• Daily sales total & bill count<br>• Read-only paper sheet counts | ❌ Cannot view profit margins<br>❌ Cannot view paper purchase cost<br>❌ Cannot edit/delete bills<br>❌ Cannot adjust stock inventory<br>❌ Cannot configure printers |
| **Admin** | `admin` | `iread@123` | • Full administrative access<br>• Bill editing & audit logs<br>• Inventory & purchase management<br>• Printer device configuration<br>• Test prints & token regeneration | None |

---

## 4. Key Deliverables & Directory Layout

### A. Android Mobile App (`mobile_app/`)
- `mobile_app/App.tsx`: Tab navigation (Billing, Sales, Stock, Settings) & auth gate.
- `mobile_app/src/screens/BillingScreen.tsx`: Complete POS billing UI with item categories, single/double sides, quantity steppers, tiered calculations, discount input, Petpooja Paid/Unpaid toggle, Save Only and Save & Print.
- `mobile_app/src/screens/SalesScreen.tsx`: Daily sales total and recent 20 bills (cost & profit stripped).
- `mobile_app/src/screens/StockScreen.tsx`: Read-only stock inventory with low-stock warnings (purchase price stripped).
- `mobile_app/src/screens/SettingsScreen.tsx`: Server IP configurator, connection test, PC printer status badge.
- `mobile_app/src/components/PrintStatusModal.tsx`: Real-time print progress modal (Pending -> Printing -> Printed / Failed with retry).

### B. Counter PC Print Service (`pc_print_service/`)
- `pc_print_service/pc_print_service.py`: Cross-platform worker daemon supporting macOS CUPS (`lp`), Linux, and Windows RAW spooler (`win32print`), with fallback simulation and disk saving.
- `pc_print_service/config.json`: Runtime configuration (server URL, token, printer name, width).
- `pc_print_service/run_service.sh` & `run_service.bat`: One-click service launchers.
- `pc_print_service/install_service.sh`: Daemon installer for macOS `launchd` and Linux `systemd`.

### C. Backend & Database Schema (`app.py`)
- Tables added in database:
  - `users`: Stores user credentials with PBKDF2:SHA256 password hashing and role (`admin`/`staff`).
  - `print_jobs`: Manages thermal print queue state, attempts, receipt text, and error logs.
  - `app_settings`: Manages active printer name, paper width, API key, and PC service heartbeat.
- Direct download endpoint: `GET /download/apk` serves `static/iread-billing-staff.apk`.
- Updated `templates/printer_settings.html`: Displays live PC Print Service status badge (Online/Offline), API token, test print button, and recent print queue table.
- Updated `templates/install.html`: Features Android APK download card and staff connection guide.

---

## 5. Verification & Testing Summary

1. **Authentication & Token Tests**:
   - `POST /api/auth/login` verified for both `staff` and `admin`.
   - `GET /api/auth/me` verifies bearer token validity.
2. **Access Control & RBAC**:
   - Staff token attempting admin routes (e.g. `/api/printer/test-print`) returns `403 Forbidden`.
   - Staff sales API returns only `today_sales` and `today_bill_count`; fields `paper_cost` and `profit` are strictly excluded.
   - Staff stock API returns only sheet counts and bundle sizes; `cost` and purchase unit price are strictly excluded.
3. **Billing & Tiered Pricing**:
   - Tiered pricing rule for **Print B&W — A4** verified: 1 copy = ₹10 (S) / ₹15 (D); 5 copies = ₹30 (S) / ₹35 (D).
   - Single-side and double-side physical sheet deduction verified: 1 copy = 1 sheet for double-side jobs.
4. **PC Thermal Print Loop**:
   - `POST /api/printer/heartbeat` successfully registers online state.
   - `GET /api/printer/pending-jobs` fetches queued jobs and transitions state to `Printing`.
   - `POST /api/printer/jobs/<job_id>/status` updates state to `Printed`.
   - `POST /api/print-jobs/<job_id>/retry` successfully resets status to `Print Pending`.
5. **Data Cleanup & Integrity**:
   - All test transactions and print queue test slips removed.
   - Historical baseline of genuine bills, purchases, and inventory records perfectly preserved.
