# Host statistics on the Glyph display

```sh
# Inspect one sample without opening the keyboard.
epomaker host-info
# Send one sample to the display.
epomaker --device /dev/hidrawN system-info
# Send 20 samples with a three-second pause between sends.
epomaker --device /dev/hidrawN system-info --count 20 --interval 3 --disk / --interface eth0
```

The command runs in the foreground and installs no service. Counts are bounded to
1–10,000 and intervals to 0.1–3,600 seconds. Ctrl+C closes the HID handle and returns
exit status 130. The final JSON contains the number sent and last collected sample.
There is no firmware readback for display statistics; successful sending is not a
verified display rendering result.

Collection uses Linux interfaces rather than the vendor's native helper processes:

- CPU usage comes from consecutive aggregate `/proc/stat` samples, excluding guest
  fields already counted in user/nice time. The first sample waits 100 ms; subsequent
  samples cover the time since the preceding one.
- Used memory is `MemTotal - MemAvailable`, converted from the kernel's KiB values.
- Disk space comes from the filesystem containing `--disk`, default `/`.
- Network values are cumulative bytes on the selected interface, not transfer rates.
  Without `--interface`, the lowest-metric active default IPv4 route supplies it.
  IPv6-only hosts can specify an interface explicitly.
- CPU temperature is the highest available input from recognized CPU hwmon drivers
  (`coretemp`, `k10temp`, `zenpower`, `cpu_thermal`), rounded to whole degrees Celsius.
  GPU and generic motherboard sensors are excluded. Driver-specific offsets and
  sensor selection can differ from the vendor application's selected sensor.

Missing CPU temperatures and missing default routes are reported as warnings; the
limited display fields receive zero. Malformed required CPU/memory data and explicit
interface read failures stop the command. A bad optional temperature sensor does not
hide readable sensors from the same device.

The packet matches the shipped `setOLEDSysInfo`: command `0x22`, header checksum at
byte 7, disk and memory values at bytes 8–15, CPU usage/temperature at 16–17 and
network totals at 18–21. Byte counts are rounded to whole GiB with .5 rounded upward.
GiB fields are unsigned 16-bit; out-of-range values are rejected instead of wrapping.
The vendor's refresh path normally sends every three seconds.

Local host collection was exercised successfully. Tests cover units, packet bytes,
counter resets, missing/malformed sensors, interface selection, repeat sends and
interruption. Physical display output remains unverified.

Primary Linux references: [proc filesystem](https://docs.kernel.org/filesystems/proc.html)
and [hwmon sysfs interface](https://docs.kernel.org/hwmon/sysfs-interface.html).
