"""Normalización aditiva y traslado verificado de columnas de la versión anterior."""
import json
import re
from sqlalchemy import text
from .database import row,rows
from .settings import LOCAL_DIR,SQL_DIR


def columns(db,table):
    return {record['COLUMN_NAME'] for record in rows(db,
        'SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:table',{'table':table})}


def upgrade_structure(db):
    geography=columns(db,'distritos')
    orders=columns(db,'pedidos')
    if 'provincia' in geography or 'destino' in orders:
        # Respaldo de los valores trasladados, sin contraseñas ni tokens.
        backup={}
        if 'provincia' in geography:
            backup['distritos']=rows(db,'SELECT * FROM distritos ORDER BY id_distrito')
        if 'destino' in orders:
            backup['pedidos']=rows(db,"SELECT id_pedido,subtotal,descuento,costo_envio,destino FROM pedidos WHERE origen='web' OR destino IS NOT NULL OR subtotal IS NOT NULL OR descuento<>0 OR costo_envio<>0")
        name=row(db,'SELECT DATABASE() nombre')['nombre']
        path=LOCAL_DIR/('pre-3fn-'+name+'.json')
        if not path.exists():
            path.write_text(json.dumps(backup,ensure_ascii=False,default=str,indent=2),encoding='utf-8')
        db.commit()
    if 'provincia' in geography:
        original=rows(db,'SELECT id_distrito,nombre,provincia,departamento FROM distritos ORDER BY id_distrito')
        if 'id_provincia' not in geography:
            db.exec_driver_sql('ALTER TABLE distritos ADD COLUMN id_provincia INT NULL')
        db.exec_driver_sql('INSERT IGNORE INTO departamentos(nombre) SELECT DISTINCT departamento FROM distritos ORDER BY departamento')
        db.exec_driver_sql('''INSERT IGNORE INTO provincias(id_departamento,nombre)
            SELECT DISTINCT de.id_departamento,d.provincia FROM distritos d
            JOIN departamentos de ON de.nombre=d.departamento ORDER BY de.id_departamento,d.provincia''')
        db.exec_driver_sql('''UPDATE distritos d JOIN departamentos de ON de.nombre=d.departamento
            JOIN provincias p ON p.id_departamento=de.id_departamento AND p.nombre=d.provincia
            SET d.id_provincia=p.id_provincia''')
        restored=rows(db,'''SELECT d.id_distrito,d.nombre,p.nombre provincia,de.nombre departamento
            FROM distritos d JOIN provincias p USING(id_provincia) JOIN departamentos de USING(id_departamento)
            ORDER BY d.id_distrito''')
        if original!=restored:
            db.rollback()
            raise RuntimeError('La normalización no reconstruye exactamente los distritos. Se conservaron las columnas originales.')
        db.commit()
        db.exec_driver_sql('''ALTER TABLE distritos MODIFY id_provincia INT NOT NULL,
            ADD CONSTRAINT fk_distrito_provincia FOREIGN KEY (id_provincia) REFERENCES provincias(id_provincia),
            DROP COLUMN provincia,DROP COLUMN departamento''')
        db.commit()
    if 'id_distrito_entrega' not in orders:
        db.exec_driver_sql('ALTER TABLE pedidos ADD COLUMN id_distrito_entrega INT NULL')
    if 'destino' in orders:
        db.exec_driver_sql("UPDATE pedidos SET id_distrito_entrega=CAST(JSON_UNQUOTE(JSON_EXTRACT(destino,'$.id_distrito')) AS UNSIGNED) WHERE destino IS NOT NULL")
        invalid=row(db,'''SELECT COUNT(*) n FROM pedidos pe LEFT JOIN distritos d ON pe.id_distrito_entrega=d.id_distrito
            WHERE pe.destino IS NOT NULL AND d.id_distrito IS NULL''')['n']
        mismatch=row(db,'''SELECT COUNT(*) n FROM pedidos pe
            LEFT JOIN (SELECT id_pedido,SUM(cantidad*precio_unit) subtotal FROM pedido_detalle GROUP BY id_pedido) li USING(id_pedido)
            LEFT JOIN (SELECT id_pedido,SUM(costo_envio) costo FROM envios GROUP BY id_pedido) en USING(id_pedido)
            WHERE pe.origen='web' AND ((pe.subtotal IS NOT NULL AND pe.subtotal<>li.subtotal)
              OR pe.costo_envio<>COALESCE(en.costo,0)
              OR pe.descuento<>COALESCE(li.subtotal,pe.total)+COALESCE(en.costo,0)-pe.total)''')['n']
        if invalid or mismatch:
            db.rollback()
            raise RuntimeError('Hay destinos o importes que requieren revisión. Se conservaron sus columnas y el respaldo local.')
        db.commit()
        # El CHECK de la versión anterior puede tener un nombre generado por MySQL.
        checks=rows(db,'''SELECT tc.CONSTRAINT_NAME,cc.CHECK_CLAUSE FROM information_schema.TABLE_CONSTRAINTS tc
            JOIN information_schema.CHECK_CONSTRAINTS cc ON tc.CONSTRAINT_SCHEMA=cc.CONSTRAINT_SCHEMA AND tc.CONSTRAINT_NAME=cc.CONSTRAINT_NAME
            WHERE tc.TABLE_SCHEMA=DATABASE() AND tc.TABLE_NAME='pedidos' AND tc.CONSTRAINT_TYPE='CHECK' ''')
        for check in checks:
            if any(name in check['CHECK_CLAUSE'] for name in ('descuento','costo_envio')):
                identifier=check['CONSTRAINT_NAME'].replace('`','``')
                db.exec_driver_sql('ALTER TABLE pedidos DROP CHECK `'+identifier+'`')
        db.exec_driver_sql('''ALTER TABLE pedidos
            ADD CONSTRAINT fk_pedido_distrito_entrega FOREIGN KEY (id_distrito_entrega) REFERENCES distritos(id_distrito),
            ADD CONSTRAINT chk_pedido_total CHECK(total>=0),
            DROP COLUMN subtotal,DROP COLUMN descuento,DROP COLUMN costo_envio,DROP COLUMN destino''')
        db.commit()


def install_read_models(db):
    for statement in (SQL_DIR/'04_vistas.sql').read_text(encoding='utf-8').split(';'):
        if statement.strip():
            db.exec_driver_sql(statement)
    present={(r['TABLE_NAME'],r['INDEX_NAME']) for r in rows(db,
        'SELECT TABLE_NAME,INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE()')}
    for statement in (SQL_DIR/'05_indices.sql').read_text(encoding='utf-8').split(';'):
        definition=re.search(r'CREATE INDEX (\w+) ON (\w+)',statement)
        if definition and (definition[2],definition[1]) not in present:
            db.exec_driver_sql(statement)
    db.exec_driver_sql('DROP TRIGGER IF EXISTS tr_pedido_validar_estado')
    db.exec_driver_sql((SQL_DIR/'06_trigger.sql').read_text(encoding='utf-8'))
    db.commit()
