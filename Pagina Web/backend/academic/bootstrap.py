"""Carga reproducible de los 15 CSV en MySQL. Los originales nunca se modifican."""
import csv
import hashlib
from itertools import islice
import json
import logging
from sqlalchemy import text
from ..dataset import SOURCE_DIR, LOCAL_DIR, TABLES as ORIGINAL_TABLES
from .settings import SQL_DIR
from .database import engine
from .schema_upgrade import upgrade_structure,install_read_models

logger = logging.getLogger(__name__)
TABLES = dict(ORIGINAL_TABLES)
TABLES['pagos'] = {'file': '10_pagos.csv', 'columns': 'id_pago id_pedido metodo monto estado'.split()}
TABLES['favoritos'] = {'file': '15_favoritos.csv', 'columns': 'id_usuario id_producto fecha'.split()}
TABLES = dict(sorted(TABLES.items(), key=lambda item: item[1]['file']))


def insert_districts(connection,records):
    """Descompone el CSV geográfico sin cambiar sus IDs ni nombres originales."""
    departments=sorted({record['departamento'] for record in records})
    connection.execute(text('INSERT IGNORE INTO departamentos(nombre) VALUES(:nombre)'),[{'nombre':value} for value in departments])
    department_ids=dict(connection.exec_driver_sql('SELECT nombre,id_departamento FROM departamentos').all())
    provinces=sorted({(department_ids[record['departamento']],record['provincia']) for record in records})
    connection.execute(text('INSERT IGNORE INTO provincias(id_departamento,nombre) VALUES(:department,:name)'),
                       [dict(department=department,name=name) for department,name in provinces])
    province_ids={(r.id_departamento,r.nombre):r.id_provincia for r in connection.exec_driver_sql('SELECT * FROM provincias')}
    connection.execute(text('INSERT INTO distritos(id_distrito,nombre,id_provincia) VALUES(:id,:name,:province)'),
        [dict(id=record['id_distrito'],name=record['nombre'],province=province_ids[department_ids[record['departamento']],record['provincia']]) for record in records])


def initialize(target=engine, source=SOURCE_DIR):
    manifest = []
    for table, spec in TABLES.items():
        path = source / spec['file']
        if not path.is_file():
            raise RuntimeError('Falta el archivo ' + spec['file'])
        manifest.append({'table': table, 'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    marker = 'tickia-dataset-v1-' + hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:20]
    with target.connect() as connection:
        database = connection.execute(text('SELECT DATABASE()')).scalar_one()
        lock_name = 'tickia-seed:' + database
        if connection.execute(text('SELECT GET_LOCK(:name,30)'), {'name': lock_name}).scalar_one() != 1:
            raise RuntimeError('Otra importación está trabajando en esta BD. Intenta nuevamente.')
        connection.commit()
        try:
            for statement in (SQL_DIR / '01_esquema.sql').read_text(encoding='utf-8').split(';'):
                if statement.strip():
                    connection.exec_driver_sql(statement)
            connection.commit()
            upgrade_structure(connection)
            columns={record[0] for record in connection.execute(text("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='usuarios'"))}
            for name,definition in {'suspendido':'BOOLEAN NOT NULL DEFAULT FALSE','banned_until':'DATETIME NULL'}.items():
                if name not in columns:
                    connection.exec_driver_sql('ALTER TABLE usuarios ADD COLUMN '+name+' '+definition)
            connection.commit()
            stored_marker = connection.execute(text("SELECT TABLE_COMMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='productos'")).scalar_one()
            connection.commit()
            if stored_marker != marker:
                if connection.execute(text('SELECT COUNT(*) FROM productos')).scalar_one():
                    raise RuntimeError('La BD ya contiene datos de otro conjunto. No se sobrescribió nada.')
                connection.commit()
                with connection.begin():
                    for item in manifest:
                        table, count = item['table'], 0
                        spec = TABLES[table]
                        fields = ','.join('`' + column + '`' for column in spec['columns'])
                        placeholders = ','.join(':' + column for column in spec['columns'])
                        statement = text(f'INSERT INTO `{table}` ({fields}) VALUES ({placeholders})')
                        with (source / spec['file']).open(encoding='utf-8-sig', newline='') as stream:
                            reader = csv.DictReader(stream)
                            if reader.fieldnames != spec['columns']:
                                raise ValueError(spec['file'] + ': columnas inválidas')
                            while batch := list(islice(reader, 5000)):
                                if table=='distritos':
                                    insert_districts(connection,batch)
                                else:
                                    connection.execute(statement, [{key: value if value != '' else None for key, value in record.items()} for record in batch])
                                count += len(batch)
                        item['rows'] = count
                        logger.info('MySQL: %s (%s filas)', table, count)
                    connection.execute(text("UPDATE couriers SET estrategia=CASE MOD(id_courier,3) WHEN 1 THEN 'estandar' WHEN 2 THEN 'rapido' ELSE 'economico' END"))
                connection.exec_driver_sql("ALTER TABLE productos COMMENT='" + marker + "'")
                connection.commit()
            for item in manifest:
                item.setdefault('rows', connection.exec_driver_sql('SELECT COUNT(*) FROM `' + item['table'] + '`').scalar_one())
            connection.commit()
            install_read_models(connection)
            routine = connection.execute(text("SELECT ROUTINE_COMMENT FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=DATABASE() AND ROUTINE_NAME='confirmar_pedido'")).scalar()
            if routine != 'tickia-universidad-v3':
                connection.exec_driver_sql('DROP PROCEDURE IF EXISTS confirmar_pedido')
                raw = connection.connection.cursor()
                try:
                    raw.execute((SQL_DIR / '02_procedimientos.sql').read_text(encoding='utf-8'))
                finally:
                    raw.close()
            connection.commit()
            output = LOCAL_DIR / 'mysql-manifest.json'
            output.write_text(json.dumps({'database': database, 'tables': manifest}, ensure_ascii=False, indent=2), encoding='utf-8')
        finally:
            connection.execute(text('SELECT RELEASE_LOCK(:name)'), {'name': lock_name})
            connection.commit()
    return manifest


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    result = initialize()
    print(json.dumps({'tables': len(result), 'records': sum(item['rows'] for item in result)}, indent=2))
