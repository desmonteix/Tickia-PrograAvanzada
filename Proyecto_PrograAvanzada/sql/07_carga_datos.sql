-- Carga de los 15 CSV con SQL (801.519 filas). Alternativa manual al cargador Python.
-- La aplicación (iniciar.py) carga con backend/academic/bootstrap.py; este script deja
-- los mismos datos e IDs para quien prefiera crear la base solo con SQL.
--
-- Orden: 01_esquema.sql (o SQL_estructura_objetos.sql) y luego este archivo.
-- Ejecutar desde la RAÍZ del repositorio, porque las rutas de los CSV son relativas:
--   mysql --local-infile=1 -u root -p tickia_universidad < Proyecto_PrograAvanzada/sql/07_carga_datos.sql
-- El servidor debe permitir LOCAL INFILE:  SET GLOBAL local_infile = 1;
-- En MySQL Workbench: Edit Connection > Advanced > Others: OPT_LOCAL_INFILE=1, y usar
-- rutas absolutas a los CSV.
--
-- Las celdas vacías se convierten en NULL con NULLIF. La última columna de cada archivo
-- se limpia de '\r' por si Git convirtió los CSV a saltos de línea de Windows.
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;   -- categorias se autorreferencia
START TRANSACTION;

-- 01 distritos: se descompone en departamentos, provincias y distritos (3FN).
-- El orden BINARY reproduce el orden del cargador Python (por código Unicode),
-- de modo que los IDs de departamentos y provincias coinciden con los de la aplicación.
CREATE TEMPORARY TABLE stg_distritos (
  id_distrito INT, nombre VARCHAR(160), provincia VARCHAR(160), departamento VARCHAR(160)
);
LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/01_distritos.csv' INTO TABLE stg_distritos
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_distrito, nombre, provincia, @departamento)
  SET departamento = TRIM(TRAILING '\r' FROM @departamento);
INSERT INTO departamentos(nombre)
  SELECT DISTINCT departamento FROM stg_distritos ORDER BY BINARY departamento;
INSERT INTO provincias(id_departamento, nombre)
  SELECT DISTINCT d.id_departamento, s.provincia
  FROM stg_distritos s JOIN departamentos d ON d.nombre = s.departamento
  ORDER BY d.id_departamento, BINARY s.provincia;
INSERT INTO distritos(id_distrito, nombre, id_provincia)
  SELECT s.id_distrito, s.nombre, p.id_provincia
  FROM stg_distritos s
  JOIN departamentos d ON d.nombre = s.departamento
  JOIN provincias p ON p.id_departamento = d.id_departamento AND p.nombre = s.provincia
  ORDER BY s.id_distrito;
DROP TEMPORARY TABLE stg_distritos;

LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/02_usuarios.csv' INTO TABLE usuarios
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_usuario, id_distrito, nombre, email, @fecha_registro)
  SET fecha_registro = TRIM(TRAILING '\r' FROM @fecha_registro);

LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/03_vendedores.csv' INTO TABLE vendedores
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_vendedor, id_usuario, razon_social, @reputacion)
  SET reputacion = TRIM(TRAILING '\r' FROM @reputacion);

LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/04_categorias.csv' INTO TABLE categorias
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_categoria, @id_padre, @nombre)
  SET id_padre = NULLIF(@id_padre, ''), nombre = TRIM(TRAILING '\r' FROM @nombre);

LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/05_productos.csv' INTO TABLE productos
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_producto, id_vendedor, id_categoria, titulo, @precio)
  SET precio = TRIM(TRAILING '\r' FROM @precio);

LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/06_variantes.csv' INTO TABLE variantes
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_variante, id_producto, @talla, @color, @stock)
  SET talla = NULLIF(@talla, ''), color = NULLIF(@color, ''),
      stock = TRIM(TRAILING '\r' FROM @stock);

LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/07_cupones.csv' INTO TABLE cupones
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_cupon, codigo, descuento_pct, @vence)
  SET vence = TRIM(TRAILING '\r' FROM @vence);

LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/08_pedidos.csv' INTO TABLE pedidos
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_pedido, id_usuario, @id_cupon, fecha, estado, @total)
  SET id_cupon = NULLIF(@id_cupon, ''), total = TRIM(TRAILING '\r' FROM @total);

LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/09_pedido_detalle.csv' INTO TABLE pedido_detalle
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_pedido, id_variante, cantidad, @precio_unit)
  SET precio_unit = TRIM(TRAILING '\r' FROM @precio_unit);

LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/10_pagos.csv' INTO TABLE pagos
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_pago, id_pedido, metodo, monto, @estado)
  SET estado = TRIM(TRAILING '\r' FROM @estado);

LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/11_couriers.csv' INTO TABLE couriers
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_courier, nombre, @costo_base)
  SET costo_base = TRIM(TRAILING '\r' FROM @costo_base);

LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/12_envios.csv' INTO TABLE envios
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_envio, id_pedido, id_courier, @fecha_envio, @fecha_entrega, @fecha_estimada, @costo_envio)
  SET fecha_envio = NULLIF(@fecha_envio, ''), fecha_entrega = NULLIF(@fecha_entrega, ''),
      fecha_estimada = NULLIF(@fecha_estimada, ''), costo_envio = TRIM(TRAILING '\r' FROM @costo_envio);

LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/13_resenas.csv' INTO TABLE resenas
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_resena, id_producto, id_usuario, estrellas, @comentario, @fecha)
  SET comentario = NULLIF(@comentario, ''), fecha = TRIM(TRAILING '\r' FROM @fecha);

LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/14_preguntas.csv' INTO TABLE preguntas
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_pregunta, id_producto, id_usuario, texto, @respuesta, @fecha)
  SET respuesta = NULLIF(@respuesta, ''), fecha = TRIM(TRAILING '\r' FROM @fecha);

LOAD DATA LOCAL INFILE 'Proyecto_PrograAvanzada/15_favoritos.csv' INTO TABLE favoritos
  CHARACTER SET utf8mb4 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n' IGNORE 1 LINES
  (id_usuario, id_producto, @fecha)
  SET fecha = TRIM(TRAILING '\r' FROM @fecha);

-- Misma asignación de estrategias de envío que hace el cargador Python.
UPDATE couriers SET estrategia = CASE MOD(id_courier,3)
  WHEN 1 THEN 'estandar' WHEN 2 THEN 'rapido' ELSE 'economico' END;

COMMIT;
SET FOREIGN_KEY_CHECKS = 1;

-- Verificación: filas por tabla (los 15 CSV suman 801.519).
SELECT 'distritos' tabla, COUNT(*) filas FROM distritos
UNION ALL SELECT 'usuarios', COUNT(*) FROM usuarios
UNION ALL SELECT 'vendedores', COUNT(*) FROM vendedores
UNION ALL SELECT 'categorias', COUNT(*) FROM categorias
UNION ALL SELECT 'productos', COUNT(*) FROM productos
UNION ALL SELECT 'variantes', COUNT(*) FROM variantes
UNION ALL SELECT 'cupones', COUNT(*) FROM cupones
UNION ALL SELECT 'pedidos', COUNT(*) FROM pedidos
UNION ALL SELECT 'pedido_detalle', COUNT(*) FROM pedido_detalle
UNION ALL SELECT 'pagos', COUNT(*) FROM pagos
UNION ALL SELECT 'couriers', COUNT(*) FROM couriers
UNION ALL SELECT 'envios', COUNT(*) FROM envios
UNION ALL SELECT 'resenas', COUNT(*) FROM resenas
UNION ALL SELECT 'preguntas', COUNT(*) FROM preguntas
UNION ALL SELECT 'favoritos', COUNT(*) FROM favoritos;
