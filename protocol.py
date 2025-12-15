"""Protocol definitions and helpers for the A B socket interaction.

This module centralizes all wire-format packing/unpacking so both
programs share the exact same behavior.

"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple
import struct

# --- Constants --------------------------------------------------------------

# Status codes for TCP response from A to B
STATUS_INVALID = 0x00
STATUS_VALID = 0x01

# Protocol sizes
UDP_REQUEST_LEN = 3  # bytes
TCP_REQUEST_LEN = 3  # bytes
TCP_RESPONSE_HEADER_LEN = 1  # status byte
TCP_RESPONSE_VALID_PAYLOAD_LEN = 3 * 2  # 3 uint16 values
UDP_RESPONSE_LEN = 4  # uint32


# --- Helper data structures -------------------------------------------------

@dataclass(slots=True)
class TcpResponse:
    """Parsed representation of the TCP response from A.

    Attributes
    ----------
    status: int
        STATUS_VALID or STATUS_INVALID.
    values: Tuple[int, int, int] | None
        When status is STATUS_VALID, a tuple of three uint16 values.
        When STATUS_INVALID, this is None.
    """

    status: int
    values: Tuple[int, int, int] | None

    @property
    def is_valid(self) -> bool:
        return self.status == STATUS_VALID


# --- Packing helpers --------------------------------------------------------


def pack_tcp_request(letters: bytes) -> bytes:
    """Pack a TCP request payload.

    Parameters
    ----------
    letters:
        Exactly 3-byte ASCII sequence.
    """

    if len(letters) != TCP_REQUEST_LEN:
        raise ValueError(f"TCP request must be exactly {TCP_REQUEST_LEN} bytes")
    return letters


def pack_tcp_response_invalid() -> bytes:
    """Pack an invalid TCP response (status only)."""

    return struct.pack("!B", STATUS_INVALID)


def pack_tcp_response_valid(values: Tuple[int, int, int]) -> bytes:
    """Pack a valid TCP response.

    Layout:
        status (1 byte) = 0x01
        followed by three big-endian uint16 values.
    """

    if len(values) != 3:
        raise ValueError("Expected exactly 3 values for valid TCP response")

    return struct.pack("!BHHH", STATUS_VALID, *values)


def unpack_tcp_response(data: bytes) -> TcpResponse:
    """Decode a TCP response from raw bytes.

    This expects at least 1 byte (status). If status indicates VALID,
    the caller is responsible for having already read the additional
    6 bytes (for 3x uint16).
    """

    if not data:
        raise ValueError("Empty TCP response")

    status = data[0]
    if status == STATUS_INVALID:
        return TcpResponse(status=status, values=None)

    if len(data) != TCP_RESPONSE_HEADER_LEN + TCP_RESPONSE_VALID_PAYLOAD_LEN:
        raise ValueError(
            f"Valid TCP response must be {TCP_RESPONSE_HEADER_LEN + TCP_RESPONSE_VALID_PAYLOAD_LEN} bytes, "
            f"got {len(data)}"
        )

    _, v1, v2, v3 = struct.unpack("!BHHH", data)
    return TcpResponse(status=status, values=(v1, v2, v3))


def pack_udp_request(letters: bytes) -> bytes:
    """Pack a UDP request A->B.

    The payload is exactly the 3 raw bytes.
    """

    if len(letters) != UDP_REQUEST_LEN:
        raise ValueError(f"UDP request must be exactly {UDP_REQUEST_LEN} bytes")
    return letters


def pack_udp_response(sum_value: int) -> bytes:
    """Pack a UDP response B->A.

    One big-endian uint32: the sum of the three uint16 values.
    """

    if not (0 <= sum_value <= 0xFFFFFFFF):
        raise ValueError("sum_value must fit into uint32")
    return struct.pack("!I", sum_value)


def unpack_udp_response(data: bytes) -> int:
    """Unpack UDP response and return the uint32 sum value."""

    if len(data) != UDP_RESPONSE_LEN:
        raise ValueError(f"UDP response must be {UDP_RESPONSE_LEN} bytes")
    (value,) = struct.unpack("!I", data)
    return value
