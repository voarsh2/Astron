#!/bin/bash

LOG_LEVEL=${LOG_LEVEL:-info}
CONFIG_FILE=${CONFIG_FILE:-astrond.yml}

if [ -f ./astrond.exe ]; then
    exec ./astrond.exe -l "$LOG_LEVEL" "$CONFIG_FILE"
else
    exec ./astrond -l "$LOG_LEVEL" "$CONFIG_FILE"
fi
