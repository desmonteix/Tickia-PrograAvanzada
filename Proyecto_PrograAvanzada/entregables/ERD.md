# Modelo entidad-relación

17 tablas y 22 FK, contando la autorrelación de categorías.
Tipos, restricciones y columnas completas en [01_esquema.sql](../sql/01_esquema.sql).

```mermaid
erDiagram
    departamentos ||--o{ provincias : agrupa
    provincias ||--o{ distritos : agrupa
    distritos ||--o{ usuarios : residencia
    distritos o|--o{ pedidos : destino
    usuarios ||--o{ vendedores : vende
    usuarios ||--o{ pedidos : compra
    usuarios ||--o{ resenas : escribe
    usuarios ||--o{ preguntas : pregunta
    usuarios ||--o{ favoritos : guarda
    categorias o|--o{ categorias : padre
    categorias ||--o{ productos : clasifica
    vendedores ||--o{ productos : publica
    productos ||--o{ variantes : presenta
    productos ||--o{ resenas : recibe
    productos ||--o{ preguntas : recibe
    productos ||--o{ favoritos : interesa
    cupones o|--o{ pedidos : descuenta
    pedidos ||--o{ pedido_detalle : contiene
    variantes ||--o{ pedido_detalle : integra
    pedidos ||--o{ pagos : registra
    pedidos ||--o{ envios : despacha
    couriers ||--o{ envios : transporta

    departamentos {
        int id_departamento PK
        string nombre UK
    }
    provincias {
        int id_provincia PK
        int id_departamento FK
        string nombre
    }
    distritos {
        int id_distrito PK
        int id_provincia FK
    }
    usuarios {
        int id_usuario PK
        int id_distrito FK
        string auth_uuid UK
        string password_hash
    }
    vendedores {
        int id_vendedor PK
        int id_usuario FK
    }
    categorias {
        int id_categoria PK
        int id_padre FK
    }
    productos {
        int id_producto PK
        int id_vendedor FK
        int id_categoria FK
        decimal precio
    }
    variantes {
        int id_variante PK
        int id_producto FK
        string talla
        string color
        int stock
    }
    cupones {
        int id_cupon PK
    }
    pedidos {
        int id_pedido PK
        int id_usuario FK
        int id_cupon FK
        int id_distrito_entrega FK
        string estado
        decimal total
        string solicitud_uuid
    }
    pedido_detalle {
        int id_pedido PK,FK
        int id_variante PK,FK
        int cantidad
        decimal precio_unit
    }
    pagos {
        int id_pago PK
        int id_pedido FK
    }
    couriers {
        int id_courier PK
    }
    envios {
        int id_envio PK
        int id_pedido FK
        int id_courier FK
    }
    resenas {
        int id_resena PK
        int id_producto FK
        int id_usuario FK
    }
    preguntas {
        int id_pregunta PK
        int id_producto FK
        int id_usuario FK
    }
    favoritos {
        int id_usuario PK,FK
        int id_producto PK,FK
    }
```

`pedido_detalle` resuelve pedidos–variantes; `favoritos`, usuarios–productos.
Cada producto pertenece a un vendedor. La aplicación consolida un envío por
pedido multivendedor; el esquema admite múltiples pagos/envíos para conservar
el histórico original.

Las extensiones permiten autenticación, descripción/foto/origen, estrategia de
courier y solicitudes idempotentes. El destino web usa una FK a distritos.
Las vistas reconstruyen geografía e importes; el histórico solo permite inferir
distrito desde el usuario. Ver [justificación de 3FN](NORMALIZACION_3FN.md).
