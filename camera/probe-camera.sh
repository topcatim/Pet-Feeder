#!/bin/sh
# The camera ribbon is marginal: the ov5647 probe sometimes fails at boot (bad chip ID / i2c -5).
# Re-probe the sensor until it binds, so feeder-cam doesn't start with no camera.
dev=10-0036
for i in 1 2 3 4 5 6 7 8 9 10; do
    [ -e /sys/bus/i2c/drivers/ov5647/$dev ] && exit 0
    echo $dev > /sys/bus/i2c/drivers/ov5647/bind 2>/dev/null
    sleep 2
done
[ -e /sys/bus/i2c/drivers/ov5647/$dev ] || { echo "ov5647 did not bind after 10 tries" >&2; exit 1; }
