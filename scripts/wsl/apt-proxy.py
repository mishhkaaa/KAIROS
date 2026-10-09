"""A forward proxy on Windows for the kairos-os distro's apt, run only while provisioning.

Some networks (VPNs, hotspots) drop large packets on WSL's NAT path: connections open, then big responses and TLS
handshakes stall. Windows itself downloads fine, so apt goes through Windows: plain GETs are relayed, HTTPS is tunnelled
(CONNECT). It listens only on the WSL host address, and install-kairos-os.ps1 stops it when provisioning is done.

    uv run python scripts/wsl/apt-proxy.py 172.19.208.1 3142
"""
from __future__ import annotations

import http.server
import select
import socket
import sys
import urllib.parse

HOP = {"proxy-connection", "connection", "keep-alive", "proxy-authorization"}


class Relay(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("apt-proxy " + fmt % args + "\n")

    def _pipe(self, upstream: socket.socket) -> None:
        conns = [self.connection, upstream]
        try:
            while True:
                ready, _, broken = select.select(conns, [], conns, 120)
                if broken or not ready:
                    return
                for s in ready:
                    data = s.recv(65536)
                    if not data:
                        return
                    (upstream if s is self.connection else self.connection).sendall(data)
        except OSError:
            return
        finally:
            upstream.close()

    def do_CONNECT(self) -> None:
        host, _, port = self.path.rpartition(":")
        try:
            upstream = socket.create_connection((host, int(port or 443)), timeout=30)
        except OSError as e:
            self.send_error(502, str(e))
            return
        self.send_response(200, "Connection established")
        self.end_headers()
        self._pipe(upstream)
        self.close_connection = True

    def _forward(self) -> None:
        url = urllib.parse.urlsplit(self.path)
        if url.scheme != "http" or not url.hostname:
            self.send_error(400, "absolute http:// URLs only")
            return
        try:
            upstream = socket.create_connection((url.hostname, url.port or 80), timeout=30)
        except OSError as e:
            self.send_error(502, str(e))
            return
        target = (url.path or "/") + (f"?{url.query}" if url.query else "")
        head = [f"{self.command} {target} HTTP/1.1"]
        head += [f"{k}: {v}" for k, v in self.headers.items() if k.lower() not in HOP]
        head.append("Connection: close")
        upstream.sendall(("\r\n".join(head) + "\r\n\r\n").encode("latin-1"))
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            upstream.sendall(self.rfile.read(length))
        # One request per connection: relay the response until the server closes.
        try:
            while chunk := upstream.recv(65536):
                self.connection.sendall(chunk)
        except OSError:
            pass
        finally:
            upstream.close()
        self.close_connection = True

    do_GET = do_HEAD = do_POST = _forward


def main() -> None:
    host, port = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3142
    server = http.server.ThreadingHTTPServer((host, port), Relay)
    server.daemon_threads = True
    print(f"apt-proxy on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
