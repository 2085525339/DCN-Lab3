#!/usr/bin/env python3
"""User-facing Fibonacci HTTP server for DCN Lab 3."""

from __future__ import annotations

import os
import re
import socket
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlencode, urlsplit


HOST = os.getenv("US_HOST", "0.0.0.0")
PORT = int(os.getenv("US_PORT", "8080"))
UDP_TIMEOUT = float(os.getenv("US_UDP_TIMEOUT", "3"))
HTTP_TIMEOUT = float(os.getenv("US_HTTP_TIMEOUT", "5"))


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _single_query_value(query: dict[str, list[str]], name: str) -> str:
    values = query.get(name)
    if not values or len(values) != 1 or not values[0]:
        raise ValueError(f"Missing or invalid parameter: {name}")
    return values[0]


def _port(value: str) -> int:
    result = int(value)
    if not 1 <= result <= 65535:
        raise ValueError("port must be between 1 and 65535")
    return result


def _udp_exchange(host: str, port: int, message: str) -> str:
    addresses = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_DGRAM)
    last_error: Exception | None = None
    for family, socket_type, protocol, _, address in addresses:
        try:
            with socket.socket(family, socket_type, protocol) as sock:
                sock.settimeout(UDP_TIMEOUT)
                sock.sendto(message.encode("utf-8"), address)
                response, _ = sock.recvfrom(4096)
                return response.decode("utf-8")
        except OSError as exc:
            last_error = exc
    raise ConnectionError(f"UDP exchange failed: {last_error}")


def _query_as(as_ip: str, as_port: int, hostname: str) -> str:
    response = _udp_exchange(as_ip, as_port, f"TYPE=A\nNAME={hostname}\n")
    if response.strip() == "ERROR":
        raise LookupError(f"AS has no record for {hostname}")

    match = re.search(
        r"^NAME=(\S+) VALUE=(\S+) TTL=(\d+)$",
        response.replace("\r\n", "\n"),
        flags=re.MULTILINE,
    )
    if not match or match.group(1) != hostname:
        raise LookupError("AS returned an invalid DNS response")
    return match.group(2)


def _fetch_fibonacci(fs_ip: str, fs_port: int, number: int) -> bytes:
    url = "http://{}:{}/fibonacci?{}".format(
        fs_ip,
        fs_port,
        urlencode({"number": str(number)}),
    )
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            if response.status != 200:
                raise ConnectionError(f"FS returned HTTP {response.status}")
            return response.read()
    except urllib.error.HTTPError as exc:
        raise ConnectionError(f"FS returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Could not reach FS: {exc.reason}") from exc


class UserHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_bytes(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _send_text(self, status: int, body: str) -> None:
        self._send_bytes(status, body.encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path)
        if path.path == "/health":
            self._send_text(200, "OK\n")
            return
        if path.path != "/fibonacci":
            self._send_text(404, "Not Found\n")
            return

        try:
            query = parse_qs(path.query, keep_blank_values=True)
            hostname = _single_query_value(query, "hostname")
            fs_port = _port(_single_query_value(query, "fs_port"))
            number = int(_single_query_value(query, "number"))
            if number < 0:
                raise ValueError("number must be non-negative")
            as_ip = _single_query_value(query, "as_ip")
            as_port = _port(_single_query_value(query, "as_port"))
        except (ValueError, TypeError):
            self._send_text(400, "Bad Request\n")
            return

        try:
            fs_ip = _query_as(as_ip, as_port, hostname)
            result = _fetch_fibonacci(fs_ip, fs_port, number)
        except (ConnectionError, LookupError, OSError) as exc:
            self._send_text(502, f"Bad Gateway: {exc}\n")
            return

        self._send_bytes(200, result)

    def log_message(self, format_string: str, *args: object) -> None:
        print(f"US: {self.address_string()} - {format_string % args}")


def main() -> None:
    with ThreadedHTTPServer((HOST, PORT), UserHandler) as server:
        print(f"US listening on HTTP {HOST}:{PORT}")
        server.serve_forever()


if __name__ == "__main__":
    main()

