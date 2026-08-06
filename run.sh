#!/bin/bash
CD_PATH="$(cd "$(dirname "$0")" && pwd)"
cd "$CD_PATH"
/usr/bin/python3 reminder_system.py >> "$CD_PATH/cron_log.txt" 2>&1
