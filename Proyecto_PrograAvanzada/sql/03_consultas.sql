-- Consultas ejecutables sobre el modelo MySQL normalizado. Sin credenciales.

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
-- JOIN de nueve tablas base (sin vistas): pedido_detalle, variantes, productos,
-- vendedores, pedidos, usuarios, distritos, provincias y departamentos.
-- El distrito histórico procede de usuarios: el dataset no contiene una dirección de entrega.
SELECT s.id_vendedor,s.razon_social,di.id_distrito,di.nombre distrito,pr.nombre provincia,
  de2.nombre departamento,COUNT(DISTINCT pe.id_pedido) pedidos,SUM(de.cantidad) unidades,
  ROUND(SUM(de.cantidad*de.precio_unit),2) ventas_brutas
FROM pedido_detalle de
JOIN variantes va USING(id_variante)
JOIN productos p USING(id_producto)
JOIN vendedores s ON s.id_vendedor=p.id_vendedor
JOIN pedidos pe ON pe.id_pedido=de.id_pedido
JOIN usuarios u ON u.id_usuario=pe.id_usuario
JOIN distritos di ON di.id_distrito=u.id_distrito
JOIN provincias pr ON pr.id_provincia=di.id_provincia
JOIN departamentos de2 ON de2.id_departamento=pr.id_departamento
WHERE pe.origen='dataset' AND pe.estado IN ('pagado','enviado','entregado')
GROUP BY s.id_vendedor,s.razon_social,di.id_distrito,di.nombre,pr.nombre,de2.nombre
ORDER BY ventas_brutas DESC,s.id_vendedor,di.id_distrito;

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

-- name: clientes_inactivos
-- Riesgo respecto a la cadencia individual, con referencia fija del histórico.
WITH compras AS (
  SELECT id_pedido,id_usuario,fecha,total,
    LAG(fecha) OVER(PARTITION BY id_usuario ORDER BY fecha,id_pedido) compra_anterior
  FROM pedidos WHERE origen='dataset' AND estado IN ('pagado','enviado','entregado')
), referencia AS (
  SELECT DATE_ADD(DATE(MAX(fecha)),INTERVAL 1 DAY) fecha FROM compras
), frecuencia AS (
  SELECT id_usuario,COUNT(*) pedidos,MAX(fecha) ultima_compra,SUM(total) monetario,
    AVG(TIMESTAMPDIFF(SECOND,compra_anterior,fecha)/86400) intervalo_dias
  FROM compras GROUP BY id_usuario
), riesgo AS (
  SELECT f.*,DATEDIFF(r.fecha,f.ultima_compra) recencia_dias,
    GREATEST(30,2*f.intervalo_dias) umbral_inactividad_dias
  FROM frecuencia f CROSS JOIN referencia r WHERE f.pedidos>=3
)
SELECT ri.id_usuario,u.nombre,ri.pedidos,ri.ultima_compra,ri.recencia_dias,
  ROUND(ri.intervalo_dias,2) intervalo_dias,ROUND(ri.umbral_inactividad_dias,2) umbral_inactividad_dias,
  ri.monetario,DENSE_RANK() OVER(ORDER BY ri.monetario DESC) prioridad_por_valor
FROM riesgo ri JOIN usuarios u USING(id_usuario)
WHERE ri.recencia_dias>ri.umbral_inactividad_dias
ORDER BY ri.monetario DESC,ri.id_usuario;

-- name: participacion_categorias
-- Descompone participación y concentración de ventas, sin llamarlas utilidades.
WITH ventas AS (
  SELECT c.id_categoria,c.nombre categoria,COUNT(DISTINCT pe.id_pedido) pedidos,
    COUNT(DISTINCT p.id_vendedor) vendedores,SUM(de.cantidad*de.precio_unit) ventas_brutas
  FROM categorias c JOIN productos p USING(id_categoria) JOIN variantes va USING(id_producto)
  JOIN pedido_detalle de USING(id_variante) JOIN pedidos pe USING(id_pedido)
  WHERE pe.origen='dataset' AND pe.estado IN ('pagado','enviado','entregado')
  GROUP BY c.id_categoria,c.nombre
)
SELECT *,DENSE_RANK() OVER(ORDER BY ventas_brutas DESC) posicion,
  ROUND(100*ventas_brutas/SUM(ventas_brutas) OVER(),4) participacion_pct,
  ROUND(100*SUM(ventas_brutas) OVER(ORDER BY ventas_brutas DESC,id_categoria ROWS UNBOUNDED PRECEDING)
    /SUM(ventas_brutas) OVER(),4) participacion_acumulada_pct
FROM ventas ORDER BY ventas_brutas DESC,id_categoria;

-- name: riesgo_courier
-- Intervalo aproximado de Wilson al 95% para la proporción tardía, mínimo 30 envíos.
WITH observados AS (
  SELECT co.id_courier,co.nombre courier,d.departamento,COUNT(*) envios,
    AVG(DATE(e.fecha_entrega)>e.fecha_estimada) proporcion_tardia,
    AVG(TIMESTAMPDIFF(SECOND,e.fecha_envio,e.fecha_entrega)/86400) entrega_dias,
    STDDEV_POP(TIMESTAMPDIFF(SECOND,e.fecha_envio,e.fecha_entrega)/86400) dispersion_dias
  FROM envios e JOIN couriers co USING(id_courier) JOIN pedidos pe USING(id_pedido)
  JOIN usuarios u ON pe.id_usuario=u.id_usuario
  JOIN v_distritos d ON d.id_distrito=COALESCE(pe.id_distrito_entrega,u.id_distrito)
  WHERE pe.origen='dataset' AND pe.estado IN ('pagado','enviado','entregado')
    AND e.fecha_estimada IS NOT NULL AND e.fecha_envio IS NOT NULL AND e.fecha_entrega>=e.fecha_envio
  GROUP BY co.id_courier,co.nombre,d.departamento HAVING COUNT(*)>=30
), intervalos AS (
  SELECT *, (proporcion_tardia+1.9208/envios)/(1+3.8416/envios) centro,
    1.96*SQRT((proporcion_tardia*(1-proporcion_tardia)+.9604/envios)/envios)/(1+3.8416/envios) margen
  FROM observados
)
SELECT id_courier,courier,departamento,envios,ROUND(entrega_dias,2) entrega_dias,
  ROUND(dispersion_dias,2) dispersion_dias,ROUND(100*proporcion_tardia,2) retraso_pct,
  ROUND(100*GREATEST(0,centro-margen),2) limite_inferior_95_pct,
  ROUND(100*LEAST(1,centro+margen),2) limite_superior_95_pct,
  DENSE_RANK() OVER(PARTITION BY departamento ORDER BY proporcion_tardia) posicion_en_departamento
FROM intervalos ORDER BY departamento,posicion_en_departamento,id_courier;

-- name: afinidad_sql
-- Market basket en SQL. Deduplicar el producto evita contar tallas como pares distintos.
WITH canastas AS (
  SELECT DISTINCT pe.id_pedido,va.id_producto FROM pedidos pe JOIN pedido_detalle de USING(id_pedido)
  JOIN variantes va USING(id_variante)
  WHERE pe.origen='dataset' AND pe.estado IN ('pagado','enviado','entregado')
), frecuencias AS (
  SELECT id_producto,COUNT(*) pedidos_producto FROM canastas GROUP BY id_producto
), parejas AS (
  SELECT a.id_producto producto_a,b.id_producto producto_b,COUNT(*) pedidos_juntos
  FROM canastas a JOIN canastas b ON a.id_pedido=b.id_pedido AND a.id_producto<b.id_producto
  GROUP BY a.id_producto,b.id_producto HAVING COUNT(*)>=5
), universo AS (
  SELECT COUNT(DISTINCT id_pedido) pedidos FROM canastas
)
SELECT pa.producto_a,a.titulo titulo_a,pa.producto_b,b.titulo titulo_b,pa.pedidos_juntos,
  fa.pedidos_producto pedidos_a,fb.pedidos_producto pedidos_b,
  ROUND(100*pa.pedidos_juntos/u.pedidos,4) soporte_pct,
  ROUND(100*pa.pedidos_juntos/fa.pedidos_producto,2) confianza_a_b_pct,
  ROUND(100*pa.pedidos_juntos/fb.pedidos_producto,2) confianza_b_a_pct,
  ROUND(pa.pedidos_juntos*u.pedidos/(fa.pedidos_producto*fb.pedidos_producto),4) lift
FROM parejas pa JOIN productos a ON a.id_producto=pa.producto_a
JOIN productos b ON b.id_producto=pa.producto_b
JOIN frecuencias fa ON fa.id_producto=pa.producto_a JOIN frecuencias fb ON fb.id_producto=pa.producto_b
CROSS JOIN universo u ORDER BY pa.pedidos_juntos DESC,lift DESC,pa.producto_a,pa.producto_b LIMIT 100;
