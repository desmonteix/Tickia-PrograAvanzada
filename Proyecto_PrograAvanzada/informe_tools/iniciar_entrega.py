"""Lanzador portable del ZIP de entrega, con MySQL y puertos independientes."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys


IMAGE = 'mysql:8.4@sha256:a81d043930e51745522bd5c430961cf8286f0a23f0a9a2a6e0108f7ea71b0902'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mysql-port', type=int, default=3308)
    parser.add_argument('--api-port', type=int, default=8002)
    parser.add_argument('--web-port', type=int, default=5175)
    parser.add_argument('--project', default='tickia-entrega')
    parser.add_argument('--solo-bd', action='store_true', help='Restaurar o comprobar MySQL sin abrir la web.')
    args = parser.parse_args()
    ports = (args.mysql_port, args.api_port, args.web_port)
    if len(set(ports)) != 3 or any(not 1024 <= p <= 65535 for p in ports):
        parser.error('Se requieren tres puertos distintos entre 1024 y 65535.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,40}', args.project):
        parser.error('Nombre de proyecto Docker no válido.')
    root = Path(__file__).resolve().parent
    sources = root / 'codigo_fuente'
    backup = root / 'respaldo/tickia_universidad_completa.sql'
    if not (sources / 'Proyecto_PrograAvanzada/iniciar.py').is_file() or not backup.is_file():
        parser.error('Ejecuta este archivo desde la raíz del ZIP extraído, junto a codigo_fuente y respaldo.')
    docker = shutil.which('docker')
    if not docker: parser.error('Instala Docker Desktop y abre el motor de contenedores Linux.')
    local = root / '.entrega_config'; local.mkdir(exist_ok=True)
    env_file = local / 'mysql.env'
    try:
        with env_file.open('x', encoding='utf-8') as stream:
            stream.write('MYSQL_DATABASE=tickia_universidad\nMYSQL_USER=tickia\nMYSQL_PASSWORD='+secrets.token_urlsafe(24)+
                         '\nMYSQL_ROOT_PASSWORD='+secrets.token_urlsafe(32)+'\n')
    except FileExistsError: pass
    values = dict(line.split('=', 1) for line in env_file.read_text(encoding='utf-8').splitlines() if '=' in line)
    compose = local / 'compose.entrega.yml'
    compose.write_text(f'''services:
  mysql:
    image: {IMAGE}
    command: ['--log-bin-trust-function-creators=ON']
    environment:
      MYSQL_DATABASE: ${{MYSQL_DATABASE:?}}
      MYSQL_USER: ${{MYSQL_USER:?}}
      MYSQL_PASSWORD: ${{MYSQL_PASSWORD:?}}
      MYSQL_ROOT_PASSWORD: ${{MYSQL_ROOT_PASSWORD:?}}
    ports:
      - '127.0.0.1:{args.mysql_port}:3306'
    volumes:
      - mysql-data:/var/lib/mysql
    healthcheck:
      test: ['CMD-SHELL', 'MYSQL_PWD="$$MYSQL_PASSWORD" mysqladmin ping -h 127.0.0.1 -u $$MYSQL_USER --silent']
      interval: 5s
      timeout: 5s
      retries: 30
volumes:
  mysql-data:
''', encoding='utf-8')
    command = [docker, 'compose', '-p', args.project, '--env-file', str(env_file), '-f', str(compose)]
    subprocess.run(command + ['up', '-d', '--wait', '--wait-timeout', '180', 'mysql'], check=True)
    # Las contraseñas se expanden dentro del contenedor, no en la línea de comandos local.
    client = command + ['exec', '-T', 'mysql', 'sh', '-c', 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot "$@"', 'sh']
    result = subprocess.run(client + ['--batch', '--skip-column-names', '-e',
        "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='tickia_universidad' AND TABLE_TYPE='BASE TABLE'"],
        capture_output=True, text=True, check=True)
    count = int(result.stdout.strip())
    if count == 0:
        print('Restaurando la copia completa de entrega...', flush=True)
        with backup.open('rb') as stream: subprocess.run(client, stdin=stream, check=True)
    elif count != 17:
        raise RuntimeError('La base existente no tiene las 17 tablas esperadas. No se sobrescribió. Usa otro --project y --mysql-port.')
    else: print('La base ya contiene las 17 tablas: se conserva su estado actual.', flush=True)
    (local / 'puertos.json').write_text(json.dumps(dict(mysql=args.mysql_port, api=args.api_port, web=args.web_port,
                                                    project=args.project)), encoding='utf-8')
    print('MySQL listo. Los datos se conservan en el volumen del proyecto '+args.project+'.', flush=True)
    if args.solo_bd: return
    python = sources / 'Pagina Web/backend/venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file(): parser.error('Crea el entorno virtual e instala las dependencias indicadas en README_ENTREGA.md.')
    from urllib.parse import quote
    password = quote(values['MYSQL_PASSWORD'], safe='')
    env = dict(os.environ, TICKIA_ACADEMIC_MYSQL_URL=f'mysql+pymysql://tickia:{password}@127.0.0.1:{args.mysql_port}/tickia_universidad?charset=utf8mb4',
               TICKIA_LOCAL_DIR=str(local / 'app'), TICKIA_LOAD_ENV='0')
    child = subprocess.Popen([str(python), str(sources / 'Proyecto_PrograAvanzada/iniciar.py'),
                              '--api-port', str(args.api_port), '--web-port', str(args.web_port)], cwd=sources, env=env)
    try: return child.wait()
    except KeyboardInterrupt:
        # El mismo Ctrl+C llega al lanzador hijo, que cierra API y frontend.
        try: return child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.terminate(); return child.wait(timeout=10)


if __name__ == '__main__':
    try: sys.exit(main())
    except (subprocess.CalledProcessError, RuntimeError) as error:
        print('No se pudo iniciar la entrega:', error, file=sys.stderr); sys.exit(1)
