# Iread Billing — Staff Android Mobile Application

Native Android application built with React Native, Expo, and TypeScript for staff counter billing at Iread Stations.

---

## Features

1. **Staff Authentication**:
   - Secure HMAC token login.
   - Staff credentials: `staff` / `iread@staff123` (Admin: `admin` / `iread@123`).
   - Strict role separation: Staff cannot edit historical bills, alter stock adjustments, or view business profits/costs.

2. **Fast Touch Billing POS**:
   - Categorized service catalog (Photostat, Print, Photo, Digital/Lamination).
   - Single-Side and Double-Side options per item.
   - Configurable tiered pricing automatically applied (e.g., **Print B&W — A4**: 1st copy ₹10/₹15, additional copies ₹5/copy).
   - Quantity/Copies counter with correct physical sheet calculation (1 copy = 1 sheet for double-side jobs as well).
   - Petpooja-style Paid / Unpaid payment status toggle with Cash / UPI / Card payment methods.
   - Discount support.
   - **"Save Only"** button: saves bill immediately to database and resets screen.
   - **"Save & Print"** button: saves bill and triggers wireless Wi-Fi printing on the Counter PC.

3. **PC-Based Wi-Fi Thermal Print Integration**:
   - Android phone sends bill wirelessly over shop Wi-Fi / LAN to the server.
   - Counter PC Print Service picks up the job and spools it directly to the physical thermal receipt printer (80mm/58mm).
   - Live real-time print status modal: Pending -> Printing -> Printed, with one-tap Retry.

4. **Counter Sales Summary**:
   - Displays today's total revenue (₹) and bill count.
   - Lists recent 20 bills with payment status.
   - Financial profit margins and paper cost remain strictly hidden from staff.

5. **Read-Only Paper & Stock Inventory**:
   - Displays available sheets, bundle counts, and reorder levels.
   - Highlights low-stock alerts.
   - Purchase costs and supplier rates remain strictly hidden from staff.

6. **Settings & Connectivity**:
   - Configurable Backend Server IP/URL (e.g., `http://192.168.1.100:5000`).
   - Built-in connection tester.
   - Live PC Thermal Printer status indicator (Online / Offline).

---

## Project Structure

```
mobile_app/
├── App.tsx                     # Main app root & tab navigation
├── app.json                    # Expo project configuration
├── package.json                # Dependencies and build scripts
├── tsconfig.json               # TypeScript configuration
├── assets/                     # App icon and splash screen assets
├── android/                    # Native Android project (Gradle)
└── src/
    ├── types/index.ts          # Shared TypeScript models and interfaces
    ├── context/AuthContext.tsx # User session & token state
    ├── services/api.ts         # REST API client with offline handling
    ├── screens/
    │   ├── LoginScreen.tsx     # Staff counter login screen
    │   ├── BillingScreen.tsx   # POS item grid, cart & checkout screen
    │   ├── SalesScreen.tsx     # Today sales & recent bills screen
    │   ├── StockScreen.tsx     # Read-only stock inventory screen
    │   └── SettingsScreen.tsx  # Server URL & PC printer status screen
    └── components/
        └── PrintStatusModal.tsx# Real-time thermal print status & retry modal
```

---

## Development & Building

### Running in Development
```bash
cd mobile_app
npm install
npm start
```

### Building the Standalone Android Release APK
```bash
cd mobile_app/android
./gradlew assembleRelease
```
The output APK will be generated at:
`mobile_app/android/app/build/outputs/apk/release/app-release.apk`
(and copied to `static/iread-billing-staff.apk` for direct download from the web interface).
