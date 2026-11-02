# Iread Photostat & Color Printing Billing — v2

Local-first billing app for one computer using Python, Flask and SQLite.

## Services included
- B&W photostat: A4, Legal and A3; single and double side
- Colour photostat: A4, Legal and A3; single and double side
- Scanning and sending/email/upload
- B&W printing: A4 first page and extra pages, A4 duplex, Legal and A3 single/double side
- Colour printing: A4 and A3 single/double side
- A4 130 gsm, A4 220 gsm and A3 220 gsm photo paper
- Laser 12x18: 130 gsm, 220 gsm, waterproof, sticker and waterproof sticker
- Lamination: ID card, RC book, A4, Legal and A3
- Frame setting: Mini, 4x4, A5, A4 and A3
- Polaroid 12x18 printing

## Important: sample prices
The initial sample rates are between ₹1 and ₹25. They are placeholders only, not confirmed Iread prices. Open **Price List** and replace them with your actual rates before live billing.

## Run on macOS
1. Install Python 3.10 or newer from https://www.python.org/downloads/.
2. Extract this ZIP and move the `iread_print_billing_v2` folder to Documents if desired.
3. Open Terminal and run:
   ```bash
   cd ~/Documents/iread_print_billing_v2
   chmod +x run_mac.command
   ./run_mac.command
   ```
   Adjust the folder path if you extracted elsewhere.
4. Open http://127.0.0.1:5000 in Chrome. Keep Terminal open while using the app. Stop with Control+C.

## Run on Windows
1. Install Python 3.10+ from https://www.python.org/downloads/ and enable “Add Python to PATH”.
2. Extract the ZIP, open the `project` folder and double-click `run_windows.bat`.
3. Open http://127.0.0.1:5000 in Chrome.

## Billing logic notes
- Formula: quantity × pages per copy × rate.
- For A4 B&W first-page/extra-page billing, add the first-page line once and add the extra-page service for each additional page. Keep pages-per-copy at 1 for those lines.
- Double-side options are separate services with their own editable rates. The side selector affects estimated paper usage; choose the matching service name and side setting when billing.
- Scanning, sending, lamination and frame setting do not count as paper consumption in the report.
- Paper usage is an estimate based on manually entered job details, not a live printer-counter reading.
- Thermal receipt printing uses the browser print dialog. Select the thermal printer, configure 58/80 mm paper width in the driver and disable browser headers/footers if needed.
- Back up `iread_billing.db` daily. Stop the app before copying the file.

## ChatGPT + Claude workflow
1. Share the project ZIP with ChatGPT for planning, formula review and test cases.
2. Ask Claude to implement one feature at a time and return complete updated files.
3. Keep a dated backup before replacing files.
4. Run and test sample bills before using the changes for real customers.
5. Share errors and reproduction steps with the assistants; avoid sharing private customer data.

Prompt: “Review this Iread Flask + SQLite billing project. Make only the requested change, preserve existing behavior, provide full updated files, explain database migration, and give manual test cases. Do not claim tests passed unless you ran them.”
