"""Arranca Tickia local: python Proyecto_PrograAvanzada/iniciar.py (Ctrl+C para cerrar)."""
import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "Pagina Web"
LOCAL = Path(os.getenv('TICKIA_LOCAL_DIR', str(Path(__file__).resolve().parent / '.local'))).resolve()


def wait_ready(process, url, timeout):
    deadline=time.monotonic()+timeout
    while process.poll() is None and time.monotonic()<deadline:
        try:
            with urllib.request.urlopen(url,timeout=2) as response:
                if response.status==200:
                    return
        except OSError:
            time.sleep(1)
    raise RuntimeError('Un servicio no pudo iniciar. Revisa los logs en '+str(LOCAL))


def main():
    if os.name == "nt":
        def interrupted(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGBREAK, interrupted)
    parser = argparse.ArgumentParser(description="Tickia con el dataset local, sin Supabase")
    parser.add_argument("--api-port", type=int, default=8001)
    parser.add_argument("--web-port", type=int, default=5174)
    parser.add_argument('--legacy-sqlite',action='store_true',help='Abrir la versión anterior de respaldo; no cumple la rúbrica MySQL.')
    args = parser.parse_args()
    if args.api_port == args.web_port or any(not 1024 <= port <= 65535 for port in (args.api_port, args.web_port)):
        parser.error("Usa dos puertos distintos entre 1024 y 65535.")
    for port in (args.api_port, args.web_port):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                parser.error(f"El puerto {port} ya está ocupado. Elige otro con --api-port o --web-port.")
    python = WEB / "backend" / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        python = Path(sys.executable)
    node = shutil.which("node")
    vite = WEB / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
    if not node or not vite.is_file():
        parser.error("Instala Node.js y ejecuta npm.cmd ci en 'Pagina Web/frontend'. Consulta COMO_EJECUTAR.md.")
    LOCAL.mkdir(exist_ok=True)
    env = dict(os.environ, TICKIA_DATA_MODE="dataset", ENVIRONMENT="development", TICKIA_LOAD_ENV="0",
               VITE_API_URL="/api", TICKIA_API_PROXY_TARGET=f"http://127.0.0.1:{args.api_port}", PYTHONUNBUFFERED="1",
               FRONTEND_PROD_URL=f"http://127.0.0.1:{args.web_port},http://localhost:{args.web_port}")
    if not args.legacy_sqlite:
        dependencies=subprocess.run([str(python),'-c','import pandas,pymysql'],cwd=WEB,env=env,capture_output=True)
        if dependencies.returncode:
            parser.error('Instala las dependencias: python -m pip install -r "Pagina Web/backend/requirements.txt"')
        if not env.get('TICKIA_ACADEMIC_MYSQL_URL'):
            docker=shutil.which('docker')
            if not docker:
                parser.error('MySQL requiere Docker Desktop en ejecución o TICKIA_ACADEMIC_MYSQL_URL configurada.')
            print('Preparando MySQL local (17 tablas normalizadas). La primera carga puede tardar unos minutos.',flush=True)
            prepared=subprocess.run([str(python),'-m','backend.academic.settings'],cwd=WEB,env=env,capture_output=True)
            if prepared.returncode:
                parser.error('No se pudo preparar la configuración local de MySQL.')
            started=subprocess.run([docker,'compose','--env-file',str(LOCAL/'mysql.env'),'-f',
                str(Path(__file__).resolve().parent/'compose.mysql.yml'),'up','-d','--wait','--wait-timeout','180','mysql'],cwd=ROOT,env=env)
            if started.returncode:
                parser.error('No se pudo iniciar MySQL. Abre Docker Desktop y vuelve a ejecutar el comando.')
    backend_module='backend.main:app' if args.legacy_sqlite else 'backend.academic.main:app'
    commands = [
        ("backend", [str(python), "-m", "uvicorn", backend_module, "--host", "127.0.0.1", "--port", str(args.api_port)], WEB),
        ("frontend", [node, str(vite), "--host", "127.0.0.1", "--port", str(args.web_port), "--strictPort"], WEB / "frontend"),
    ]
    processes, logs = [], []
    try:
        for name, command, cwd in commands:
            log = (LOCAL / f"{name}.log").open("w", encoding="utf-8")
            logs.append(log)
            processes.append(subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
            wait_ready(processes[-1],f'http://127.0.0.1:{args.api_port}/ready' if name=='backend'
                       else f'http://127.0.0.1:{args.web_port}/',300 if name=='backend' else 60)
        print(f"Tickia local: http://127.0.0.1:{args.web_port}", flush=True)
        print('Motor: '+('SQLite de respaldo' if args.legacy_sqlite else 'MySQL · 17 tablas normalizadas · 15 CSV originales')+'.',flush=True)
        print('Logs: '+str(LOCAL),flush=True)
        print("Pulsa Ctrl+C para cerrar ambos servicios.", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(1)
        failed = next(process.returncode for process in processes if process.returncode is not None)
        print("Un servicio terminó. Revisa backend.log y frontend.log.", file=sys.stderr)
        return failed or 1
    except KeyboardInterrupt:
        return 0
    except RuntimeError as error:
        print(str(error),file=sys.stderr)
        return 1
    finally:
        for process in processes:
            if process.poll() is None:
                if os.name == "nt":
                    # El ejecutable del venv puede crear otro python.exe: cerrar todo el árbol.
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    sys.exit(main())
