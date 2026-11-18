-- Proyecciones de lectura: las tablas base mantienen las dependencias de 3FN.
CREATE OR REPLACE SQL SECURITY INVOKER VIEW v_distritos AS
SELECT d.id_distrito,d.nombre,p.nombre provincia,de.nombre departamento,
       d.id_provincia,p.id_departamento
FROM distritos d JOIN provincias p USING(id_provincia)
JOIN departamentos de USING(id_departamento);

CREATE OR REPLACE SQL SECURITY INVOKER VIEW v_pedidos_importes AS
SELECT pe.*,COALESCE(li.subtotal,pe.total) subtotal,COALESCE(en.costo_envio,0) costo_envio,
  COALESCE(li.subtotal,pe.total)+IF(pe.origen='dataset',0,COALESCE(en.costo_envio,0))-pe.total descuento,
  IF(d.id_distrito IS NULL,NULL,JSON_OBJECT('id_distrito',d.id_distrito,'distrito',d.nombre,
      'provincia',d.provincia,'departamento',d.departamento)) destino
FROM pedidos pe
LEFT JOIN (SELECT id_pedido,SUM(cantidad*precio_unit) subtotal FROM pedido_detalle GROUP BY id_pedido) li USING(id_pedido)
LEFT JOIN (SELECT id_pedido,SUM(costo_envio) costo_envio FROM envios GROUP BY id_pedido) en USING(id_pedido)
LEFT JOIN v_distritos d ON pe.id_distrito_entrega=d.id_distrito;

CREATE OR REPLACE SQL SECURITY INVOKER VIEW v_ventas_vendedor AS
SELECT s.id_vendedor,s.razon_social,COALESCE(v.pedidos,0) pedidos,
       COALESCE(v.unidades,0) unidades,COALESCE(v.ventas_brutas,0) ventas_brutas
FROM vendedores s LEFT JOIN (
  SELECT p.id_vendedor,COUNT(DISTINCT pe.id_pedido) pedidos,SUM(de.cantidad) unidades,
         SUM(de.cantidad*de.precio_unit) ventas_brutas
  FROM productos p JOIN variantes va USING(id_producto)
  JOIN pedido_detalle de USING(id_variante) JOIN pedidos pe USING(id_pedido)
  WHERE pe.origen='dataset' AND pe.estado IN ('pagado','enviado','entregado')
  GROUP BY p.id_vendedor
) v USING(id_vendedor);
