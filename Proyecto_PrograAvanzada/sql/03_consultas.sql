-- Consultas ejecutables sobre las quince tablas MySQL. Sin credenciales.

-- name: categorias
WITH RECURSIVE arbol AS (
  SELECT id_categoria,id_padre,nombre,0 nivel,CAST(nombre AS CHAR(1500)) ruta
  FROM categorias WHERE id_padre IS NULL
  UNION ALL
  SELECT c.id_categoria,c.id_padre,c.nombre,a.nivel+1,CONCAT(a.ruta,' > ',c.nombre)
  FROM categorias c JOIN arbol a ON c.id_padre=a.id_categoria
)
SELECT * FROM arbol ORDER BY ruta;

-- name: ventas_distrito
-- Exactamente seis tablas: productos, variantes, pedido_detalle, pedidos,
-- usuarios y distritos. El vendedor se identifica por productos.id_vendedor.
-- El distrito histórico procede de usuarios: el dataset no contiene una dirección de entrega.
SELECT p.id_vendedor,di.id_distrito,di.nombre distrito,di.departamento,
  COUNT(DISTINCT pe.id_pedido) pedidos,SUM(de.cantidad) unidades,
  ROUND(SUM(de.cantidad*de.precio_unit),2) ventas_brutas
FROM productos p JOIN variantes va USING(id_producto)
JOIN pedido_detalle de USING(id_variante) JOIN pedidos pe USING(id_pedido)
JOIN usuarios u ON pe.id_usuario=u.id_usuario JOIN distritos di ON u.id_distrito=di.id_distrito
WHERE pe.origen='dataset' AND pe.estado IN ('pagado','enviado','entregado')
GROUP BY p.id_vendedor,di.id_distrito,di.nombre,di.departamento
ORDER BY ventas_brutas DESC,p.id_vendedor,di.id_distrito;

-- name: stock
SELECT p.id_producto,p.titulo,va.id_variante,va.talla,va.color,va.stock,
  s.razon_social vendedor,IF(va.stock=0,'Agotado','Crítico') nivel
FROM variantes va JOIN productos p USING(id_producto) JOIN vendedores s USING(id_vendedor)
WHERE va.stock<=3 ORDER BY va.stock,va.id_variante;

-- name: diagnostico_sql
-- Cada agregado se calcula por separado para no multiplicar ventas por reseñas.
WITH ventas AS (
  SELECT p.id_vendedor,COUNT(DISTINCT pe.id_pedido) pedidos,SUM(de.cantidad*de.precio_unit) ventas_brutas
  FROM pedido_detalle de JOIN variantes va USING(id_variante) JOIN productos p USING(id_producto)
  JOIN pedidos pe USING(id_pedido) WHERE pe.origen='dataset' AND pe.estado IN ('pagado','enviado','entregado')
  GROUP BY p.id_vendedor
), opinion AS (
  SELECT p.id_vendedor,AVG(r.estrellas) estrellas_promedio,COUNT(*) resenas
  FROM resenas r JOIN productos p USING(id_producto) JOIN usuarios u ON r.id_usuario=u.id_usuario
  WHERE u.auth_uuid IS NULL GROUP BY p.id_vendedor
), por_pedido AS (
  SELECT id_pedido,MAX(DATE(fecha_entrega)>fecha_estimada) tarde
  FROM envios WHERE fecha_entrega IS NOT NULL AND fecha_envio IS NOT NULL
    AND fecha_entrega>=fecha_envio AND fecha_estimada IS NOT NULL GROUP BY id_pedido
), enlaces AS (
  SELECT DISTINCT p.id_vendedor,pe.id_pedido FROM pedidos pe JOIN pedido_detalle de USING(id_pedido)
  JOIN variantes va USING(id_variante) JOIN productos p USING(id_producto)
  WHERE pe.origen='dataset' AND pe.estado IN ('pagado','enviado','entregado')
), puntualidad AS (
  SELECT en.id_vendedor,100*AVG(pp.tarde) retraso_pct FROM enlaces en
  JOIN por_pedido pp USING(id_pedido) GROUP BY en.id_vendedor
)
SELECT s.id_vendedor,s.razon_social,v.pedidos,ROUND(v.ventas_brutas,2) ventas_brutas,
  ROUND(o.estrellas_promedio,2) estrellas_promedio,o.resenas,ROUND(p.retraso_pct,2) retraso_pct
FROM vendedores s JOIN ventas v USING(id_vendedor) JOIN opinion o USING(id_vendedor)
JOIN puntualidad p USING(id_vendedor)
WHERE v.pedidos>=10 AND o.estrellas_promedio<3.5 AND p.retraso_pct>=25
ORDER BY v.ventas_brutas DESC;
