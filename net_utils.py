"""Common networking helpers for the socket programming project.

This module provides utilities shared between Program A and Program B,
including robust "read exactly N bytes" helpers and simple logging.

"""
from __future__ import annotations

from typing import Optional, Tuple
import logging
import socket


# --- Logging helpers --------------------------------------------------------


def setup_logging(verbose: bool) -> None:
    """Configure root logger based on verbosity flag."""

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
    )


# --- Socket helpers ---------------------------------------------------------


def create_tcp_server_socket(host: str, port: int, backlog: int = 5) -> socket.socket:
    """Create, bind, and listen on a TCP server socket.

    The returned socket is ready for accept().
    """

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Allow quick restart of the server
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(backlog)
    return srv


def create_udp_socket(bind_host: Optional[str] = None, bind_port: Optional[int] = None) -> socket.socket:
    """Create a UDP socket, optionally bound to a local host/port."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if bind_host is not None and bind_port is not None:
        sock.bind((bind_host, bind_port))
    return sock


def read_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly *n* bytes from a TCP socket.

    Raises RuntimeError if the connection is closed before *n* bytes are
    received. This function loops until all bytes have been read or an
    error/EOF occurs.
    """

    chunks: list[bytes] = []
    bytes_remaining = n

    while bytes_remaining > 0:
        try:
            chunk = sock.recv(bytes_remaining)
        except OSError as exc:  # includes timeouts
            raise RuntimeError(f"Socket recv failed: {exc}") from exc

        if not chunk:
            # Remote closed connection
            raise RuntimeError(
                f"Connection closed while reading, {bytes_remaining} bytes remaining"
            )

        chunks.append(chunk)
        bytes_remaining -= len(chunk)

    return b"".join(chunks)


def safe_close(sock: Optional[socket.socket]) -> None:
    """Safely close a socket, ignoring common errors."""

    if sock is None:
        return
    try:
        sock.close()
    except OSError:
        pass


def connect_tcp(host: str, port: int, timeout: Optional[float] = None) -> socket.socket:
    """Create a TCP connection with optional timeout and basic error handling."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if timeout is not None:
        sock.settimeout(timeout)
    try:
        sock.connect((host, port))
    except OSError:
        sock.close()
        raise
    return sock
