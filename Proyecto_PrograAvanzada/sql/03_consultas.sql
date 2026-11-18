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
JOIN usuarios u ON pe.id_usuario=u.id_usuario JOIN v_distritos di ON u.id_distrito=di.id_distrito
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

-- name: resenas_producto
-- Cuatro tablas. El agregado no se cruza con detalles de venta.
SELECT p.id_producto,p.titulo,c.nombre categoria,s.razon_social vendedor,
  COUNT(*) resenas,ROUND(AVG(r.estrellas),2) estrellas_promedio
FROM resenas r JOIN productos p USING(id_producto)
JOIN categorias c USING(id_categoria) JOIN vendedores s USING(id_vendedor)
GROUP BY p.id_producto,p.titulo,c.nombre,s.razon_social
ORDER BY resenas DESC,p.id_producto;

-- name: favoritos_categoria
-- Cuatro tablas y dos dimensiones sobre la tabla puente de favoritos.
SELECT c.id_categoria,c.nombre categoria,s.id_vendedor,s.razon_social,
  COUNT(*) favoritos,COUNT(DISTINCT f.id_usuario) usuarios_interesados
FROM favoritos f JOIN productos p USING(id_producto)
JOIN categorias c USING(id_categoria) JOIN vendedores s USING(id_vendedor)
GROUP BY c.id_categoria,c.nombre,s.id_vendedor,s.razon_social
ORDER BY favoritos DESC,c.id_categoria,s.id_vendedor;

-- name: entregas_departamento
-- Cinco fuentes. v_distritos reconstruye los tres catálogos normalizados.
SELECT co.id_courier,co.nombre courier,di.departamento,COUNT(*) envios,
  ROUND(AVG(TIMESTAMPDIFF(SECOND,e.fecha_envio,e.fecha_entrega)/86400),2) entrega_dias,
  COUNT(e.fecha_estimada) promesas_conocidas,
  ROUND(100*AVG(IF(e.fecha_estimada IS NULL,NULL,DATE(e.fecha_entrega)>e.fecha_estimada)),2) retraso_pct
FROM envios e JOIN couriers co USING(id_courier) JOIN pedidos pe USING(id_pedido)
JOIN usuarios u ON pe.id_usuario=u.id_usuario
JOIN v_distritos di ON di.id_distrito=COALESCE(pe.id_distrito_entrega,u.id_distrito)
WHERE pe.origen='dataset' AND pe.estado IN ('pagado','enviado','entregado')
  AND e.fecha_envio IS NOT NULL AND e.fecha_entrega>=e.fecha_envio
GROUP BY co.id_courier,co.nombre,di.departamento
ORDER BY envios DESC,co.id_courier,di.departamento;

-- name: ranking_vendedores
-- RANK conserva empates. ROWS y el ID resuelven el orden del acumulado.
SELECT id_vendedor,razon_social,pedidos,ventas_brutas,
  RANK() OVER(ORDER BY ventas_brutas DESC) posicion,
  SUM(ventas_brutas) OVER(ORDER BY ventas_brutas DESC,id_vendedor ROWS UNBOUNDED PRECEDING) ventas_acumuladas
FROM v_ventas_vendedor WHERE pedidos>0
ORDER BY ventas_brutas DESC,id_vendedor;

-- name: ventas_mensuales
-- LAG compara con el mes observado anterior del mismo vendedor.
WITH meses AS (
  SELECT p.id_vendedor,DATE_FORMAT(pe.fecha,'%Y-%m') mes,SUM(de.cantidad*de.precio_unit) ventas_brutas
  FROM pedidos pe JOIN pedido_detalle de USING(id_pedido)
  JOIN variantes va USING(id_variante) JOIN productos p USING(id_producto)
  WHERE pe.origen='dataset' AND pe.estado IN ('pagado','enviado','entregado')
  GROUP BY p.id_vendedor,DATE_FORMAT(pe.fecha,'%Y-%m')
)
SELECT id_vendedor,mes,ventas_brutas,
  LAG(ventas_brutas) OVER(PARTITION BY id_vendedor ORDER BY mes) ventas_mes_anterior,
  SUM(ventas_brutas) OVER(PARTITION BY id_vendedor ORDER BY mes ROWS UNBOUNDED PRECEDING) acumulado_vendedor
FROM meses ORDER BY id_vendedor,mes;
