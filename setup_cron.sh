#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$(which python3)"
mkdir -p "$DIR/logs"
CRON="0 8 * * * cd $DIR && $PY run.py >> $DIR/logs/cron.log 2>&1"
(crontab -l 2>/dev/null | grep -v "crawler/run.py") | crontab -
(crontab -l 2>/dev/null; echo "$CRON") | crontab -
echo "✅ Cron: mỗi ngày 8h sáng. Kiểm tra: crontab -l"
