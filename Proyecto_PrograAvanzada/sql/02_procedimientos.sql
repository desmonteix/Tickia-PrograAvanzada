-- Ejecutar como una única sentencia CREATE PROCEDURE desde Python.
-- El procedimiento es la autoridad final de precio, descuentos y stock.
CREATE PROCEDURE confirmar_pedido(
  IN p_usuario INT, IN p_solicitud CHAR(36), IN p_hash CHAR(64), IN p_items JSON,
  IN p_cupon INT, IN p_courier INT, IN p_distrito INT, IN p_metodo VARCHAR(80),
  IN p_total_esperado DECIMAL(12,2)
)
COMMENT 'tickia-universidad-v2'
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
  DECLARE v_destino JSON;
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
  SELECT departamento,JSON_OBJECT('id_distrito',id_distrito,'distrito',nombre,
      'provincia',provincia,'departamento',departamento) INTO v_departamento,v_destino
    FROM distritos WHERE id_distrito=p_distrito;
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
  INSERT INTO pedidos(id_usuario,id_cupon,fecha,estado,total,subtotal,descuento,costo_envio,
      destino,solicitud_uuid,solicitud_hash,origen)
    VALUES(p_usuario,p_cupon,UTC_TIMESTAMP(),'pendiente',v_neto+v_envio,v_subtotal,v_subtotal-v_neto,v_envio,
      v_destino,p_solicitud,p_hash,'web');
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
END
