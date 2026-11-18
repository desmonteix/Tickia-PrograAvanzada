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
END
