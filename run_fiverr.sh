#!/bin/bash
cd /home/ubuntu/fiverr

# Kill stale Chrome/driver
pkill -f chrome
pkill -f chromedriver

# Start headless Chrome (for attachable debugging)
google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/fiverr_profile \
  --no-sandbox --disable-dev-shm-usage --disable-gpu \
  --headless --disable-software-rasterizer &

# Wait for Chrome to boot
sleep 3

# Run the bot
/usr/bin/python3 /home/ubuntu/fiverr/fiverr_keeper_sb.py
