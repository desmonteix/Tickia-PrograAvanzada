-- El instalador comprueba INFORMATION_SCHEMA y crea solo los índices ausentes.
CREATE INDEX idx_pedido_usuario_fecha ON pedidos(id_usuario,fecha DESC,id_pedido DESC);
CREATE INDEX idx_pedido_origen_estado_fecha ON pedidos(origen,estado,fecha);
CREATE INDEX idx_producto_precio ON productos(precio,id_producto);
CREATE INDEX idx_producto_categoria_precio ON productos(id_categoria,precio,id_producto);
CREATE INDEX idx_variante_stock ON variantes(stock,id_producto);
CREATE INDEX idx_resena_usuario_producto ON resenas(id_usuario,id_producto);
CREATE INDEX idx_vendedor_reputacion ON vendedores(reputacion,id_vendedor);
