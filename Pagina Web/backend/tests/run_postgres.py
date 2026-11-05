"""Run the real PostgreSQL tests against a disposable local PostgreSQL 17 cluster.

No services or existing data directories are used. The server binds loopback
only, and owned processes are hidden on Windows and stopped in finally.
"""
import datetime
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

import psycopg

BACKEND = Path(__file__).parents[1]
BIN = Path(os.getenv("TICKIA_TEST_PG_BIN", "C:/Program Files/PostgreSQL/17/bin"))
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def run():
    for executable in ("initdb.exe", "postgres.exe", "pg_ctl.exe"):
        if not (BIN / executable).is_file():
            raise RuntimeError("PostgreSQL 17 test binaries are unavailable.")
    work = BACKEND / "test-results" / ("postgres-" + uuid.uuid4().hex)
    work.mkdir(parents=True)
    data = work / "data"
    password_file = work / "empty.pgpass"
    password_file.write_text("", encoding="utf-8")
    os.environ["PGPASSFILE"] = str(password_file)
    os.environ["PGSSLMODE"] = "disable"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    init = subprocess.run(
        [str(BIN / "initdb.exe"), "-D", str(data), "-A", "trust", "-U", "tickia",
         "--encoding=UTF8", "--no-locale"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=FLAGS, timeout=60,
    )
    (work / "initdb.log").write_bytes(init.stdout)
    if init.returncode:
        raise RuntimeError("Disposable initdb failed; see its dedicated test log.")
    server = None
    return_code = 1
    with (work / "postgres.log").open("wb") as log:
        try:
            server = subprocess.Popen(
                [str(BIN / "postgres.exe"), "-D", str(data), "-h", "127.0.0.1", "-p", str(port)],
                stdout=log, stderr=subprocess.STDOUT, creationflags=FLAGS,
            )
            deadline = time.monotonic() + 20
            while True:
                try:
                    with psycopg.connect(host="127.0.0.1", port=port, dbname="postgres", user="tickia", autocommit=True, connect_timeout=1, sslmode="disable") as db:
                        db.execute("CREATE DATABASE tickia_test")
                    break
                except psycopg.OperationalError:
                    if server.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("The disposable PostgreSQL server failed to start.")
                    time.sleep(0.2)
            env = dict(os.environ)
            env.update({
                "TICKIA_LOAD_ENV": "0", "ENVIRONMENT": "test", "DATABASE_URL": "sqlite://",
                "SECRET_KEY": "offline-postgres-cluster-tests-no-production-material",
                "TEST_POSTGRES_URL": "postgresql+psycopg://tickia@127.0.0.1:" + str(port) + "/tickia_test",
                "PYTHONUTF8": "1",
            })
            tests = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", str(BACKEND / "tests"), "-v"],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=FLAGS, timeout=90,
            )
            (BACKEND / "test-results" / "postgres-tests.txt").write_bytes(tests.stdout)
            sys.stdout.write(tests.stdout.decode("utf-8", errors="replace"))
            return_code = tests.returncode
        finally:
            if server is not None:
                stopped = subprocess.run(
                    [str(BIN / "pg_ctl.exe"), "-D", str(data), "-m", "fast", "-w", "stop"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=FLAGS, timeout=20,
                )
                (work / "shutdown.log").write_bytes(stopped.stdout)
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.terminate()
                    server.wait(timeout=10)
                    raise RuntimeError("Owned PostgreSQL process needed forced termination; review logs.")
                if stopped.returncode and return_code == 0:
                    raise RuntimeError("Review disposable cluster shutdown logs.")
    print("Disposable PostgreSQL stopped; test evidence:", BACKEND / "test-results" / "postgres-tests.txt")
    return return_code


if __name__ == "__main__":
    sys.exit(run())
