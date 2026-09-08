# Hardware validation

No configuration feature is hardware-verified yet. The connected Glyph's Bluetooth descriptor
matches report 6 with 65-byte input/output payloads, VID/PID 3151:5004, usage page FF55/usage 0202.
The current user's `/dev/hidraw3` is root-only, so live command validation has not run.

Discover dynamically. VID/PID and descriptor matching precede opening; the firmware's internal
ID must be 3059 before the current Glyph configuration API writes anything. USB uses feature
report 0, 64 payload bytes; Bluetooth uses output/input report 6 with the extra 55 marker.

The driver does not require a root GUI. Device permissions should be granted to the active user
for the specific command collection using the distribution's udev/ACL mechanism. No broad
MODE=0666 rule or system permission change is installed by this package.

Hardware test order: identify/status; complete read backup; reversible RGB change and restore;
one noncritical key and restore; macro; screen pattern; sleep/reconnect; USB/Bluetooth switching;
receiver discovery and routing. A successful write alone is not proof of persistence.

HIDRAW behavior is documented by the Linux project:
https://docs.kernel.org/hid/hidraw.html

For unnumbered USB feature replies, Linux may return exactly the payload length without the
synthetic zero that another platform's shim uses. The transport accepts the explicit 64-byte
unnumbered form and 65-byte report-prefixed form; numbered reports require their ID. Normal
Bluetooth keyboard input reports are discarded and never logged.
