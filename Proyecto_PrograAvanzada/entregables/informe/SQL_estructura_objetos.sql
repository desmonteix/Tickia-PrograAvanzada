-- Tickia: creación de estructura y objetos. Ejecutar sobre una base nueva.
SET NAMES utf8mb4;
CREATE DATABASE IF NOT EXISTS tickia_universidad CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE tickia_universidad;


-- Archivo: 01_esquema.sql
-- MySQL 8.4 / InnoDB. Modelo lógico en 3FN: 17 tablas, 22 FK.
-- Los 15 CSV se conservan. Provincia y departamento se separan como catálogos.
CREATE TABLE IF NOT EXISTS departamentos (
  id_departamento INT PRIMARY KEY AUTO_INCREMENT, nombre VARCHAR(160) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS provincias (
  id_provincia INT PRIMARY KEY AUTO_INCREMENT, id_departamento INT NOT NULL, nombre VARCHAR(160) NOT NULL,
  UNIQUE KEY uq_provincia_departamento(id_departamento,nombre),
  FOREIGN KEY (id_departamento) REFERENCES departamentos(id_departamento)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS distritos (
  id_distrito INT PRIMARY KEY AUTO_INCREMENT,
  nombre VARCHAR(160) NOT NULL, id_provincia INT NOT NULL,
  CONSTRAINT fk_distrito_provincia FOREIGN KEY (id_provincia) REFERENCES provincias(id_provincia)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS usuarios (
  id_usuario INT PRIMARY KEY AUTO_INCREMENT, id_distrito INT NOT NULL,
  nombre VARCHAR(160) NOT NULL, email VARCHAR(254) NOT NULL, fecha_registro DATE NOT NULL,
  auth_uuid CHAR(36) UNIQUE NULL, password_hash VARCHAR(100) NULL, telefono VARCHAR(25) NULL,
  es_admin BOOLEAN NOT NULL DEFAULT FALSE,
  suspendido BOOLEAN NOT NULL DEFAULT FALSE, banned_until DATETIME NULL,
  auth_email VARCHAR(254) GENERATED ALWAYS AS (IF(password_hash IS NOT NULL, LOWER(email), NULL)) STORED,
  UNIQUE KEY uq_usuario_auth_email (auth_email), KEY idx_usuario_email (email),
  FOREIGN KEY (id_distrito) REFERENCES distritos(id_distrito)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS vendedores (
  id_vendedor INT PRIMARY KEY AUTO_INCREMENT, id_usuario INT NOT NULL,
  razon_social VARCHAR(160) NOT NULL, reputacion DECIMAL(3,2) NOT NULL,
  FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario), KEY idx_vendedor_usuario(id_usuario),
  CHECK (reputacion BETWEEN 0 AND 5)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS categorias (
  id_categoria INT PRIMARY KEY AUTO_INCREMENT, id_padre INT NULL, nombre VARCHAR(160) NOT NULL,
  FOREIGN KEY (id_padre) REFERENCES categorias(id_categoria)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS productos (
  id_producto INT PRIMARY KEY AUTO_INCREMENT, id_vendedor INT NOT NULL, id_categoria INT NOT NULL,
  titulo VARCHAR(160) NOT NULL, precio DECIMAL(12,2) NOT NULL,
  descripcion TEXT NULL, imagen VARCHAR(100) NULL, origen VARCHAR(10) NOT NULL DEFAULT 'dataset',
  creado DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (id_vendedor) REFERENCES vendedores(id_vendedor),
  FOREIGN KEY (id_categoria) REFERENCES categorias(id_categoria), CHECK (precio > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS variantes (
  id_variante INT PRIMARY KEY AUTO_INCREMENT, id_producto INT NOT NULL,
  talla VARCHAR(60) NULL, color VARCHAR(60) NULL, stock INT NOT NULL,
  FOREIGN KEY (id_producto) REFERENCES productos(id_producto), CHECK (stock >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS cupones (
  id_cupon INT PRIMARY KEY AUTO_INCREMENT, codigo VARCHAR(80) NOT NULL,
  descuento_pct DECIMAL(5,2) NOT NULL, vence DATE NOT NULL,
  KEY idx_cupon_codigo(codigo), CHECK (descuento_pct BETWEEN 0 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS pedidos (
  id_pedido INT PRIMARY KEY AUTO_INCREMENT, id_usuario INT NOT NULL, id_cupon INT NULL,
  fecha DATETIME NOT NULL, estado VARCHAR(20) NOT NULL, total DECIMAL(12,2) NOT NULL,
  id_distrito_entrega INT NULL,
  solicitud_uuid CHAR(36) NULL, solicitud_hash CHAR(64) NULL, origen VARCHAR(10) NOT NULL DEFAULT 'dataset',
  UNIQUE KEY uq_pedido_solicitud(id_usuario,solicitud_uuid), KEY idx_pedido_fecha(fecha),
  FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario), FOREIGN KEY (id_cupon) REFERENCES cupones(id_cupon),
  CONSTRAINT fk_pedido_distrito_entrega FOREIGN KEY (id_distrito_entrega) REFERENCES distritos(id_distrito),
  CHECK (total >= 0),
  CHECK (estado IN ('pendiente','pagado','enviado','entregado','cancelado'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS pedido_detalle (
  id_pedido INT NOT NULL, id_variante INT NOT NULL, cantidad INT NOT NULL, precio_unit DECIMAL(12,2) NOT NULL,
  PRIMARY KEY (id_pedido,id_variante),
  FOREIGN KEY (id_pedido) REFERENCES pedidos(id_pedido), FOREIGN KEY (id_variante) REFERENCES variantes(id_variante),
  CHECK (cantidad > 0 AND precio_unit >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS pagos (
  id_pago INT PRIMARY KEY AUTO_INCREMENT, id_pedido INT NOT NULL, metodo VARCHAR(80) NOT NULL,
  monto DECIMAL(12,2) NOT NULL, estado VARCHAR(20) NOT NULL,
  simulado BOOLEAN NOT NULL DEFAULT FALSE, fecha DATETIME NULL,
  FOREIGN KEY (id_pedido) REFERENCES pedidos(id_pedido), CHECK (monto >= 0),
  CHECK (estado IN ('aprobado','rechazado','reembolsado','pendiente'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS couriers (
  id_courier INT PRIMARY KEY AUTO_INCREMENT, nombre VARCHAR(120) NOT NULL, costo_base DECIMAL(12,2) NOT NULL,
  estrategia VARCHAR(20) NOT NULL DEFAULT 'estandar', CHECK (costo_base >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS envios (
  id_envio INT PRIMARY KEY AUTO_INCREMENT, id_pedido INT NOT NULL, id_courier INT NOT NULL,
  fecha_envio DATETIME NULL, fecha_entrega DATETIME NULL, fecha_estimada DATE NULL, costo_envio DECIMAL(12,2) NOT NULL,
  FOREIGN KEY (id_pedido) REFERENCES pedidos(id_pedido), FOREIGN KEY (id_courier) REFERENCES couriers(id_courier),
  CHECK (costo_envio >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS resenas (
  id_resena INT PRIMARY KEY AUTO_INCREMENT, id_producto INT NOT NULL, id_usuario INT NOT NULL,
  estrellas INT NOT NULL, comentario TEXT NULL, fecha DATE NOT NULL,
  FOREIGN KEY (id_producto) REFERENCES productos(id_producto), FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
  CHECK (estrellas BETWEEN 1 AND 5), KEY idx_resena_producto_fecha(id_producto,fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS preguntas (
  id_pregunta INT PRIMARY KEY AUTO_INCREMENT, id_producto INT NOT NULL, id_usuario INT NOT NULL,
  texto TEXT NOT NULL, respuesta TEXT NULL, fecha DATETIME NOT NULL,
  FOREIGN KEY (id_producto) REFERENCES productos(id_producto), FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
  KEY idx_pregunta_producto_fecha(id_producto,fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS favoritos (
  id_usuario INT NOT NULL, id_producto INT NOT NULL, fecha DATE NOT NULL,
  PRIMARY KEY (id_usuario,id_producto),
  FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario), FOREIGN KEY (id_producto) REFERENCES productos(id_producto)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- Archivo: 05_indices.sql
-- El instalador comprueba INFORMATION_SCHEMA y crea solo los índices ausentes.
CREATE INDEX idx_pedido_usuario_fecha ON pedidos(id_usuario,fecha DESC,id_pedido DESC);
CREATE INDEX idx_pedido_origen_estado_fecha ON pedidos(origen,estado,fecha);
CREATE INDEX idx_producto_precio ON productos(precio,id_producto);
CREATE INDEX idx_producto_categoria_precio ON productos(id_categoria,precio,id_producto);
CREATE INDEX idx_variante_stock ON variantes(stock,id_producto);
CREATE INDEX idx_resena_usuario_producto ON resenas(id_usuario,id_producto);
CREATE INDEX idx_vendedor_reputacion ON vendedores(reputacion,id_vendedor);


-- Archivo: 04_vistas.sql
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


-- Archivo: 02_procedimientos.sql
DROP PROCEDURE IF EXISTS confirmar_pedido;
DELIMITER $$
-- Ejecutar como una única sentencia CREATE PROCEDURE desde Python.
-- El procedimiento es la autoridad final de precio, descuentos y stock.
CREATE PROCEDURE confirmar_pedido(
  IN p_usuario INT, IN p_solicitud CHAR(36), IN p_hash CHAR(64), IN p_items JSON,
  IN p_cupon INT, IN p_courier INT, IN p_distrito INT, IN p_metodo VARCHAR(80),
  IN p_total_esperado DECIMAL(12,2)
)
COMMENT 'tickia-universidad-v3'
SQL SECURITY INVOKER
procedure_body: BEGIN
  DECLARE v_pedido INT DEFAULT NULL;
  DECLARE v_hash CHAR(64);
  DECLARE v_count INT DEFAULT 0;
  DECLARE v_units INT DEFAULT 0;
  DECLARE v_subtotal DECIMAL(12,2) DEFAULT 0;
  DECLARE v_neto DECIMAL(12,2) DEFAULT 0;
  DECLARE v_envio DECIMAL(12,2) DEFAULT 0;
  DECLARE v_base DECIMAL(12,2);
  DECLARE v_pct DECIMAL(5,2) DEFAULT 0;
  DECLARE v_departamento VARCHAR(160);
  DECLARE v_estrategia VARCHAR(20);
  DECLARE EXIT HANDLER FOR 1062
  BEGIN
    ROLLBACK;
    SELECT MAX(id_pedido), MAX(solicitud_hash) INTO v_pedido, v_hash
      FROM pedidos WHERE id_usuario=p_usuario AND solicitud_uuid=p_solicitud;
    DROP TEMPORARY TABLE IF EXISTS tmp_tickia_items;
    IF v_pedido IS NOT NULL AND v_hash=p_hash THEN
      SELECT id_pedido,total,estado FROM pedidos WHERE id_pedido=v_pedido;
    ELSE
      RESIGNAL;
    END IF;
  END;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    DROP TEMPORARY TABLE IF EXISTS tmp_tickia_items;
    RESIGNAL;
  END;

  START TRANSACTION;
  SELECT MAX(id_pedido),MAX(solicitud_hash) INTO v_pedido,v_hash
    FROM pedidos WHERE id_usuario=p_usuario AND solicitud_uuid=p_solicitud;
  IF v_pedido IS NOT NULL THEN
    IF NOT (v_hash<=>p_hash) OR p_hash IS NULL THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Solicitud reutilizada para otro pedido.';
    END IF;
    COMMIT;
    SELECT id_pedido,total,estado FROM pedidos WHERE id_pedido=v_pedido;
    LEAVE procedure_body;
  END IF;

  IF JSON_TYPE(p_items)<>'ARRAY' OR JSON_LENGTH(p_items) NOT BETWEEN 1 AND 20 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='El pedido debe tener entre 1 y 20 variantes.';
  END IF;
  DROP TEMPORARY TABLE IF EXISTS tmp_tickia_items;
  IF EXISTS (SELECT 1 FROM JSON_TABLE(p_items,'$[*]' COLUMNS(
      id_variante INT PATH '$.variant_id' ERROR ON ERROR,
      cantidad INT PATH '$.quantity' ERROR ON ERROR
    )) j WHERE id_variante IS NULL OR id_variante<1 OR cantidad IS NULL OR cantidad NOT BETWEEN 1 AND 100) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Cantidad o variante inválida.';
  END IF;
  CREATE TEMPORARY TABLE tmp_tickia_items (
    id_variante INT PRIMARY KEY, cantidad INT NOT NULL
  ) ENGINE=InnoDB;
  INSERT INTO tmp_tickia_items
    SELECT id_variante,SUM(cantidad) FROM JSON_TABLE(p_items,'$[*]' COLUMNS(
      id_variante INT PATH '$.variant_id' ERROR ON ERROR,
      cantidad INT PATH '$.quantity' ERROR ON ERROR
    )) j GROUP BY id_variante;
  SELECT COUNT(*),SUM(cantidad) INTO v_count,v_units FROM tmp_tickia_items;
  IF EXISTS (SELECT 1 FROM tmp_tickia_items WHERE cantidad NOT BETWEEN 1 AND 100 OR id_variante<1) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Cantidad inválida.';
  END IF;
  IF (SELECT COUNT(*) FROM variantes v JOIN tmp_tickia_items i USING(id_variante))<>v_count THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Una variante ya no existe.';
  END IF;
  IF EXISTS (SELECT 1 FROM tmp_tickia_items i JOIN variantes v USING(id_variante)
    JOIN productos p USING(id_producto) JOIN vendedores s USING(id_vendedor) WHERE s.id_usuario=p_usuario) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='No puedes comprar tus propios productos.';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM usuarios WHERE id_usuario=p_usuario AND password_hash IS NOT NULL) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Cuenta de comprador inválida.';
  END IF;

  SELECT SUM(i.cantidad*p.precio) INTO v_subtotal FROM tmp_tickia_items i
    JOIN variantes v USING(id_variante) JOIN productos p USING(id_producto);
  SET v_neto=v_subtotal;
  IF v_units>=3 THEN SET v_neto=v_neto-ROUND(v_neto*0.03,2); END IF;
  IF p_cupon IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM cupones WHERE id_cupon=p_cupon
       AND vence>=DATE(CONVERT_TZ(UTC_TIMESTAMP(),'+00:00','-05:00'))) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='El cupón no existe o venció.';
    END IF;
    SELECT descuento_pct INTO v_pct FROM cupones WHERE id_cupon=p_cupon;
    SET v_neto=v_neto-ROUND(v_neto*v_pct/100,2);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM couriers WHERE id_courier=p_courier)
     OR NOT EXISTS (SELECT 1 FROM distritos WHERE id_distrito=p_distrito) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Selecciona un courier y un distrito válidos.';
  END IF;
  SELECT departamento INTO v_departamento FROM v_distritos WHERE id_distrito=p_distrito;
  SELECT costo_base,estrategia INTO v_base,v_estrategia FROM couriers WHERE id_courier=p_courier;
  SET v_envio=ROUND(CASE v_estrategia
    WHEN 'rapido' THEN v_base*IF(LOWER(v_departamento)='lima',1.40,1.75)+0.50*v_units
    WHEN 'economico' THEN v_base*IF(LOWER(v_departamento)='lima',0.85,1.15)
    ELSE v_base*IF(LOWER(v_departamento)='lima',1.00,1.35) END,2);
  IF p_total_esperado IS NULL OR v_neto+v_envio<>p_total_esperado THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='La cotización cambió; revisa el total antes de confirmar.';
  END IF;
  IF p_metodo NOT IN ('tarjeta_demo','yape_demo','transferencia_demo') THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Método de demostración inválido.';
  END IF;

  -- UPDATE condicional: InnoDB bloquea las variantes. Si falta cualquier unidad,
  -- el handler revierte también los descuentos de stock que sí habían avanzado.
  UPDATE variantes v JOIN tmp_tickia_items i USING(id_variante)
    SET v.stock=v.stock-i.cantidad WHERE v.stock>=i.cantidad;
  IF ROW_COUNT()<>v_count THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Stock insuficiente; no se modificó ningún artículo.';
  END IF;
  INSERT INTO pedidos(id_usuario,id_cupon,fecha,estado,total,id_distrito_entrega,
      solicitud_uuid,solicitud_hash,origen)
    VALUES(p_usuario,p_cupon,UTC_TIMESTAMP(),'pendiente',v_neto+v_envio,p_distrito,
      p_solicitud,p_hash,'web');
  SET v_pedido=LAST_INSERT_ID();
  INSERT INTO pedido_detalle(id_pedido,id_variante,cantidad,precio_unit)
    SELECT v_pedido,i.id_variante,i.cantidad,p.precio FROM tmp_tickia_items i
      JOIN variantes v USING(id_variante) JOIN productos p USING(id_producto);
  INSERT INTO pagos(id_pedido,metodo,monto,estado,simulado,fecha)
    VALUES(v_pedido,p_metodo,v_neto+v_envio,'aprobado',TRUE,UTC_TIMESTAMP());
  UPDATE pedidos SET estado='pagado' WHERE id_pedido=v_pedido AND estado='pendiente';
  INSERT INTO envios(id_pedido,id_courier,fecha_estimada,costo_envio)
    VALUES(v_pedido,p_courier,DATE_ADD(DATE(CONVERT_TZ(UTC_TIMESTAMP(),'+00:00','-05:00')),
      INTERVAL (CASE v_estrategia WHEN 'rapido' THEN 2 WHEN 'economico' THEN 7 ELSE 5 END) DAY),v_envio);
  DROP TEMPORARY TABLE tmp_tickia_items;
  COMMIT;
  SELECT id_pedido,total,estado FROM pedidos WHERE id_pedido=v_pedido;
END$$
DELIMITER ;

-- Archivo: 06_trigger.sql
DROP TRIGGER IF EXISTS tr_pedido_validar_estado;
DELIMITER $$
-- Enviar como una única sentencia desde Python o con DELIMITER en mysql.
CREATE TRIGGER tr_pedido_validar_estado
BEFORE UPDATE ON pedidos FOR EACH ROW
BEGIN
  IF NEW.estado <> OLD.estado AND NOT (
    (OLD.estado='pendiente' AND NEW.estado IN ('pagado','cancelado')) OR
    (OLD.estado='pagado' AND NEW.estado='enviado') OR
    (OLD.estado='enviado' AND NEW.estado='entregado')
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Transicion de estado de pedido no permitida.';
  END IF;
END$$
DELIMITER ;
