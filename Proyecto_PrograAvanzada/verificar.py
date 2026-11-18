"""Integración MySQL y navegador sin modificar la base de uso de la aplicación."""
import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT/'Pagina Web'
sys.path.insert(0,str(WEB))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sin-navegador',action='store_true')
    args=parser.parse_args()
    if not args.sin_navegador:
        for port in (8031,5201):
            with socket.socket() as check:
                try:
                    check.bind(('127.0.0.1',port))
                except OSError:
                    parser.error(f'El puerto de pruebas {port} está ocupado; cierra la instancia de pruebas anterior.')
    if os.getenv('TICKIA_ACADEMIC_MYSQL_URL') or os.getenv('TICKIA_LOCAL_DIR'):
        parser.error('Ejecutar sin overrides de MySQL/directorio local; este verificador usa Docker aislado.')
    from backend.academic.settings import mysql_env_file
    from backend.academic.database import engine
    docker=shutil.which('docker')
    if not docker:
        parser.error('Se requiere Docker Desktop en ejecución.')
    if not args.sin_navegador:
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError:
            parser.error('Instala Pagina Web/tests/requirements.txt y playwright install chromium.')
    subprocess.run([docker,'compose','--env-file',str(mysql_env_file()),'-f',
        str(ROOT/'Proyecto_PrograAvanzada/compose.mysql.yml'),'up','-d','--wait','--wait-timeout','180','mysql'],check=True)
    # Credencial root solo dentro del contenedor. La sentencia fija no toca la base de la app.
    sql="CREATE DATABASE IF NOT EXISTS tickia_universidad_test CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci; GRANT ALL PRIVILEGES ON tickia_universidad_test.* TO 'tickia'@'%';"
    subprocess.run([docker,'exec','-i','tickia-universidad-mysql-1','sh','-c',
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot'],input=sql,text=True,check=True)
    output=ROOT/'Proyecto_PrograAvanzada/.local'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tickia-academic-tests-') as temporary:
        env=dict(os.environ,TICKIA_TEST_MYSQL='1',TICKIA_LOCAL_DIR=temporary,
            TICKIA_ACADEMIC_MYSQL_URL=engine.url.set(database='tickia_universidad_test').render_as_string(hide_password=False))
        with (output/'mysql-tests.log').open('w',encoding='utf-8') as log:
            result=subprocess.run([sys.executable,'-m','unittest','discover','-s','backend/tests','-p',
                'test_academic_*.py','-v'],cwd=WEB,env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:
            print('Fallaron las pruebas MySQL. Revisa .local/mysql-tests.log.')
            return result.returncode
        print('Pruebas académicas, MySQL y generación NumPy: correctas. Detalle en .local/mysql-tests.log.',flush=True)
        if args.sin_navegador:
            return 0
        launcher=None
        with (output/'academic-e2e-launcher.log').open('w',encoding='utf-8') as log:
            try:
                launcher=subprocess.Popen([sys.executable,str(ROOT/'Proyecto_PrograAvanzada/iniciar.py'),
                    '--api-port','8031','--web-port','5201'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                for _ in range(180):
                    if launcher.poll() is not None:
                        raise RuntimeError('La instancia de pruebas no pudo iniciar; revisa academic-e2e-launcher.log.')
                    try:
                        with urlopen('http://127.0.0.1:5201/api/runtime',timeout=2) as response:
                            if response.status==200:
                                break
                    except (URLError,TimeoutError):
                        time.sleep(1)
                else:
                    raise RuntimeError('Tiempo de espera agotado al iniciar la instancia de pruebas.')
                env['TICKIA_ACADEMIC_URL']='http://127.0.0.1:5201'
                with (output/'academic-e2e.log').open('w',encoding='utf-8') as browser_log:
                    result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests/e2e','-p',
                        'test_academic_marketplace.py','-v'],cwd=WEB,env=env,stdout=browser_log,stderr=subprocess.STDOUT)
                print('Chromium: '+('recorrido completo correcto.' if result.returncode==0 else 'falló; revisa .local/academic-e2e.log.'))
                return result.returncode
            finally:
                if launcher is not None and launcher.poll() is None:
                    if os.name=='nt':
                        subprocess.run(['taskkill','/PID',str(launcher.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    else:
                        launcher.send_signal(signal.SIGINT)
                    launcher.wait(timeout=20)
                for name in ('backend','frontend'):
                    source=Path(temporary)/(name+'.log')
                    if source.is_file():
                        shutil.copyfile(source,output/('academic-test-'+name+'.log'))


if __name__=='__main__':
    sys.exit(main())
