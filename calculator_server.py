#!/usr/bin/env python3
"""A small raw-socket HTTP/1.1 persistent-connection calculator."""

import argparse
import socket
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlsplit


MAX_HEADER_BYTES = 64 * 1024
MAX_BODY_BYTES = 1024 * 1024


class BadRequest(Exception):
    """The request is complete but violates the HTTP/calculator contract."""


def parse_request(buffer):
    """Return (request, bytes_used), or None when more bytes are needed."""
    header_end = buffer.find(b"\r\n\r\n")
    if header_end == -1:
        if len(buffer) > MAX_HEADER_BYTES:
            raise BadRequest("headers too large")
        return None

    header_block = bytes(buffer[:header_end])
    lines = header_block.split(b"\r\n")
    try:
        request_line = lines[0].decode("ascii")
    except UnicodeDecodeError as exc:
        raise BadRequest("request line is not ASCII") from exc

    parts = request_line.split(" ")
    if len(parts) != 3:
        raise BadRequest("malformed request line")
    method, target, version = parts
    if version != "HTTP/1.1":
        raise BadRequest("only HTTP/1.1 is supported")

    headers = {}
    for raw_line in lines[1:]:
        if b":" not in raw_line:
            raise BadRequest("malformed header")
        name, value = raw_line.split(b":", 1)
        try:
            name = name.decode("ascii").strip().lower()
            value = value.decode("iso-8859-1").strip()
        except UnicodeDecodeError as exc:
            raise BadRequest("malformed header encoding") from exc
        if not name or name in headers:
            raise BadRequest("duplicate or empty header")
        headers[name] = value

    content_length = headers.get("content-length", "0")
    try:
        body_length = int(content_length)
    except ValueError as exc:
        raise BadRequest("invalid Content-Length") from exc
    if body_length < 0 or body_length > MAX_BODY_BYTES:
        raise BadRequest("invalid Content-Length")

    total_length = header_end + 4 + body_length
    if len(buffer) < total_length:
        return None

    return {
        "method": method,
        "target": target,
        "headers": headers,
        "has_host": "host" in headers,
        "body": bytes(buffer[header_end + 4 : total_length]),
    }, total_length


def format_number(value):
    """Produce compact, non-exponential output for Decimal results."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def calculate(path, query):
    operations = {"/add": lambda a, b: a + b, "/sub": lambda a, b: a - b,
                  "/mul": lambda a, b: a * b, "/div": lambda a, b: a / b}
    if path not in operations:
        return 404, "Not Found\n"

    values = parse_qs(query, keep_blank_values=True)
    if len(values.get("a", [])) != 1 or len(values.get("b", [])) != 1:
        return 400, "a and b must be numeric query parameters\n"
    try:
        a = Decimal(values["a"][0])
        b = Decimal(values["b"][0])
        if not a.is_finite() or not b.is_finite():
            raise InvalidOperation
        result = operations[path](a, b)
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return 400, "invalid numeric parameters\n"
    return 200, format_number(result) + "\n"


def make_response(status, body):
    reasons = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed"}
    body_bytes = body.encode("utf-8")
    headers = [
        f"HTTP/1.1 {status} {reasons[status]}",
        "Content-Type: text/plain; charset=utf-8",
        f"Content-Length: {len(body_bytes)}",
        "",
        "",
    ]
    return "\r\n".join(headers).encode("ascii") + body_bytes


def handle_request(request):
    if not request["has_host"]:
        return make_response(400, "Bad Request: missing Host header\n")

    method = request["method"]
    parsed_target = urlsplit(request["target"])
    if parsed_target.scheme or parsed_target.netloc:
        return make_response(400, "absolute-form targets are not supported\n")

    if method != "GET":
        if parsed_target.path in {"/add", "/sub", "/mul", "/div"}:
            return make_response(405, "Method Not Allowed\n")
        return make_response(404, "Not Found\n")

    status, body = calculate(parsed_target.path, parsed_target.query)
    return make_response(status, body)


def serve_connection(connection, address):
    print(f"accepted {address[0]}:{address[1]}", flush=True)
    buffer = bytearray()
    with connection:
        while True:
            try:
                request_info = parse_request(buffer)
            except BadRequest as exc:
                connection.sendall(make_response(400, f"Bad Request: {exc}\n"))
                return

            if request_info is not None:
                request, used = request_info
                del buffer[:used]
                connection.sendall(handle_request(request))
                continue

            data = connection.recv(4096)
            if not data:
                return
            buffer.extend(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((args.host, args.port))
        server.listen(5)
        print(f"listening on {args.host}:{args.port}", flush=True)
        while True:
            connection, address = server.accept()
            serve_connection(connection, address)


if __name__ == "__main__":
    main()