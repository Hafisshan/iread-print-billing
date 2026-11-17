#!/usr/bin/env bash
# Iread PC Thermal Print Service Auto-Installer
# Configures auto-start on boot for macOS (launchd) or Linux (systemd)

set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PYTHON_PATH="$(which python3 || echo '/usr/bin/python3')"

echo "=========================================================="
echo " Installing Iread PC Print Background Service"
echo " Working Directory: $DIR"
echo " Python: $PYTHON_PATH"
echo "=========================================================="

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS launchd setup
    PLIST_DIR="$HOME/Library/LaunchAgents"
    PLIST_FILE="$PLIST_DIR/com.iread.pcprintservice.plist"
    mkdir -p "$PLIST_DIR"

    cat <<EOF > "$PLIST_FILE"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.iread.pcprintservice</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$DIR/pc_print_service.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$DIR/service.log</string>
    <key>StandardErrorPath</key>
    <string>$DIR/service_err.log</string>
</dict>
</plist>
EOF

    echo "Loading launchd service: $PLIST_FILE"
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    launchctl load "$PLIST_FILE"
    echo "✓ macOS LaunchAgent installed and running!"
    echo "Logs are available at: $DIR/service.log"

elif [[ "$OSTYPE" == "linux"* ]]; then
    # Linux systemd setup
    SERVICE_FILE="/etc/systemd/system/iread-pc-print.service"
    if [ "$EUID" -ne 0 ]; then
        echo "Note: Linux systemd installation requires sudo. Re-run with sudo if needed."
        echo "Creating local user systemd service instead..."
        SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
        mkdir -p "$SYSTEMD_USER_DIR"
        cat <<EOF > "$SYSTEMD_USER_DIR/iread-pc-print.service"
[Unit]
Description=Iread PC Thermal Print Service
After=network.target

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=$PYTHON_PATH $DIR/pc_print_service.py
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF
        systemctl --user daemon-reload
        systemctl --user enable --now iread-pc-print.service
        echo "✓ Linux user systemd service started and enabled!"
    else
        cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Iread PC Thermal Print Service
After=network.target

[Service]
Type=simple
User=$(logname || echo 'root')
WorkingDirectory=$DIR
ExecStart=$PYTHON_PATH $DIR/pc_print_service.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl enable --now iread-pc-print.service
        echo "✓ Systemd service installed and running!"
    fi
fi
