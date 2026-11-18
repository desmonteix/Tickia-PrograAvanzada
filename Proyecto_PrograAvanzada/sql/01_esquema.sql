-- MySQL 8.4 / InnoDB. 15 tablas del modelo: 18 relaciones entre tablas
-- más la autorrelación de categorías necesaria para la jerarquía.
CREATE TABLE IF NOT EXISTS distritos (
  id_distrito INT PRIMARY KEY AUTO_INCREMENT,
  nombre VARCHAR(160) NOT NULL, provincia VARCHAR(160) NOT NULL, departamento VARCHAR(160) NOT NULL
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
  subtotal DECIMAL(12,2) NULL, descuento DECIMAL(12,2) NOT NULL DEFAULT 0,
  costo_envio DECIMAL(12,2) NOT NULL DEFAULT 0, destino JSON NULL,
  solicitud_uuid CHAR(36) NULL, solicitud_hash CHAR(64) NULL, origen VARCHAR(10) NOT NULL DEFAULT 'dataset',
  UNIQUE KEY uq_pedido_solicitud(id_usuario,solicitud_uuid), KEY idx_pedido_fecha(fecha),
  FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario), FOREIGN KEY (id_cupon) REFERENCES cupones(id_cupon),
  CHECK (total >= 0 AND descuento >= 0 AND costo_envio >= 0),
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
