"""Real Docker regression: frontend survives absent/replaced upstream DNS.

Run after building tickia-web and tickia-api. Uses only isolated test containers.
"""
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import uuid


def docker(*args, check=True):
    return subprocess.run(["docker", *args], check=check, capture_output=True,
                          text=True, timeout=60)


def eventually(check, description):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise AssertionError(description)


def main():
    suffix = uuid.uuid4().hex[:12]
    network, frontend, backend = (f"tickia-boot-{suffix}-{kind}" for kind in ("net", "web", "api"))
    secret = secrets.token_urlsafe(48)
    env = {**os.environ, "PROXY_SHARED_SECRET": secret}
    docker("network", "create", network)
    try:
        # An unset/malformed secret must stop the real image before nginx starts.
        invalid = docker("run", "--rm", "-e", "API_UPSTREAM=http://missing:8000",
                         "tickia-web", check=False)
        assert invalid.returncode != 0 and "PROXY_SHARED_SECRET" in invalid.stderr
        subprocess.run(
            ["docker", "run", "-d", "--name", frontend, "--network", network,
             "-p", "127.0.0.1::80", "-e", "PROXY_SHARED_SECRET",
             "-e", "API_UPSTREAM=http://late-api:8000", "tickia-web"],
            env=env, check=True, capture_output=True, text=True, timeout=60,
        )
        port = json.loads(docker("inspect", frontend).stdout)[0]["NetworkSettings"]["Ports"]["80/tcp"][0]["HostPort"]
        origin = f"http://127.0.0.1:{port}"

        def request(path):
            try:
                with urllib.request.urlopen(origin + path, timeout=5) as response:
                    return response.status, response.read(), response.headers
            except urllib.error.HTTPError as error:
                return error.code, error.read(), error.headers

        eventually(lambda: request("/")[0] == 200, "frontend did not start without backend DNS")
        assert request("/api/probe")[0] == 502
        assert request("/ready")[0] == 502
        fixture = '''
import hmac, json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"path": self.path, "proxy_authenticated": hmac.compare_digest(
            self.headers.get("X-Tickia-Proxy-Secret", ""), os.environ["PROXY_SHARED_SECRET"])}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", "session=fixture; HttpOnly; Secure; SameSite=Lax; Path=/")
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
'''
        def start_backend():
            subprocess.run(
                ["docker", "run", "-d", "--name", backend, "--network", network,
                 "--network-alias", "late-api", "-e", "PROXY_SHARED_SECRET", "--entrypoint", "python",
                 "tickia-api", "-c", fixture], env=env, check=True,
                capture_output=True, text=True, timeout=60,
            )

        start_backend()
        eventually(lambda: request("/ready")[0] == 200, "proxy did not recover when DNS appeared")
        path = "/api/probe?name=entrada%20general&limit=2"
        status, body, headers = request(path)
        assert status == 200 and json.loads(body) == {"path": path, "proxy_authenticated": True}
        assert "HttpOnly" in headers["Set-Cookie"]
        assert request("/health")[0] == 200
        docker("rm", "-f", backend)
        start_backend()
        eventually(lambda: request("/ready")[0] == 200, "proxy did not recover after backend replacement")
        print("Docker startup: missing secret rejected; absent DNS tolerated; API paths, query, cookie and authenticated forwarding preserved; backend replacement recovered.")
    finally:
        docker("rm", "-f", frontend, backend, check=False)
        docker("network", "rm", network, check=False)


if __name__ == "__main__":
    main()
