"""Errors callers can distinguish without parsing log strings."""


class DriverError(Exception):
    """Base error exposed by the driver API."""


class DeviceUnavailable(DriverError):
    """Device disconnected, changed identity, or could not be opened."""


class DevicePermissionError(DeviceUnavailable):
    """The current user lacks access to the selected command collection."""


class ProtocolError(DriverError):
    """The peer returned a malformed or unexpected response."""


class ResponseTimeout(DriverError):
    """No matching reply arrived before the deadline."""


class UnsupportedDevice(DriverError):
    """The device or feature has not been implemented for this model."""
