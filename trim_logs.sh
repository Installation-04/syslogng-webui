#!/usr/bin/env bash
# Deletes oldest log files until the log directory is back under the cap.

LOG_DIR="/path/to/your/logs"
MAX_SIZE_KB=$((20 * 1024 * 1024))  # 20 GB in KB

current_size_kb=$(du -s "$LOG_DIR" | cut -f1)

if [ "$current_size_kb" -le "$MAX_SIZE_KB" ]; then
    exit 0
fi

echo "$(date): log dir is ${current_size_kb}KB, over ${MAX_SIZE_KB}KB cap, trimming oldest files..."

# Oldest-first, delete one at a time and recheck, so we never over-delete
find "$LOG_DIR" -type f \( -name "*.log" -o -name "*.gz" \) -printf '%T@ %p\n' \
  | sort -n \
  | while read -r _ file; do
      current_size_kb=$(du -s "$LOG_DIR" | cut -f1)
      if [ "$current_size_kb" -le "$MAX_SIZE_KB" ]; then
          break
      fi
      echo "  removing $file"
      rm -f "$file"
    done
