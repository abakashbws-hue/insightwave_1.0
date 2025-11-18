#!/bin/bash

# 1. Start ADK Web in the background (Port 8000)
# We bind to 127.0.0.1 because only Nginx needs to talk to it.
echo "Starting ADK Web..."
adk web --host 127.0.0.1 --port 8000 --allow_origins="*" &

# 2. Start Nginx in the foreground (Port 8080 - Public)
echo "Starting Nginx..."
nginx -g 'daemon off;'