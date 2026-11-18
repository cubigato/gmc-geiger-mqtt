#!/bin/sh
set -eu

image=${1:?Usage: sh tests/test_container.sh IMAGE}
repo_dir=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)

# A mapped /dev/null can be opened but rejects serial configuration.
status=0
output=$(podman run --rm --network=none \
    --device /dev/null:/dev/ttyUSB0:rw \
    --mount "type=bind,src=$repo_dir/config.example.yaml,dst=/etc/gmc-geiger-mqtt/config.yaml,readonly" \
    "$image" 2>&1) || status=$?

if [ "$status" -ne 1 ] || ! printf '%s\n' "$output" | grep -F 'Inappropriate ioctl for device' >/dev/null; then
    printf 'Expected the bridge to open the mapped device and fail at serial setup (exit 1). Got exit %s.\n%s\n' "$status" "$output" >&2
    exit 1
fi

printf '%s\n' 'Container startup, config mount and device mapping passed.'
