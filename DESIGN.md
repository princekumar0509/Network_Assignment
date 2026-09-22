# Persistent HTTP/1.1 Calculator

## Framing

`calculator_server.py` uses a byte buffer for each accepted TCP connection. TCP
does not preserve application-message boundaries, so the server first searches
for the HTTP header terminator, `CRLF CRLF`. It parses `Content-Length` as a
decimal byte count and waits until the buffer contains that many bytes after the
headers. Only then is one request removed from the buffer. Any remaining bytes
belong to the next request and remain buffered.

This means EOF is never used to decide where a request ends. The response also
includes `Content-Length`, allowing the test client to find the response body
without closing the connection. HTTP/1.1 persistence is therefore maintained
between requests.

## Deliberate limits

The server supports origin-form request targets and HTTP/1.1 only. It requires
`Host`, rejects duplicate headers and invalid lengths, and limits header/body
size to avoid unbounded buffering. Chunked transfer encoding and
`Connection: close` are left as stretch goals.

## Running

```text
python3 calculator_server.py --port 8080
python3 test_calculator.py
```

The test sends all required success and error scenarios over one socket, then
sends one additional request to prove that the connection is still open.