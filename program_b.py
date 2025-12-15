"""Program B: UDP server + TCP client.

- Runs a UDP server listening on --udp-port (default 5000).
- Acts as a TCP client connecting to Program A at --a-host and --tcp-port
  (default 5001) for each UDP request.

Behavior summary
----------------
* UDP server (B side)
  - Wait for UDP datagrams.
  - If the datagram payload is not exactly 3 bytes, ignore it.
  - For valid 3-byte payloads:
      * reverse the 3 letters and send them as a TCP request to Program A
        (exactly 3 bytes).
      * read the TCP response:
          - first 1 byte status
          - if status == 0x00 (invalid): do NOT send any UDP response.
          - if status == 0x01 (valid): read 3x uint16 values (big-endian),
            sum them, and send the sum back to the original UDP sender as a
            4-byte big-endian uint32.

"""
from __future__ import annotations

import argparse
import logging
import socket
from typing import Optional

from protocol import (
    TCP_REQUEST_LEN,
    TCP_RESPONSE_HEADER_LEN,
    TCP_RESPONSE_VALID_PAYLOAD_LEN,
    UDP_REQUEST_LEN,
    UDP_RESPONSE_LEN,
    STATUS_INVALID,
    unpack_tcp_response,
    pack_tcp_request,
    pack_udp_response,
)
from net_utils import (
    setup_logging,
    create_udp_socket,
    connect_tcp,
    read_exact,
    safe_close,
)


log = logging.getLogger(__name__)


def handle_udp_request(
    data: bytes,
    client_addr: tuple[str, int],
    a_host: str,
    tcp_port: int,
    udp_sock: socket.socket,
    tcp_timeout: float = 3.0,
) -> None:
    """Process a single UDP request payload.

    If the TCP exchange with Program A yields a valid response, send
    the sum back over UDP. Otherwise, do nothing.
    """

    if len(data) != UDP_REQUEST_LEN:
        log.debug("[UDP] Ignoring datagram from %s with invalid length %d", client_addr, len(data))
        return

    log.info("[UDP] Handling request %r from %s", data, client_addr)
    reversed_letters = data[::-1]
    tcp_req = pack_tcp_request(reversed_letters)

    sock: Optional[socket.socket] = None
    try:
        sock = connect_tcp(a_host, tcp_port, timeout=tcp_timeout)
        log.info("[TCP] Connected to A at %s:%d", a_host, tcp_port)

        # Send request
        sock.sendall(tcp_req)
        log.debug("[TCP] Sent request %r", tcp_req)

        # Read status byte
        status_bytes = read_exact(sock, TCP_RESPONSE_HEADER_LEN)
        # If status is valid, also read payload
        status = status_bytes[0]
        log.debug("[TCP] Received status byte: 0x%02x", status)

        if status == STATUS_INVALID:
            log.info("[TCP] A reported invalid message for %r; no UDP response", reversed_letters)
            return

        # Read the remaining payload for a valid response (3x uint16)
        payload = read_exact(sock, TCP_RESPONSE_VALID_PAYLOAD_LEN)
        full_resp = status_bytes + payload
        tcp_resp = unpack_tcp_response(full_resp)

        if not tcp_resp.is_valid or tcp_resp.values is None:
            log.warning("[TCP] Parsed response marked invalid unexpectedly; no UDP response")
            return

        values = tcp_resp.values
        sum_value = sum(values)
        log.info("[TCP] Valid response values=%s, sum=%d", values, sum_value)

        # Send UDP response with the sum
        udp_payload = pack_udp_response(sum_value)
        udp_sock.sendto(udp_payload, client_addr)
        log.info("[UDP] Sent response to %s", client_addr)

    except Exception as exc:
        log.warning("[B] Error while handling UDP request from %s: %s", client_addr, exc)
    finally:
        safe_close(sock)


# --- UDP server loop --------------------------------------------------------


def udp_server_loop(a_host: str, udp_port: int, tcp_port: int) -> None:
    sock = create_udp_socket("0.0.0.0", udp_port)
    log.info("[UDP] Server listening on 0.0.0.0:%d", udp_port)

    while True:
        try:
            data, addr = sock.recvfrom(4096)
        except OSError as exc:
            log.error("[UDP] recvfrom failed: %s", exc)
            break

        handle_udp_request(data, addr, a_host, tcp_port, sock)


# --- CLI / main -------------------------------------------------------------


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Program B: UDP server + TCP client")
    parser.add_argument("--a-host", default="127.0.0.1", help="Program A host (default: 127.0.0.1)")
    parser.add_argument("--udp-port", type=int, default=5000, help="UDP port to listen on (default: 5000)")
    parser.add_argument("--tcp-port", type=int, default=5001, help="TCP port on Program A (default: 5001)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)

    log.info("Starting Program B with args: %s", args)
    try:
        udp_server_loop(args.a_host, args.udp_port, args.tcp_port)
    except KeyboardInterrupt:
        log.info("Received KeyboardInterrupt, shutting down Program B")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
