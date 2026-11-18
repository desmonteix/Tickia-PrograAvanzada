"""Exporta el respaldo de entrega y demuestra su restauración en otro MySQL temporal."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
LOCAL=ROOT/'Proyecto_PrograAvanzada/.local/informe-build'
OUT=ROOT/'Proyecto_PrograAvanzada/entregables/informe'
PACKAGE=ROOT/'Proyecto_PrograAvanzada/.local/entrega_final/Tickia_PrograAvanzada'
SOURCE_DB='tickia_universidad_clean_test'
TARGET_DB='tickia_universidad'
IMAGE='mysql:8.4@sha256:a81d043930e51745522bd5c430961cf8286f0a23f0a9a2a6e0108f7ea71b0902'
sys.path.insert(0,str(ROOT/'Pagina Web'))


def sql(container,statement,check=True):
    return subprocess.run(['docker','exec','-i',container,'sh','-c',
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot --batch --raw --skip-column-names'],input=statement,text=True,capture_output=True,encoding='utf-8',check=check)


def run():
    from backend.academic.database import engine,make_engine,rows,row
    release=make_engine(engine.url.set(database=SOURCE_DB))
    with release.connect() as db:
        accounts=rows(db,'SELECT email FROM usuarios WHERE auth_uuid IS NOT NULL ORDER BY email')
        assert {a['email'] for a in accounts}=={'vendedor.campus@example.com','papeleria.demo@example.com','comprador.demo@example.com'},'La entrega debe contener solo las tres cuentas ficticias.'
        tables=[r['TABLE_NAME'] for r in rows(db,"SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")]
        counts={name:row(db,'SELECT COUNT(*) n FROM `'+name+'`')['n'] for name in tables}
        schema=rows(db,'''SELECT TABLE_NAME tabla,COLUMN_NAME columna,COLUMN_TYPE tipo,IS_NULLABLE permite_null,COLUMN_KEY clave
            FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN
            (SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE')
            ORDER BY TABLE_NAME,ORDINAL_POSITION''')
        version=row(db,'SELECT VERSION() version')['version']
    backup_dir=PACKAGE/'respaldo';backup_dir.mkdir(parents=True,exist_ok=True)
    backup=backup_dir/'tickia_universidad_completa.sql'
    raw=LOCAL/'respaldo-original.sql'
    with raw.open('wb') as stream:
        subprocess.run(['docker','exec','tickia-universidad-mysql-1','sh','-c',
            f'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --routines --triggers --set-gtid-purged=OFF --no-tablespaces --databases {SOURCE_DB}'],stdout=stream,check=True)
    content=raw.read_bytes().replace(('`'+SOURCE_DB+'`').encode(),('`'+TARGET_DB+'`').encode())
    content=re.sub(rb'DEFINER\s*=\s*`[^`]+`@`[^`]+`\s*',b'',content)
    backup.write_bytes(content)
    print('Respaldo completo exportado:',round(backup.stat().st_size/1024/1024,2),'MB.',flush=True)
    combined='-- Tickia: creación de estructura y objetos. Ejecutar sobre una base nueva.\nSET NAMES utf8mb4;\nCREATE DATABASE IF NOT EXISTS tickia_universidad CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;\nUSE tickia_universidad;\n\n'
    scripts=ROOT/'Proyecto_PrograAvanzada/sql'
    for name in ('01_esquema.sql','05_indices.sql','04_vistas.sql'):
        combined+='\n-- Archivo: '+name+'\n'+(scripts/name).read_text(encoding='utf-8')+'\n'
    for name,drop in [('02_procedimientos.sql','DROP PROCEDURE IF EXISTS confirmar_pedido;'),('06_trigger.sql','DROP TRIGGER IF EXISTS tr_pedido_validar_estado;')]:
        combined+='\n-- Archivo: '+name+'\n'+drop+'\nDELIMITER $$\n'+(scripts/name).read_text(encoding='utf-8').rstrip()+'$$\nDELIMITER ;\n'
    (OUT/'SQL_estructura_objetos.sql').write_text(combined,encoding='utf-8')
    metadata=dict(generated_at=datetime.now(timezone.utc).isoformat(),mysql=version,database=TARGET_DB,
        source_database=SOURCE_DB,counts=counts,rows=sum(counts.values()),tables=len(tables),views=3,foreign_keys=22,
        stored_procedures=1,triggers=1,demo_accounts=3,original_orders=111016,demo_orders=1,
        backup_file=backup.name,backup_bytes=backup.stat().st_size,backup_sha256=hashlib.sha256(content).hexdigest(),
        definer_removed_for_portability=True,contains_personal_work_accounts=False)
    (LOCAL/'diccionario_bd.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2),encoding='utf-8')
    name='tickia-informe-restore-'+secrets.token_hex(4)
    root_password=secrets.token_urlsafe(32)
    envfile=LOCAL/'restore.env';envfile.write_text('MYSQL_ROOT_PASSWORD='+root_password+'\n',encoding='utf-8')
    container=subprocess.run(['docker','run','--rm','--name',name,'--env-file',str(envfile),'-p','127.0.0.1::3306','-d',IMAGE,
        '--log-bin-trust-function-creators=ON'],capture_output=True,text=True,check=True).stdout.strip()
    (LOCAL/'restore-process.json').write_text(json.dumps(dict(id=container,name=name)))
    try:
        for _ in range(120):
            ready=subprocess.run(['docker','exec',container,'sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqladmin ping -h127.0.0.1 -uroot --silent'],capture_output=True)
            if ready.returncode==0:break
            time.sleep(1)
        else:raise RuntimeError('El MySQL temporal no inició.')
        print('Restaurando en un contenedor temporal independiente...',flush=True)
        with backup.open('rb') as stream:
            restored=subprocess.run(['docker','exec','-i',container,'sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot'],stdin=stream,capture_output=True)
        if restored.returncode:raise RuntimeError(restored.stderr.decode('utf-8',errors='replace')[:2500])
        restored_counts={}
        for table in tables:
            restored_counts[table]=int(sql(container,f'SELECT COUNT(*) FROM {TARGET_DB}.`{table}`;').stdout.strip())
        assert restored_counts==counts,(counts,restored_counts)
        actual={
          'views':int(sql(container,f"SELECT COUNT(*) FROM information_schema.VIEWS WHERE TABLE_SCHEMA='{TARGET_DB}';").stdout.strip()),
          'foreign_keys':int(sql(container,f"SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA='{TARGET_DB}';").stdout.strip()),
          'stored_procedures':int(sql(container,f"SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA='{TARGET_DB}' AND ROUTINE_TYPE='PROCEDURE';").stdout.strip()),
          'triggers':int(sql(container,f"SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='{TARGET_DB}';").stdout.strip())}
        assert actual==dict(views=3,foreign_keys=22,stored_procedures=1,triggers=1),actual
        order=int(sql(container,f"SELECT id_pedido FROM {TARGET_DB}.pedidos WHERE estado='pagado' ORDER BY id_pedido LIMIT 1;").stdout.strip())
        invalid=sql(container,f"USE {TARGET_DB}; START TRANSACTION; UPDATE pedidos SET estado='entregado' WHERE id_pedido={order}; ROLLBACK;",check=False)
        assert invalid.returncode!=0 and 'Transicion' in invalid.stderr,invalid.stderr
        metadata['restore_validation']=dict(success=True,container_isolated=True,counts=restored_counts,objects=actual,trigger_rejected_invalid_transition=True)
        port=int(subprocess.run(['docker','port',container,'3306/tcp'],capture_output=True,text=True,check=True).stdout.strip().rsplit(':',1)[1])
        from sqlalchemy import URL
        from unittest.mock import patch
        from backend.academic import bootstrap,schema_upgrade,auth,catalog,commerce,social
        from backend.academic.database import get_db
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        restored_engine=make_engine(URL.create('mysql+pymysql',username='root',password=root_password,host='127.0.0.1',port=port,database=TARGET_DB))
        checkdir=LOCAL/'restore-check';checkdir.mkdir(exist_ok=True)
        with patch.object(bootstrap,'LOCAL_DIR',checkdir),patch.object(schema_upgrade,'LOCAL_DIR',checkdir):
            bootstrap.initialize(restored_engine)
        app=FastAPI()
        for router in (auth.router,catalog.router,commerce.router,social.router):app.include_router(router)
        def connection():
            with restored_engine.begin() as db:yield db
        app.dependency_overrides[get_db]=connection
        with patch.object(commerce,'engine',restored_engine),TestClient(app) as client:
            logged=client.post('/api/auth/login',data=dict(username='comprador.demo@example.com',password='TickiaDemo2026!'))
            assert logged.status_code==200
            history=client.get('/api/marketplace/orders').json()
            assert history['total']==1 and history['items'][0]['estado']=='entregado'
            assert history['items'][0]['total_centimos']==27867
            assert client.get('/api/marketplace/products?page_size=1').json()['total']==counts['productos']
        metadata['restore_validation']['application_bootstrap_succeeded']=True
        metadata['restore_validation']['demo_login_and_order_verified']=True
        restored_engine.dispose()
        print('Restauración verificada:',sum(restored_counts.values()),'filas;',len(tables),'tablas y todos los objetos.',flush=True)
    finally:
        # Solo el contenedor recién creado y registrado por este proceso.
        subprocess.run(['docker','stop',container],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    (backup_dir/'validacion_respaldo.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (LOCAL/'respaldo_manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':run()
