#!/usr/bin/env python3
"""Fibonacci HTTP server for DCN Lab 3."""

from __future__ import annotations

import json
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlsplit


HOST = os.getenv("FS_HOST", "0.0.0.0")
PORT = int(os.getenv("FS_PORT", "9090"))
UDP_TIMEOUT = float(os.getenv("FS_UDP_TIMEOUT", "3"))


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


def _fibonacci(number: int) -> int:
    if number < 0:
        raise ValueError("number must be non-negative")
    first, second = 0, 1
    for _ in range(number):
        first, second = second, first + second
    return first


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


def _register_with_as(payload: dict[str, object]) -> None:
    hostname = str(payload["hostname"])
    ip = str(payload["ip"])
    as_ip = str(payload["as_ip"])
    as_port = _port(str(payload["as_port"]))
    message = f"TYPE=A\nNAME={hostname} VALUE={ip} TTL=10\n"
    response = _udp_exchange(as_ip, as_port, message).strip()
    if response != "OK":
        raise ConnectionError(f"AS rejected registration: {response or '<empty>'}")


class FibonacciHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_text(self, status: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def do_PUT(self) -> None:  # noqa: N802
        if urlsplit(self.path).path != "/register":
            self._send_text(404, "Not Found\n")
            return

        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if length < 0:
                raise ValueError("Content-Length is required")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object")
            required = {"hostname", "ip", "as_ip", "as_port"}
            if not required.issubset(payload):
                raise ValueError(f"JSON must contain {sorted(required)}")
            _register_with_as(payload)
        except (ValueError, TypeError, json.JSONDecodeError, ConnectionError, OSError) as exc:
            self._send_text(400, f"Bad Request: {exc}\n")
            return

        self._send_text(201, "Registered\n")

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
            number = int(_single_query_value(query, "number"))
            result = _fibonacci(number)
        except (ValueError, TypeError):
            self._send_text(400, "Bad Request\n")
            return

        self._send_text(200, f"{result}\n")

    def log_message(self, format_string: str, *args: object) -> None:
        print(f"FS: {self.address_string()} - {format_string % args}")


def main() -> None:
    with ThreadedHTTPServer((HOST, PORT), FibonacciHandler) as server:
        print(f"FS listening on HTTP {HOST}:{PORT}")
        server.serve_forever()


if __name__ == "__main__":
    main()

