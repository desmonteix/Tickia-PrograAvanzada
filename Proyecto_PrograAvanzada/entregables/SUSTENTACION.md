# Guion de sustentación

1. Ejecutar el lanzador y mostrar catálogo, búsqueda, categorías y variantes.
2. Registrar un vendedor, publicar un producto con dos tallas/colores y stocks.
   En otra sesión, crear un segundo vendedor y publicar otro producto.
3. Como comprador, agregar tres unidades o más entre ambos productos. Mostrar
   carrito, courier, distrito, cupón y desglose: Builder, Strategy y Decorator.
4. Confirmar el pago de demostración y comprobar el stock de cada variante.
5. Abrir **Mis compras**, simular despacho y confirmar recepción. Relacionar los
   estados con State. Mostrar **Mis ventas** desde el vendedor.
6. Reseñar, guardar favorito y hacer una pregunta; responder desde el propietario.
7. En **Análisis**, presentar los 14 vendedores detectados, RFM, cohortes,
   co-compras, entregas y reputación. Descargar un CSV completo.

## MySQL y consultas

Conectar a `127.0.0.1:3307`; credenciales en `.local/mysql.env`.
No exponer sus contraseñas durante la presentación.

```sql
USE tickia_universidad;
SHOW TABLES;
SELECT COUNT(*) AS relaciones
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE();
SHOW CREATE PROCEDURE confirmar_pedido;
```

Son 15 tablas y 19 FK contando la autorrelación de categorías. Ejecutar los
bloques de `sql/03_consultas.sql`: `WITH RECURSIVE`, ventas por vendedor/distrito
con seis tablas (cinco operadores JOIN en la cadena), stock 0–3 y diagnóstico.

En el procedimiento, señalar `START TRANSACTION`, `JSON_TABLE`, validación del
total, UPDATE condicional de stock, handler de rollback y `COMMIT`. Pedido,
detalle, pago y envío pertenecen a la misma transacción.

## Defender los análisis

- RFM: pedidos distintos, total monetario y referencia 01-10-2026.
- Cohortes: primera compra, clientes únicos y solo meses observados.
- Co-compras: un producto por pedido; soporte, confianza y lift.
- Entregas: día prometido frente a recepción; excluir fechas inválidas.
- Reputación: agregar ventas, reseñas y envíos por separado evita multiplicar
  importes en relaciones uno-a-muchos.
- Diagnóstico: 14 vendedores con umbrales explícitos. La correlación no demuestra
  que cada reseña negativa corresponda a una entrega tardía.

Ejecutar `verificar.py` según el [manual](../COMO_EJECUTAR.md). Las pruebas usan
otra base y cubren concurrencia, rollback, idempotencia, permisos y Chromium.

Aplicación académica local: pagos/despachos simulados, tarifas educativas y
envío consolidado por pedido. No hay pasarela/courier real ni contraseñas para
los usuarios históricos. Los módulos originales de eventos quedan como referencia.
