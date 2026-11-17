# Iread PC Thermal Print Service

Cross-platform background print worker for the Iread Billing App.
Allows staff to create bills on their Android phones and wirelessly print thermal receipts via the Counter PC without OTG/USB cables on the phone.

---

## Architecture Overview

```
 [ Android Mobile App (Staff) ]
             |
             | Wi-Fi (HTTP / JSON API)
             v
 [ Iread Billing Backend (app.py) ] <--- Print Job Queue
             ^
             | Polling & Heartbeat (every 2s)
 [ Counter PC Print Service ]
             |
             | Direct USB Spooler (RAW / CUPS / Win32)
             v
 [ Thermal Printer (80mm / 58mm) ]
```

---

## 1. Quick Start

### Prerequisites
- Python 3.8+ installed on Counter PC.
- Thermal receipt printer connected to Counter PC via USB and installed as a system printer (e.g. `POS-80`, `EPSON TM-T82`, etc.).

### Run in One Command
```bash
# On macOS or Linux:
./run_service.sh

# On Windows:
run_service.bat
```

---

## 2. Configuration (`config.json`)

Edit `config.json` on the Counter PC:

```json
{
  "server_url": "http://192.168.1.100:5000",
  "api_token": "iread-print-token-2026",
  "printer_name": "__DEFAULT__",
  "poll_interval_seconds": 2,
  "heartbeat_interval_seconds": 10,
  "thermal_width": "80mm",
  "save_printed_slips_to_disk": true,
  "simulation_mode": false
}
```

- **`server_url`**: The IP or URL of the main billing server.
- **`api_token`**: Must match the token in Admin Web > Printer Settings (`iread-print-token-2026`).
- **`printer_name`**: Name of the thermal printer (or `__DEFAULT__` to use the OS default printer).
- **`save_printed_slips_to_disk`**: Keeps a text copy of every receipt in `receipts/` for accounting records.
- **`simulation_mode`**: Set `true` to test without physical hardware (receipts will be logged to console and saved to disk).

---

## 3. Test Printing

To verify connectivity to the physical printer:
```bash
python3 pc_print_service.py --test
```

To test without hardware (Simulation mode):
```bash
python3 pc_print_service.py --simulate
```

---

## 4. Automatic Startup on Boot

To keep the service running in the background automatically when the PC turns on:

```bash
# macOS & Linux:
./install_service.sh
```

On Windows, create a shortcut to `run_service.bat` in your Windows Startup folder (`Win + R` > `shell:startup`).
