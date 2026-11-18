"""Comprueba el ZIP en una extracción nueva, con dependencias ya instaladas.

La prueba usa puertos y proyecto Docker propios. No instala paquetes globales
ni copia claves del entorno de desarrollo. Los junctions de dependencias están
solo en la carpeta temporal extraída, que nunca se vuelve a empaquetar.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT/'Proyecto_PrograAvanzada/.local/informe-build'


def main():
    import httpx
    target = BUILD / ('prueba_zip_'+uuid.uuid4().hex[:8]); target.mkdir()
    package = ROOT/'Proyecto_PrograAvanzada/entregables/Entrega_Tickia_PrograAvanzada.zip'
    with zipfile.ZipFile(package) as archive:
        for item in archive.infolist():
            relative = Path(item.filename)
            assert not relative.is_absolute() and '..' not in relative.parts
        archive.extractall(target)
    delivery = target/'Tickia_PrograAvanzada'
    hashes = (delivery/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines()
    for line in hashes:
        checksum, name = line.split('  ', 1)
        assert hashlib.file_digest((delivery/name).open('rb'), 'sha256').hexdigest() == checksum
    print('Integridad SHA-256:',len(hashes),'archivos comprobados.',flush=True)
    source = delivery/'codigo_fuente'
    for name, dependency in [('Pagina Web/backend/venv', 'Pagina Web/backend/venv'),
                             ('Pagina Web/frontend/node_modules', 'Pagina Web/frontend/node_modules')]:
        location = source/name
        assert not location.exists()
        subprocess.run(['cmd','/c','mklink','/J',str(location),str(ROOT/dependency)],capture_output=True,check=True)
    docker_project = 'tickia-prueba-zip-'+uuid.uuid4().hex[:8]
    args = [sys.executable,str(delivery/'iniciar_entrega.py'),'--project',docker_project,
            '--mysql-port','3310','--api-port','8040','--web-port','5203']
    log = (target/'arranque.log').open('w',encoding='utf-8')
    process = subprocess.Popen(args,cwd=delivery,stdout=log,stderr=subprocess.STDOUT,
                               env=dict(os.environ,PYTHONUNBUFFERED='1'),creationflags=subprocess.CREATE_NO_WINDOW)
    result = dict(zip_sha256=hashlib.file_digest(package.open('rb'),'sha256').hexdigest(),
                  hashed_files=len(hashes), independent_docker_project=docker_project)
    try:
        print('Restaurando y abriendo la aplicación desde el ZIP extraído...',flush=True)
        deadline = time.monotonic()+300
        with httpx.Client(timeout=5,trust_env=False) as client:
            while time.monotonic()<deadline:
                if process.poll() is not None: raise RuntimeError('El lanzador terminó antes de abrir la aplicación. Revisar arranque.log.')
                try:
                    if client.get('http://127.0.0.1:8040/ready').status_code==200 and client.get('http://127.0.0.1:5203').status_code==200: break
                except httpx.HTTPError: pass
                time.sleep(1)
            else: raise RuntimeError('La copia no inició dentro de cinco minutos.')
            response = client.post('http://127.0.0.1:8040/api/auth/login',data=dict(username='comprador.demo@example.com',password='TickiaDemo2026!'))
            assert response.status_code==200
            orders = client.get('http://127.0.0.1:8040/api/marketplace/orders').json()
            assert orders['total']==1
            order = orders['items'][0]
            assert order['id_pedido']==111017 and order['total_centimos']==27867 and order['estado']=='entregado'
            assert client.get('http://127.0.0.1:8040/api/marketplace/products?page_size=1').json()['total']==9339
        print('Web, API, acceso y pedido restaurado: correctos.',flush=True)
        repeat = subprocess.run(args+['--solo-bd'],cwd=delivery,capture_output=True,text=True,encoding='utf-8',check=True)
        assert 'se conserva su estado actual' in repeat.stdout
        result.update(web_ready=True,api_ready=True,login_verified=True,order_verified=True,
                      repeat_did_not_reimport=True,source_csv_marker_accepted=True)
        (BUILD/'validacion_arranque_zip.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:
        # Solo el árbol iniciado por esta prueba; nunca se toca el lanzador cotidiano.
        if process.poll() is None:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        log.close()
        config = delivery/'.entrega_config'
        if (config/'compose.entrega.yml').is_file():
            subprocess.run(['docker','compose','-p',docker_project,'--env-file',str(config/'mysql.env'),
                            '-f',str(config/'compose.entrega.yml'),'stop'],capture_output=True,check=True)


if __name__ == '__main__': main()
