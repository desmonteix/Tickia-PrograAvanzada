"""Migración idempotente de la versión SQLite anterior. Abre el origen en solo lectura."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid
from sqlalchemy import text
from ..dataset import LOCAL_DIR
from .database import engine,row,rows


def migrate_legacy(target=engine,source=None,marker=None):
    source=Path(source or LOCAL_DIR/'tickia.sqlite3')
    if not source.is_file():
        return dict(users=0,products=0,orders=0)
    marker=Path(marker or LOCAL_DIR/('legacy-migrated-'+target.url.database+'.json'))
    if marker.is_file():
        return json.loads(marker.read_text(encoding='utf-8'))
    previous=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)
    previous.row_factory=sqlite3.Row
    counts=dict(users=0,products=0,orders=0)
    try:
        tables={record[0] for record in previous.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'users' not in tables:
            return counts
        with target.begin() as db:
            users={}
            for old in previous.execute('SELECT * FROM users'):
                identifier=str(uuid.UUID(old['id']))
                existing=row(db,'SELECT id_usuario FROM usuarios WHERE auth_uuid=:id',{'id':identifier})
                if not existing:
                    # Se agrega una cuenta operativa: nunca se toma una identidad del histórico.
                    result=db.execute(text('''INSERT INTO usuarios(id_distrito,nombre,email,fecha_registro,auth_uuid,password_hash,telefono,es_admin,suspendido,banned_until)
                        VALUES(1,:name,:email,DATE(CONVERT_TZ(UTC_TIMESTAMP(),'+00:00','-05:00')),:uuid,:password,:phone,:admin,:suspended,:banned)'''),
                        dict(name=old['full_name'] or old['email'].split('@')[0],email=old['email'],uuid=identifier,
                             password=old['hashed_password'],phone=old['phone_number'],admin=bool(old['is_admin']),
                             suspended=bool(old['is_suspended']),banned=old['banned_until']))
                    existing={'id_usuario':result.lastrowid}
                    counts['users']+=1
                users[old['id']]=existing['id_usuario']
            sellers={}
            if 'local_products' in tables:
                for old in previous.execute('SELECT * FROM local_products WHERE source_product_id IS NULL ORDER BY id_producto'):
                    owner=users.get(old['owner_id'])
                    if not owner:
                        raise RuntimeError('Una publicación local no tiene una cuenta propietaria migrable.')
                    if owner not in sellers:
                        existing=row(db,'SELECT id_vendedor FROM vendedores WHERE id_usuario=:id ORDER BY id_vendedor LIMIT 1',{'id':owner})
                        if not existing:
                            result=db.execute(text('INSERT INTO vendedores(id_usuario,razon_social,reputacion) VALUES(:user,:name,:rating)'),
                                dict(user=owner,name=old['vendedor'],rating=old['reputacion']))
                            existing={'id_vendedor':result.lastrowid}
                        sellers[owner]=existing['id_vendedor']
                    existing=row(db,'SELECT p.id_producto,s.id_usuario FROM productos p JOIN vendedores s USING(id_vendedor) WHERE p.id_producto=:id',{'id':old['id_producto']})
                    if existing and existing['id_usuario']!=owner:
                        raise RuntimeError('Un ID de publicación colisiona con otro producto. Se conservó SQLite intacto.')
                    if not existing:
                        db.execute(text('''INSERT INTO productos(id_producto,id_vendedor,id_categoria,titulo,precio,descripcion,imagen,origen)
                            VALUES(:id,:seller,:category,:title,:price,:description,:image,'web')'''),
                            dict(id=old['id_producto'],seller=sellers[owner],category=old['id_categoria'],title=old['titulo'],
                                 price=Decimal(old['precio_centimos'])/100,description=old['descripcion'],image=old['imagen']))
                        counts['products']+=1
                        for variant in previous.execute('SELECT * FROM local_variants WHERE id_producto=?',(old['id_producto'],)):
                            db.execute(text('INSERT INTO variantes(id_variante,id_producto,talla,color,stock) VALUES(:id_variante,:id_producto,:talla,:color,:stock)'),dict(variant))
            if 'local_variants' in tables:
                current={record['id_variante']:record['stock'] for record in rows(db,'SELECT id_variante,stock FROM variantes')}
                updates=[dict(id=record['id_variante'],stock=record['stock']) for record in previous.execute('SELECT id_variante,stock FROM local_variants')
                         if record['id_variante'] in current and current[record['id_variante']]!=record['stock']]
                if updates:
                    db.execute(text('UPDATE variantes SET stock=:stock WHERE id_variante=:id'),updates)
            if 'local_orders' in tables:
                for old in previous.execute('SELECT * FROM local_orders ORDER BY created_at'):
                    owner=users.get(old['buyer_id'])
                    request=str(uuid.UUID(old['request_id']))
                    if row(db,'SELECT id_pedido FROM pedidos WHERE id_usuario=:user AND solicitud_uuid=:request',dict(user=owner,request=request)):
                        continue
                    result=db.execute(text('''INSERT INTO pedidos(id_usuario,fecha,estado,total,subtotal,costo_envio,solicitud_uuid,solicitud_hash,origen)
                        VALUES(:user,:date,'pagado',:total,:total,0,:request,:hash,'web')'''),dict(user=owner,date=old['created_at'],
                        total=Decimal(old['total_centimos'])/100,request=request,hash=hashlib.sha256(('legacy:'+old['id']).encode()).hexdigest()))
                    identifier=result.lastrowid
                    db.execute(text('INSERT INTO pedido_detalle(id_pedido,id_variante,cantidad,precio_unit) VALUES(:order,:variant,:quantity,:price)'),
                        dict(order=identifier,variant=old['id_variante'],quantity=old['cantidad'],price=Decimal(old['precio_unit_centimos'])/100))
                    db.execute(text("INSERT INTO pagos(id_pedido,metodo,monto,estado,simulado,fecha) VALUES(:id,'legacy_demo',:total,'aprobado',TRUE,:date)"),
                               dict(id=identifier,total=Decimal(old['total_centimos'])/100,date=old['created_at']))
                    db.execute(text('INSERT INTO envios(id_pedido,id_courier,fecha_estimada,costo_envio) VALUES(:id,1,DATE_ADD(UTC_DATE(),INTERVAL 5 DAY),0)'),{'id':identifier})
                    counts['orders']+=1
        marker.write_text(json.dumps(counts,indent=2),encoding='utf-8')
    finally:
        previous.close()
    return counts
