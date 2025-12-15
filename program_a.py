"""Program A: TCP server + UDP client.

- Runs a TCP server listening on --tcp-port (default 5001).
- Runs a UDP client sending random 3-letter strings to Program B
  at --b-host and --udp-port (default 5000).

Behavior summary
----------------
* TCP server (A side)
  - Accept TCP connections and for each connection:
    - Read exactly 3 bytes (must use a read-exactly helper).
    - Validate: all 3 characters must be alphabetic and contain no vowels
      (a, e, i, o, u). Case-insensitive; validation done on lowercase.
    - If valid:
        * Respond with a TCP message consisting of:
            status byte 0x01
            followed by three uint16 values (big-endian), each equal to
            ord(letter) + 41 for the received letters (in order).
      If invalid:
        * Respond with a single status byte 0x00 and close.

* UDP client (A side)
  - On start, repeatedly:
      * generate a random 3-letter ASCII lowercase string [a-z]{3}
      * send via UDP to Program B (exactly 3 bytes)
      * wait for UDP response with configurable timeout (default 0.5s)
      * if timeout/no response: generate a NEW random 3-letter string and
        retry indefinitely until a UDP response is received.
      * When a response is received, treat it as a big-endian uint32 sum,
        print the sum and exit (or keep running if --loop is set).

"""
from __future__ import annotations

import argparse
import logging
import random
import signal
import socket
import string
import sys
import threading
from typing import Optional

from protocol import (
    UDP_REQUEST_LEN,
    UDP_RESPONSE_LEN,
    pack_udp_request,
    unpack_udp_response,
    pack_tcp_response_invalid,
    pack_tcp_response_valid,
)
from net_utils import (
    setup_logging,
    create_tcp_server_socket,
    create_udp_socket,
    read_exact,
    safe_close,
)


log = logging.getLogger(__name__)

# Global shutdown flag shared between threads
_shutdown_event = threading.Event()


# --- Validation helpers -----------------------------------------------------

VOWELS = set("aeiou")


def is_valid_letters(data: bytes) -> bool:
    """Return True if data is exactly 3 alphabetic characters with no vowels.

    The check is case-insensitive; we convert to lowercase for validation.
    """

    if len(data) != 3:
        return False
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return False

    text_lower = text.lower()
    if not all(ch.isalpha() for ch in text_lower):
        return False
    if any(ch in VOWELS for ch in text_lower):
        return False
    return True


# --- TCP server side (A) ----------------------------------------------------


def handle_tcp_client(conn: socket.socket, addr: tuple[str, int]) -> None:
    """Handle a single TCP client connection on Program A.

    This reads exactly 3 bytes, validates them, and sends back the
    protocol-defined response before closing the connection.
    """

    log.debug("[TCP] Connection from %s", addr)
    try:
        # Read exactly 3 bytes as required by the spec
        data = read_exact(conn, 3)
        log.debug("[TCP] Received raw bytes: %r from %s", data, addr)

        if not is_valid_letters(data):
            log.info("[TCP] Invalid message from %s -> responding with status=0", addr)
            resp = pack_tcp_response_invalid()
            conn.sendall(resp)
            return

        # Valid message: produce values ord(letter) + 41
        text = data.decode("ascii")
        values = tuple(ord(ch) + 41 for ch in text)
        log.info("[TCP] Valid message %r from %s, values=%s", text, addr, values)
        resp = pack_tcp_response_valid(values)  # type: ignore[arg-type]
        conn.sendall(resp)

    except Exception as exc:  # broad catch: we only log and close
        log.warning("[TCP] Error while handling client %s: %s", addr, exc)
    finally:
        safe_close(conn)
        log.debug("[TCP] Closed connection from %s", addr)


def tcp_server_loop(host: str, port: int) -> None:
    """Main loop for the TCP server running in its own thread.

    This accepts connections and dispatches a thread per connection
    until the global shutdown event is set.
    """

    srv_sock: Optional[socket.socket] = None
    try:
        srv_sock = create_tcp_server_socket(host, port)
        srv_sock.settimeout(1.0)  # periodic timeout to check shutdown
        log.info("[TCP] Server listening on %s:%d", host, port)

        while not _shutdown_event.is_set():
            try:
                conn, addr = srv_sock.accept()
            except socket.timeout:
                continue
            except OSError as exc:
                if _shutdown_event.is_set():
                    break
                log.error("[TCP] accept() failed: %s", exc)
                continue

            t = threading.Thread(
                target=handle_tcp_client, args=(conn, addr), daemon=True
            )
            t.start()

    finally:
        log.info("[TCP] Shutting down server socket")
        safe_close(srv_sock)


# --- UDP client side (A) ----------------------------------------------------


def random_three_letters() -> bytes:
    """Generate a random 3-letter lowercase ASCII string as bytes."""

    letters = random.choices(string.ascii_lowercase, k=3)
    return "".join(letters).encode("ascii")


def udp_client_once(
    b_host: str,
    udp_port: int,
    timeout: float,
) -> Optional[int]:
    """Send random strings over UDP until a single response is obtained.

    Returns the received sum (int) if successful, or None if shutdown
    was requested before success.
    """

    sock = create_udp_socket()
    sock.settimeout(timeout)
    log.info("[UDP] Client sending to %s:%d (timeout=%.3fs)", b_host, udp_port, timeout)
    try:
        while not _shutdown_event.is_set():
            msg = random_three_letters()
            payload = pack_udp_request(msg)
            try:
                log.info("[UDP] Sending %r to %s:%d", msg, b_host, udp_port)
                sock.sendto(payload, (b_host, udp_port))

                data, addr = sock.recvfrom(UDP_RESPONSE_LEN)
                log.info("[UDP] Received %d bytes from %s", len(data), addr)
                if len(data) != UDP_RESPONSE_LEN:
                    log.warning("[UDP] Ignoring response with wrong length: %d", len(data))
                    continue

                sum_value = unpack_udp_response(data)
                log.info("[UDP] Parsed sum value: %d", sum_value)
                return sum_value
            except socket.timeout:
                log.info("[UDP] Timeout waiting for response, will retry with new string")
                continue
            except OSError as exc:
                log.error("[UDP] Socket error: %s", exc)
                return None
    finally:
        safe_close(sock)

    return None


# --- CLI / main -------------------------------------------------------------


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Program A: TCP server + UDP client")
    parser.add_argument("--b-host", default="127.0.0.1", help="Program B host (default: 127.0.0.1)")
    parser.add_argument("--udp-port", type=int, default=5000, help="UDP port for Program B (default: 5000)")
    parser.add_argument("--tcp-port", type=int, default=5001, help="TCP port for this server (default: 5001)")
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.5,
        help="UDP response timeout in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="If set, keep sending even after successful response",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args(argv)


def _install_signal_handlers() -> None:
    """Install Ctrl+C handler to signal graceful shutdown."""

    def _handle_sigint(signum, frame):  # type: ignore[unused-argument]
        log.info("Received SIGINT, initiating shutdown...")
        _shutdown_event.set()

    signal.signal(signal.SIGINT, _handle_sigint)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)

    log.info("Starting Program A with args: %s", args)
    _install_signal_handlers()

    # Start TCP server thread
    tcp_thread = threading.Thread(
        target=tcp_server_loop,
        args=("0.0.0.0", args.tcp_port),
        daemon=True,
    )
    tcp_thread.start()

    # UDP client loop
    exit_code = 0
    try:
        while not _shutdown_event.is_set():
            result = udp_client_once(args.b_host, args.udp_port, args.timeout)
            if result is None:
                if _shutdown_event.is_set():
                    break
                log.error("[MAIN] UDP client encountered an error; exiting")
                exit_code = 1
                break

            print(result)
            sys.stdout.flush()

            if not args.loop:
                # Success and one-shot mode
                _shutdown_event.set()
                break

            log.info("[MAIN] --loop is set, sending another sequence")

    finally:
        # Ensure shutdown event is set so TCP server loop can exit
        _shutdown_event.set()
        # Wait briefly for the TCP thread to finish
        tcp_thread.join(timeout=3.0)
        log.info("Program A exiting with code %d", exit_code)

    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
