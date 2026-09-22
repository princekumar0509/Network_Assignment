#!/usr/bin/env python3
"""End-to-end test: all cases use one persistent TCP connection."""

import socket
import subprocess
import sys
import time


HOST = "127.0.0.1"
PORT = 18080


CASES = [
    ("GET /add?a=2&b=3 HTTP/1.1\r\nHost: localhost\r\n\r\n", 200, b"5\n"),
    ("GET /sub?a=10&b=4 HTTP/1.1\r\nHost: localhost\r\n\r\n", 200, b"6\n"),
    ("GET /mul?a=6&b=7 HTTP/1.1\r\nHost: localhost\r\n\r\n", 200, b"42\n"),
    ("GET /div?a=9&b=2 HTTP/1.1\r\nHost: localhost\r\n\r\n", 200, b"4.5\n"),
    ("GET /div?a=1&b=0 HTTP/1.1\r\nHost: localhost\r\n\r\n", 400, b"invalid numeric parameters\n"),
    ("GET /add?a=x&b=3 HTTP/1.1\r\nHost: localhost\r\n\r\n", 400, b"invalid numeric parameters\n"),
    ("GET /pow?a=2&b=8 HTTP/1.1\r\nHost: localhost\r\n\r\n", 404, b"Not Found\n"),
    ("POST /add HTTP/1.1\r\nHost: localhost\r\nContent-Length: 7\r\n\r\nignored", 405, b"Method Not Allowed\n"),
    ("GET /add?a=1&b=2 HTTP/1.1\r\n\r\n", 400, b"Bad Request: missing Host header\n"),
]


def read_response(sock):
    data = bytearray()
    while b"\r\n\r\n" not in data:
        data.extend(sock.recv(4096))
    header_end = data.index(b"\r\n\r\n") + 4
    headers = data[:header_end].decode("ascii").split("\r\n")
    status = int(headers[0].split(" ")[1])
    content_length = int(next(line.split(":", 1)[1] for line in headers if line.lower().startswith("content-length:")))
    while len(data) - header_end < content_length:
        data.extend(sock.recv(4096))
    return status, bytes(data[header_end : header_end + content_length])


def main():
    server = subprocess.Popen([sys.executable, "calculator_server.py", "--port", str(PORT)])
    try:
        for _ in range(50):
            try:
                sock = socket.create_connection((HOST, PORT), timeout=0.2)
                break
            except OSError:
                time.sleep(0.02)
        else:
            raise RuntimeError("server did not start")

        with sock:
            for number, (request, expected_status, expected_body) in enumerate(CASES, 1):
                sock.sendall(request.encode("ascii"))
                status, body = read_response(sock)
                assert (status, body) == (expected_status, expected_body), (number, status, body)
                print(f"request {number}: {status} {body!r}")

            sock.sendall(b"GET /add?a=4&b=5 HTTP/1.1\r\nHost: localhost\r\n\r\n")
            status, body = read_response(sock)
            assert (status, body) == (200, b"9\n")
            print("persistent connection check: 200 b'9\\n'")
    finally:
        server.terminate()
        server.wait(timeout=3)


if __name__ == "__main__":
    main()