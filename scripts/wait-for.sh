#!/usr/bin/env bash
# wait-for.sh URL [TIMEOUT_SECONDS]
# Polls a URL until it answers, so CI steps do not race the containers.
set -euo pipefail

url="${1:?usage: wait-for.sh URL [timeout]}"
timeout="${2:-60}"
deadline=$(( $(date +%s) + timeout ))

printf 'waiting for %s (timeout %ss)' "$url" "$timeout"
until curl -fsS -o /dev/null "$url" 2>/dev/null; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        printf '\nTIMEOUT: %s did not become ready in %ss\n' "$url" "$timeout" >&2
        exit 1
    fi
    printf '.'
    sleep 2
done
printf '\n%s is ready\n' "$url"
