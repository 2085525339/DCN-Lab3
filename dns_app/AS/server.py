#!/usr/bin/env python3
"""Simplified authoritative DNS server for DCN Lab 3."""

from __future__ import annotations

import json
import os
import re
import socketserver
import threading
from pathlib import Path


HOST = os.getenv("AS_HOST", "0.0.0.0")
PORT = int(os.getenv("AS_PORT", "53533"))
DATA_FILE = Path(os.getenv("AS_DATA_FILE", "records.json"))

_records: dict[str, dict[str, object]] = {}
_records_lock = threading.Lock()


def _load_records() -> None:
    global _records
    if not DATA_FILE.exists():
        return
    try:
        loaded = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            _records = loaded
    except (OSError, json.JSONDecodeError):
        print(f"Warning: could not load {DATA_FILE}; starting with empty records")


def _save_records() -> None:
    temporary = DATA_FILE.with_suffix(DATA_FILE.suffix + ".tmp")
    temporary.write_text(json.dumps(_records, indent=2), encoding="utf-8")
    temporary.replace(DATA_FILE)


def _parse_message(message: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in message.replace("\r\n", "\n").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("TYPE="):
            fields["TYPE"] = line.removeprefix("TYPE=").strip()
            continue

        name_match = re.fullmatch(
            r"NAME=(\S+)(?: VALUE=(\S+) TTL=(\d+))?", line
        )
        if name_match:
            fields["NAME"] = name_match.group(1)
            if name_match.group(2) is not None:
                fields["VALUE"] = name_match.group(2)
                fields["TTL"] = name_match.group(3)
            continue

        raise ValueError(f"Unsupported DNS line: {line}")

    return fields


def _handle_message(message: str) -> str:
    fields = _parse_message(message)
    if fields.get("TYPE") != "A" or not fields.get("NAME"):
        return "ERROR\n"

    name = fields["NAME"]
    if "VALUE" in fields:
        value = fields.get("VALUE", "")
        ttl_text = fields.get("TTL", "")
        if not value or not ttl_text:
            return "ERROR\n"
        try:
            ttl = int(ttl_text)
        except ValueError:
            return "ERROR\n"
        if ttl < 0:
            return "ERROR\n"

        with _records_lock:
            _records[name] = {
                "name": name,
                "value": value,
                "type": "A",
                "ttl": ttl,
            }
            _save_records()
        return "OK\n"

    with _records_lock:
        record = _records.get(name)
    if not record or record.get("type") != "A":
        return "ERROR\n"

    return (
        "TYPE=A\n"
        f"NAME={record['name']} VALUE={record['value']} TTL={record['ttl']}\n"
    )


class AuthoritativeUDPServer(socketserver.ThreadingUDPServer):
    allow_reuse_address = True
    daemon_threads = True


class DNSHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data, sock = self.request
        try:
            message = data.decode("utf-8")
            response = _handle_message(message)
        except (UnicodeDecodeError, ValueError, OSError) as exc:
            print(f"Invalid request from {self.client_address}: {exc}")
            response = "ERROR\n"
        sock.sendto(response.encode("utf-8"), self.client_address)


def main() -> None:
    _load_records()
    with AuthoritativeUDPServer((HOST, PORT), DNSHandler) as server:
        print(f"AS listening on UDP {HOST}:{PORT}")
        server.serve_forever()


if __name__ == "__main__":
    main()

