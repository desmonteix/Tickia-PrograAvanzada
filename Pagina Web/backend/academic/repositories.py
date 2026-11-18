"""Repositories: todo el SQL de catálogo, compras y análisis, con consultas parametrizadas."""
import pandas as pd
import pymysql
from sqlalchemy import text
from .database import row,rows


def placeholders(values):
    return ','.join(':id'+str(i) for i in range(len(values))),{'id'+str(i):value for i,value in enumerate(values)}


class CatalogRepository:
    def __init__(self,connection):
        self.db=connection

    def variants(self,identifiers):
        fields,params=placeholders(sorted(identifiers))
        return rows(self.db,'''SELECT va.id_variante,va.stock,va.talla,va.color,p.id_producto,p.titulo,p.precio,p.imagen,
            s.id_usuario owner FROM variantes va JOIN productos p USING(id_producto)
            JOIN vendedores s USING(id_vendedor) WHERE va.id_variante IN ('''+fields+')',params)

    def valid_coupon(self,code):
        return row(self.db,"SELECT * FROM cupones WHERE codigo=:code AND vence>=DATE(CONVERT_TZ(UTC_TIMESTAMP(),'+00:00','-05:00')) ORDER BY id_cupon LIMIT 1",{'code':code.strip()})

    def courier(self,identifier):
        return row(self.db,'SELECT * FROM couriers WHERE id_courier=:id',{'id':identifier})

    def district(self,identifier):
        return row(self.db,'SELECT * FROM v_distritos WHERE id_distrito=:id',{'id':identifier})


class OrderRepository:
    def __init__(self,connection):
        self.db=connection

    def find_by_request(self,user_id,request_id):
        return row(self.db,'SELECT id_pedido,solicitud_hash FROM pedidos WHERE id_usuario=:user AND solicitud_uuid=:request',
                   dict(user=user_id,request=str(request_id)))

    def receipt_records(self,identifiers):
        fields,params=placeholders(identifiers)
        orders=rows(self.db,'SELECT * FROM v_pedidos_importes WHERE id_pedido IN ('+fields+') ORDER BY fecha DESC,id_pedido DESC',params)
        details=rows(self.db,'''SELECT de.*,p.id_producto,p.titulo,s.razon_social vendedor,va.talla,va.color
            FROM pedido_detalle de JOIN variantes va USING(id_variante) JOIN productos p USING(id_producto)
            JOIN vendedores s USING(id_vendedor) WHERE de.id_pedido IN ('''+fields+') ORDER BY de.id_variante',params)
        payments=rows(self.db,'SELECT * FROM pagos WHERE id_pedido IN ('+fields+') ORDER BY id_pago',params)
        shipments=rows(self.db,'''SELECT e.*,c.nombre courier FROM envios e JOIN couriers c USING(id_courier)
            WHERE e.id_pedido IN ('''+fields+') ORDER BY e.id_envio',params)
        return orders,details,payments,shipments

    def accessible(self,user_id,order_id):
        return row(self.db,'''SELECT pe.* FROM pedidos pe WHERE pe.id_pedido=:id AND (pe.id_usuario=:user OR EXISTS(
            SELECT 1 FROM pedido_detalle de JOIN variantes va USING(id_variante) JOIN productos p USING(id_producto)
            JOIN vendedores s USING(id_vendedor) WHERE de.id_pedido=pe.id_pedido AND s.id_usuario=:user))''',
            dict(id=order_id,user=user_id))

    def history(self,user_id,seller,page):
        condition='''EXISTS(SELECT 1 FROM pedido_detalle de JOIN variantes va USING(id_variante)
            JOIN productos pr USING(id_producto) JOIN vendedores s USING(id_vendedor)
            WHERE de.id_pedido=p.id_pedido AND s.id_usuario=:user)''' if seller else 'p.id_usuario=:user'
        params=dict(user=user_id,offset=(page-1)*24)
        total=row(self.db,'SELECT COUNT(*) n FROM pedidos p WHERE '+condition,params)['n']
        identifiers=[r['id_pedido'] for r in rows(self.db,'SELECT p.id_pedido FROM pedidos p WHERE '+condition+
            ' ORDER BY p.fecha DESC,p.id_pedido DESC LIMIT 24 OFFSET :offset',params)]
        return identifiers,total

    def locked_state(self,order_id):
        return row(self.db,'SELECT estado FROM pedidos WHERE id_pedido=:id FOR UPDATE',{'id':order_id})['estado']

    def advance(self,order_id,state):
        field={'enviado':'fecha_envio','entregado':'fecha_entrega'}[state]
        self.db.execute(text('UPDATE pedidos SET estado=:state WHERE id_pedido=:id'),dict(state=state,id=order_id))
        self.db.execute(text('UPDATE envios SET '+field+'=UTC_TIMESTAMP() WHERE id_pedido=:id AND '+field+' IS NULL'),{'id':order_id})

    @staticmethod
    def confirm(target,arguments):
        """El procedimiento posee su transacción, separada de la conexión de lectura."""
        connection=target.raw_connection()
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute('CALL confirmar_pedido(%s,%s,%s,%s,%s,%s,%s,%s,%s)',arguments)
                outcome=cursor.fetchone()
                while cursor.nextset():
                    pass
            connection.commit()
            return outcome
        except pymysql.MySQLError:
            connection.rollback()
            raise
        finally:
            connection.close()


class ProductRepository:
    """Catálogo: productos, variantes, reseñas, preguntas y tablas de referencia."""
    CATALOG='''FROM productos p JOIN categorias c USING(id_categoria)
    JOIN vendedores s USING(id_vendedor) JOIN usuarios u ON s.id_usuario=u.id_usuario
    JOIN v_distritos d USING(id_distrito)
    LEFT JOIN (SELECT id_producto,SUM(stock) stock FROM variantes GROUP BY id_producto) inv USING(id_producto)
    LEFT JOIN (SELECT id_producto,AVG(estrellas) estrellas,COUNT(*) total_resenas FROM resenas GROUP BY id_producto) r USING(id_producto)'''
    FIELDS='''p.*,c.nombre categoria,s.razon_social vendedor,s.reputacion,u.auth_uuid owner_id,
    d.nombre distrito,d.provincia,COALESCE(inv.stock,0) stock,r.estrellas,COALESCE(r.total_resenas,0) total_resenas,
    EXISTS(SELECT 1 FROM favoritos f WHERE f.id_producto=p.id_producto AND f.id_usuario=:viewer) favorito'''
    ORDER={'id':'p.id_producto','price_asc':'p.precio,p.id_producto','price_desc':'p.precio DESC,p.id_producto',
           'rating':'s.reputacion DESC,p.id_producto','stock':'stock DESC,p.id_producto','newest':'p.id_producto DESC'}

    def __init__(self,connection):
        self.db=connection

    def search(self,viewer,q='',category=None,sort='id',in_stock=False,page=1,page_size=24,owned=False,favorites=False):
        conditions,params=[],{'viewer':viewer}
        if q.strip():
            conditions.append("LOCATE(:q,CONCAT_WS(' ',p.titulo,c.nombre,s.razon_social))>0")
            params['q']=q.strip()
        if category is not None:
            conditions.append('''p.id_categoria IN (WITH RECURSIVE ramas AS (
            SELECT id_categoria FROM categorias WHERE id_categoria=:category
            UNION ALL SELECT c.id_categoria FROM categorias c JOIN ramas r ON c.id_padre=r.id_categoria
        ) SELECT id_categoria FROM ramas)''')
            params['category']=category
        if in_stock:
            conditions.append('COALESCE(inv.stock,0)>0')
        if owned:
            conditions.append('s.id_usuario=:viewer')
        if favorites:
            conditions.append('EXISTS(SELECT 1 FROM favoritos f WHERE f.id_producto=p.id_producto AND f.id_usuario=:viewer)')
        where=' WHERE '+' AND '.join(conditions) if conditions else ''
        total=row(self.db,'SELECT COUNT(*) total '+self.CATALOG+where,params)['total']
        params.update(limit=page_size,offset=(page-1)*page_size)
        items=rows(self.db,'SELECT '+self.FIELDS+' '+self.CATALOG+where+' ORDER BY '+self.ORDER[sort]+' LIMIT :limit OFFSET :offset',params)
        return items,total

    def detail(self,product_id,viewer):
        return row(self.db,'SELECT '+self.FIELDS+' '+self.CATALOG+' WHERE p.id_producto=:id',dict(id=product_id,viewer=viewer))

    def variants(self,product_id):
        return rows(self.db,'SELECT * FROM variantes WHERE id_producto=:id ORDER BY id_variante',{'id':product_id})

    def latest_reviews(self,product_id):
        return rows(self.db,'''SELECT r.id_resena,r.estrellas,r.comentario,r.fecha,u.nombre autor FROM resenas r
        JOIN usuarios u USING(id_usuario) WHERE r.id_producto=:id ORDER BY r.fecha DESC,r.id_resena DESC LIMIT 10''',{'id':product_id})

    def latest_questions(self,product_id):
        return rows(self.db,'''SELECT p.id_pregunta,p.texto,p.respuesta,p.fecha,u.nombre autor FROM preguntas p
        JOIN usuarios u USING(id_usuario) WHERE p.id_producto=:id ORDER BY p.fecha DESC,p.id_pregunta DESC LIMIT 10''',{'id':product_id})

    def has_review(self,user_id,product_id):
        return bool(row(self.db,'SELECT 1 FROM resenas WHERE id_producto=:id AND id_usuario=:user LIMIT 1',dict(id=product_id,user=user_id)))

    def received(self,user_id,product_id):
        return bool(row(self.db,'''SELECT 1 FROM pedidos pe JOIN pedido_detalle de USING(id_pedido)
        JOIN variantes va USING(id_variante) WHERE pe.id_usuario=:user AND pe.estado='entregado' AND va.id_producto=:id LIMIT 1''',
            dict(user=user_id,id=product_id)))

    def categories(self):
        return rows(self.db,'''SELECT c.*,COUNT(p.id_producto) productos FROM categorias c LEFT JOIN productos p USING(id_categoria)
        GROUP BY c.id_categoria ORDER BY c.nombre,c.id_categoria''')

    def count(self,table):
        """`table` debe venir de la lista blanca TABLES o de los catálogos normalizados."""
        return row(self.db,'SELECT COUNT(*) n FROM `'+table+'`')['n']

    def table_page(self,table,columns,page,page_size):
        fields=','.join('`'+column+'`' for column in columns)
        order=','.join('`'+column+'`' for column in columns if column.startswith('id_'))
        source='v_distritos' if table=='distritos' else table
        return rows(self.db,'SELECT '+fields+' FROM `'+source+'` ORDER BY '+order+' LIMIT :limit OFFSET :offset',
                    dict(limit=page_size,offset=(page-1)*page_size))

    def districts(self):
        return rows(self.db,'SELECT * FROM v_distritos ORDER BY departamento,provincia,nombre')

    def couriers(self):
        return rows(self.db,'SELECT * FROM couriers ORDER BY id_courier')

    def active_coupons(self):
        return rows(self.db,"SELECT * FROM cupones WHERE vence>=DATE(CONVERT_TZ(UTC_TIMESTAMP(),'+00:00','-05:00')) ORDER BY vence,id_cupon LIMIT 30")


class AnalyticsRepository:
    """Análisis: devuelve DataFrames del histórico válido (origen dataset; pagado, enviado o entregado)."""
    VALID="pe.origen='dataset' AND pe.estado IN ('pagado','enviado','entregado')"

    def __init__(self,connection):
        self.db=connection

    def frame(self,sql,**options):
        return pd.read_sql_query(text(sql),self.db,**options)

    def orders(self):
        return self.frame('SELECT pe.id_pedido,pe.id_usuario,pe.fecha,CAST(ROUND(pe.total*100) AS SIGNED) total_centimos FROM pedidos pe WHERE '+self.VALID,parse_dates=['fecha'])

    def clients(self):
        return self.frame('SELECT id_usuario FROM usuarios WHERE auth_uuid IS NULL')

    def items(self):
        return self.frame('''SELECT de.id_pedido,va.id_producto,p.id_vendedor,p.titulo,de.cantidad,
        CAST(ROUND(de.precio_unit*100) AS SIGNED) precio_unit_centimos FROM pedido_detalle de
        JOIN variantes va USING(id_variante) JOIN productos p USING(id_producto) JOIN pedidos pe USING(id_pedido) WHERE '''+self.VALID)

    def shipments(self):
        return self.frame('''SELECT e.*,c.nombre courier,COALESCE(dest.departamento,d.departamento) departamento
        FROM envios e JOIN pedidos pe USING(id_pedido) JOIN couriers c USING(id_courier)
        JOIN usuarios u ON pe.id_usuario=u.id_usuario JOIN v_distritos d ON u.id_distrito=d.id_distrito
        LEFT JOIN v_distritos dest ON pe.id_distrito_entrega=dest.id_distrito WHERE '''+self.VALID)

    def reviews(self):
        return self.frame('''SELECT r.id_resena,r.id_producto,p.id_vendedor,r.estrellas,r.comentario FROM resenas r
        JOIN productos p USING(id_producto) JOIN usuarios u ON r.id_usuario=u.id_usuario WHERE u.auth_uuid IS NULL''')

    def vendors(self):
        return self.frame('''SELECT s.id_vendedor,s.razon_social,s.reputacion reputacion_registrada
        FROM vendedores s JOIN usuarios u USING(id_usuario) WHERE u.auth_uuid IS NULL''')
