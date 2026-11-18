"""Repositories de compras: consultas parametrizadas y límites de transacción explícitos."""
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
