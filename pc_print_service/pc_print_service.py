#!/usr/bin/env python3
"""
Iread PC Print Service - Background Thermal Print Daemon
Connects to the Iread Billing backend over local Wi-Fi or LAN, receives print jobs
sent from staff Android mobile apps, and prints directly to the Counter PC's thermal printer.
"""

import os
import sys
import time
import json
import socket
import platform
import argparse
import logging
from pathlib import Path
from datetime import datetime

try:
    import requests
except ImportError:
    print("[ERROR] 'requests' library is required. Run: pip install requests")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("IreadPrintService")

VERSION = "2.0.0"
CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
RECEIPTS_DIR = Path(__file__).resolve().parent / "receipts"

DEFAULT_CONFIG = {
    "server_url": "http://127.0.0.1:5000",
    "api_token": "iread-print-token-2026",
    "printer_name": "__DEFAULT__",
    "poll_interval_seconds": 2,
    "heartbeat_interval_seconds": 10,
    "thermal_width": "80mm",
    "save_printed_slips_to_disk": True,
    "simulation_mode": False
}


def load_config(config_path=None):
    cfg = DEFAULT_CONFIG.copy()
    target_path = Path(config_path) if config_path else CONFIG_FILE
    if target_path.exists():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                cfg.update(loaded)
            logger.info(f"Loaded configuration from {target_path}")
        except Exception as e:
            logger.warning(f"Could not read {target_path} ({e}), using default configuration.")
    else:
        logger.info(f"No config.json found at {target_path}. Using defaults and saving default config.")
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass
    return cfg


def send_to_printer_macos_linux(printer_name, text_content):
    """Prints via lp command on macOS and Linux (CUPS)."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as tf:
        tf.write(text_content)
        temp_path = tf.name

    try:
        cmd = ["lp"]
        if printer_name and printer_name != "__DEFAULT__":
            cmd.extend(["-d", printer_name])
        cmd.extend(["-o", "raw", temp_path])
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            logger.info(f"Successfully spooled job to printer ({printer_name}): {res.stdout.strip()}")
            return True, ""
        else:
            logger.warning(f"lp command returned code {res.returncode}: {res.stderr.strip()}")
            # Retry without -o raw in case driver prefers text mode
            cmd_fallback = ["lp"]
            if printer_name and printer_name != "__DEFAULT__":
                cmd_fallback.extend(["-d", printer_name])
            cmd_fallback.append(temp_path)
            res2 = subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=10)
            if res2.returncode == 0:
                logger.info(f"Successfully spooled job with fallback to printer ({printer_name})")
                return True, ""
            return False, res2.stderr.strip() or res.stderr.strip()
    except Exception as e:
        return False, str(e)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def send_to_printer_windows(printer_name, text_content):
    """Prints via win32print on Windows if available, else raw spooler copy."""
    try:
        import win32print
        target_printer = win32print.GetDefaultPrinter() if (not printer_name or printer_name == "__DEFAULT__") else printer_name
        hprinter = win32print.OpenPrinter(target_printer)
        try:
            raw_bytes = text_content.encode("utf-8", errors="replace")
            hjob = win32print.StartDocPrinter(hprinter, 1, ("Iread Receipt", None, "RAW"))
            win32print.StartPagePrinter(hprinter)
            win32print.WritePrinter(hprinter, raw_bytes)
            win32print.EndPagePrinter(hprinter)
            win32print.EndDocPrinter(hprinter)
            logger.info(f"Successfully sent RAW print job to Windows printer: {target_printer}")
            return True, ""
        finally:
            win32print.ClosePrinter(hprinter)
    except ImportError:
        # Fallback to notepad /p or raw copy on Windows
        import tempfile
        import subprocess
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as tf:
            tf.write(text_content)
            temp_path = tf.name
        try:
            cmd = ["notepad.exe", "/p", temp_path]
            res = subprocess.run(cmd, capture_output=True, timeout=10)
            return True, ""
        except Exception as e:
            return False, f"win32print not installed and notepad fallback failed: {e}"
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass
    except Exception as e:
        return False, f"Windows win32print error: {e}"


def print_receipt(printer_name, receipt_text, simulation_mode=False, save_to_disk=True, job_id=""):
    """Dispatches printing according to current operating system."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    if save_to_disk:
        filename = f"receipt_{job_id or int(time.time())}.txt"
        filepath = RECEIPTS_DIR / filename
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(receipt_text)
            logger.info(f"Saved copy of receipt to {filepath}")
        except Exception as e:
            logger.warning(f"Could not save receipt copy: {e}")

    if simulation_mode:
        logger.info(f"[SIMULATION MODE] Receipt rendered for job {job_id}:\n" + receipt_text)
        return True, ""

    os_type = platform.system().lower()
    if "windows" in os_type:
        return send_to_printer_windows(printer_name, receipt_text)
    else:
        # macOS or Linux
        return send_to_printer_macos_linux(printer_name, receipt_text)


class PCPrintService:
    def __init__(self, config):
        self.config = config
        self.server_url = config.get("server_url", "http://127.0.0.1:5000").rstrip("/")
        self.api_token = config.get("api_token", "iread-print-token-2026")
        self.printer_name = config.get("printer_name", "__DEFAULT__")
        self.poll_interval = float(config.get("poll_interval_seconds", 2))
        self.heartbeat_interval = float(config.get("heartbeat_interval_seconds", 10))
        self.simulation_mode = bool(config.get("simulation_mode", False))
        self.save_to_disk = bool(config.get("save_printed_slips_to_disk", True))

        self.last_heartbeat = 0
        self.hostname = socket.gethostname()
        self.os_info = f"{platform.system()} {platform.release()}"

        self.session = requests.Session()
        self.session.headers.update({
            "X-Printer-Token": self.api_token,
            "User-Agent": f"IreadPCPrintService/{VERSION} ({self.hostname})"
        })

    def send_heartbeat(self):
        url = f"{self.server_url}/api/printer/heartbeat"
        payload = {
            "hostname": self.hostname,
            "os": self.os_info,
            "printer_name": self.printer_name,
            "version": VERSION,
            "status": "online"
        }
        try:
            res = self.session.post(url, json=payload, timeout=5)
            if res.status_code == 200:
                self.last_heartbeat = time.time()
                return True
            else:
                logger.warning(f"Heartbeat rejected with HTTP {res.status_code}: {res.text}")
                return False
        except Exception as e:
            logger.debug(f"Heartbeat connection error to {url}: {e}")
            return False

    def check_pending_jobs(self):
        url = f"{self.server_url}/api/printer/pending-jobs"
        try:
            res = self.session.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                return data.get("jobs", [])
            else:
                logger.warning(f"Failed to query pending jobs (HTTP {res.status_code}): {res.text}")
                return []
        except Exception as e:
            logger.debug(f"Pending jobs polling error: {e}")
            return []

    def update_job_status(self, job_id, status, error_message=""):
        url = f"{self.server_url}/api/printer/jobs/{job_id}/status"
        payload = {
            "status": status,
            "error_message": error_message,
            "printer_name": self.printer_name
        }
        try:
            res = self.session.post(url, json=payload, timeout=5)
            return res.status_code == 200
        except Exception as e:
            logger.error(f"Failed to update job status for {job_id}: {e}")
            return False

    def process_job(self, job):
        job_id = job.get("job_id")
        bill_no = job.get("bill_no", "N/A")
        receipt_text = job.get("receipt_text", "")
        thermal_width = job.get("thermal_width", "80mm")

        logger.info(f"==> Processing Print Job: {job_id} for Bill: {bill_no} (Width: {thermal_width})")

        success, err = print_receipt(
            printer_name=self.printer_name,
            receipt_text=receipt_text,
            simulation_mode=self.simulation_mode,
            save_to_disk=self.save_to_disk,
            job_id=job_id
        )

        if success:
            logger.info(f"✓ Print Successful for {job_id} ({bill_no})")
            self.update_job_status(job_id, "Printed")
        else:
            logger.error(f"✕ Print Failed for {job_id}: {err}")
            self.update_job_status(job_id, "Print Failed", error_message=err)

    def run(self):
        logger.info("=" * 60)
        logger.info(f"  IREAD PC PRINT SERVICE v{VERSION}")
        logger.info(f"  Server URL   : {self.server_url}")
        logger.info(f"  Printer Name : {self.printer_name}")
        logger.info(f"  Host / OS    : {self.hostname} ({self.os_info})")
        logger.info(f"  Mode         : {'SIMULATION / TEST' if self.simulation_mode else 'PHYSICAL HARDWARE SPOOLER'}")
        logger.info("=" * 60)

        # Initial heartbeat
        if self.send_heartbeat():
            logger.info("✓ Initial server heartbeat acknowledged. Service is ONLINE.")
        else:
            logger.warning("! Could not reach server on initial startup. Will keep retrying...")

        while True:
            try:
                now = time.time()
                if now - self.last_heartbeat >= self.heartbeat_interval:
                    self.send_heartbeat()

                jobs = self.check_pending_jobs()
                if jobs:
                    for job in jobs:
                        self.process_job(job)

                time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                logger.info("Shutdown requested by user. Exiting gracefully.")
                break
            except Exception as e:
                logger.error(f"Unexpected loop exception: {e}")
                time.sleep(self.poll_interval)


def main():
    parser = argparse.ArgumentParser(description="Iread PC Thermal Print Service")
    parser.add_argument("--server", help="Server backend URL (e.g. http://192.168.1.100:5000)")
    parser.add_argument("--token", help="PC Print Service API token")
    parser.add_argument("--printer", help="Local printer name (or __DEFAULT__)")
    parser.add_argument("--config", help="Path to config.json file")
    parser.add_argument("--simulate", action="store_true", help="Run in simulation mode (logs receipt without sending to hardware)")
    parser.add_argument("--test", action="store_true", help="Send a local test slip to printer and exit")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.server:
        cfg["server_url"] = args.server
    if args.token:
        cfg["api_token"] = args.token
    if args.printer:
        cfg["printer_name"] = args.printer
    if args.simulate:
        cfg["simulation_mode"] = True

    if args.test:
        test_slip = """==========================================
              IREAD STATIONS
     Printing • Photocopy • Lamination
==========================================
TEST SLIP : Hardware Connectivity Check
Date      : """ + datetime.now().strftime("%d/%m/%Y %I:%M %p") + """
Printer   : """ + cfg.get("printer_name", "__DEFAULT__") + """
Status    : Connection OK
==========================================
      PC Thermal Print Service Test
==========================================\n\n\n\x1dVA0"""
        print(f"Sending test slip to printer {cfg.get('printer_name')}...")
        ok, err = print_receipt(cfg.get("printer_name"), test_slip, simulation_mode=cfg.get("simulation_mode", False), job_id="TEST_MANUAL")
        if ok:
            print("✓ Test slip sent successfully!")
            sys.exit(0)
        else:
            print(f"✕ Test print failed: {err}")
            sys.exit(1)

    service = PCPrintService(cfg)
    service.run()


if __name__ == "__main__":
    main()
