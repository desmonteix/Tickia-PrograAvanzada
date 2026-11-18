"""Redacción del informe; incorpora scripts y metadatos verificables sin secretos."""
from collections import defaultdict
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / 'Proyecto_PrograAvanzada'
OUT = PROJECT / 'entregables/informe'
BUILD = PROJECT / '.local/informe-build'


INTRO = '''# 1. Enunciado del caso
## 1.1. Contexto y problema
Tickia es un marketplace multivendedor adaptado para el proyecto universitario de Programación Avanzada. La plataforma conserva la identidad visual de Tickia y presenta un catálogo de productos físicos. Reúne compradores y vendedores en una aplicación web que permite publicar artículos con variantes, comprar varios productos, registrar pagos y entregas de demostración y consultar información comercial.
El caso plantea una tienda similar, en su funcionamiento general, a un marketplace: cada vendedor administra publicaciones y cada cliente puede comprar productos de diferentes vendedores dentro de un pedido. La información de usuarios, catálogo, inventario, pedidos, pagos, logística e interacción debe conservar integridad y servir también para análisis con SQL y Pandas.
La versión académica utiliza MySQL local y autenticación propia. La ejecución del proyecto se realiza mediante backend Python, interfaz React y un cargador del dataset suministrado. El punto de entrada académico es `backend.academic.main`; los módulos heredados del repositorio se conservan como parte de su historial técnico, pero no definen la persistencia utilizada en este informe.
## 1.2. Objetivos
El objetivo general es implementar y documentar un marketplace funcional que integre programación orientada a objetos, patrones de diseño, una base relacional normalizada, consultas SQL avanzadas y análisis reproducible de datos.
- Modelar las entidades y relaciones comerciales en tercera forma normal, con integridad referencial e índices apropiados.
- Permitir el ciclo de publicación, selección de variantes, cotización, compra y seguimiento del pedido desde la plataforma.
- Aplicar patrones de diseño a decisiones reales de construcción del pedido, descuentos, tarifas, estados y persistencia.
- Resolver preguntas comerciales mediante consultas multitabla, funciones de ventana y análisis Pandas.
- Proporcionar código, scripts, evidencias y un respaldo que permitan ejecutar y revisar el proyecto en otro equipo.
## 1.3. Actores y alcance
| Actor | Responsabilidad y permisos principales |
| --- | --- |
| Visitante | Consultar productos, categorías, variantes y contenido público. |
| Comprador autenticado | Administrar el carrito, confirmar compras, consultar sus pedidos, confirmar recepción y participar en la comunidad. |
| Vendedor autenticado | Publicar productos con variantes, revisar ventas y responder preguntas sobre sus propias publicaciones. |
| Evaluador del proyecto | Revisar el modelo, ejecutar consultas, repetir análisis y comprobar la restauración de la entrega. |
Los pagos, las tarifas y los despachos son educativos y simulados. Las operaciones sí persisten en MySQL y modifican el inventario, pero no procesan dinero ni contratan entregas reales. El diseño contempla un envío consolidado por compra web, aunque el modelo admite varios pagos y envíos por pedido. La página de análisis ofrece reportes académicos, sin atribuir a sus resultados capacidad predictiva o causal automática.
## 1.4. Datos de entrada y cumplimiento
La carpeta del proyecto contiene 15 archivos CSV efectivos, que suman 801.519 filas originales. El pedido inicial se refería a archivos Excel; la carga ejecutable y los conteos de este informe corresponden a los CSV presentes en el repositorio. Se conserva su contenido y no se atribuye a esos archivos una procedencia pública ni un generador que no esté acreditado.
El histórico incluye 111.016 pedidos y 247.482 líneas de detalle. Para demostrar generación reproducible se incorpora además NumPy con semilla 20261118: se cargaron y comprobaron 10.000 pedidos adicionales, con sus relaciones, en la base independiente `tickia_universidad_test`. Esa prueba no se mezcla con el histórico analizado ni con la compra de demostración del respaldo entregado.
| Exigencia académica | Implementación comprobada |
| --- | --- |
| 12 tablas y 3FN | 17 tablas base, PK en todas y 22 FK; dependencias justificadas en el capítulo 4. |
| Dos relaciones N:M | pedido_detalle y favoritos, ambas con PK compuesta. |
| 10.000 registros de hechos | 111.016 pedidos originales; carga reproducible adicional de 10.000 pedidos NumPy en pruebas. |
| Cinco JOIN de tres o más tablas | Diez consultas cumplen ese criterio dentro de trece SQL ejecutables. |
| Dos ventanas y una CTE | Cinco consultas con ventanas; siete con CTE, incluida una recursiva. |
| Dos vistas, procedimiento y trigger | Tres vistas, confirmar_pedido y tr_pedido_validar_estado. |
| Capa Python con clases y tres patrones | Dos Repository integrados y cinco patrones justificados. |
| Índices y evidencia | 48 índices, considerando PK, índices de FK y los índices específicos; EXPLAIN y pruebas reales. |

# 2. Funcionalidades del software
## 2.1. Catálogo, cuenta y publicación
El catálogo permite buscar productos, recorrer categorías y consultar precio, vendedor, variantes e inventario. El acceso y el registro se realizan desde la interfaz. Los usuarios del histórico no reciben contraseñas inventadas: las cuentas operativas se crean mediante el flujo local de autenticación.
Un usuario autenticado puede publicar un artículo para vender. La publicación registra título, categoría, descripción, precio e imagen opcional, y asocia variantes de talla y color con su stock. Se valida que el precio sea positivo y que las cantidades correspondan a enteros admitidos. Una publicación admite hasta veinte variantes; los errores se comunican antes de guardar información inválida.
## 2.2. Carrito, cotización y compra
El acceso al carrito está en la esquina superior derecha del encabezado. El cliente selecciona variantes y cantidades, combina productos de distintos vendedores y consulta un resumen antes de confirmar. El carrito admite hasta veinte variantes y hasta cien unidades por variante; las variantes repetidas se agrupan.
La cotización obtiene los precios e inventarios actuales desde el servidor, aplica descuento por volumen y cupón vigente cuando corresponde, y calcula la tarifa según courier y destino. Los importes se manejan con Decimal y redondeo de mitad hacia arriba a dos decimales. La base vuelve a comprobar las condiciones al confirmar: una cotización anterior no autoriza stock inexistente ni precios manipulados.
La compra genera cabecera, detalle, pago simulado aprobado y envío dentro de una transacción. Una clave UUID por usuario identifica la solicitud y su hash vincula esa clave al contenido. Reintentar la misma solicitud permite recuperar el resultado; reutilizarla con otro contenido produce un conflicto.
## 2.3. Pedidos y comunidad
El comprador consulta sus compras y el vendedor las ventas en que participa. El ciclo operativo pasa por pendiente, pagado, enviado y entregado. El despacho se simula desde el seguimiento; la recepción corresponde exclusivamente al comprador. Las transiciones no autorizadas se rechazan tanto en Python como mediante el trigger de MySQL. El modelo admite cancelado como estado terminal; la interfaz demostrada no ofrece una operación general de cancelación y reembolso.
La comunidad integra preguntas, respuestas del propietario, reseñas y favoritos. La publicación de una reseña requiere una compra entregada y no permite duplicar la reseña del mismo usuario sobre el producto. La comprobación de propiedad limita quién puede responder una pregunta de una publicación.
## 2.4. Análisis y exportación
El panel Análisis permite seleccionar dieciocho reportes y descargar sus resultados completos en CSV. Incluye segmentación RFM, cohortes, productos comprados juntos, entregas, reputación y ventas, además de ranking, evolución mensual, stock crítico y otros reportes SQL. El cuaderno Jupyter entregado ejecuta las transformaciones y genera tablas y gráficos a partir de MySQL.
| Operación | Resultado persistente o verificable |
| --- | --- |
| Publicar | Producto asociado a vendedor y categoría, con variantes e inventario. |
| Comprar | Pedido con líneas, pago y envío; descuento atómico del stock. |
| Repetir confirmación | Recuperación idempotente de una solicitud ya procesada. |
| Despachar y recibir | Cambio válido de estado y fechas de envío/entrega. |
| Participar | Preguntas, respuestas, reseñas y favoritos ligados por FK. |
| Analizar | Tablas, gráficos y CSV con criterios y denominadores explícitos. |

# 3. Marco teórico
## 3.1. Modelo relacional y normalización
El modelo relacional organiza información en tablas identificadas por claves. Una clave primaria identifica cada fila y una foránea vincula una referencia con una fila existente. Las relaciones N:M se representan mediante tablas intermedias, en lugar de listas de identificadores dentro de una celda.
La primera forma normal exige valores atómicos dentro del dominio elegido. La segunda elimina dependencias de una parte de una clave compuesta. La tercera elimina dependencias transitivas indebidas entre atributos no clave. La finalidad práctica es reducir inconsistencias al insertar, actualizar o borrar información [1]. La justificación de 3FN requiere conocer las dependencias del negocio; el número de tablas por sí solo no la demuestra.
En Tickia, separar provincia y departamento evita repetir sus nombres en cada distrito. Separar variantes permite registrar stock por talla y color. Conservar el precio acordado en el detalle permite consultar una compra histórica aunque cambie el precio vigente del producto.
## 3.2. Objetos, composición y patrones
Una clase reúne estado y operaciones; la herencia permite especializar comportamiento y la composición permite construir objetos a partir de otros [3]. En el dominio del proyecto se usan objetos de pedido y contratos de precio, tarifa y estado. Las dataclasses inmutables del borrador reducen modificaciones accidentales entre la cotización y la confirmación.
Un patrón de diseño describe una solución reutilizable para una estructura de colaboración. Builder organiza la construcción de un objeto; Strategy intercambia algoritmos; Decorator añade comportamiento mediante envolturas; State delega operaciones según un estado [7]. Repository ofrece una interfaz de persistencia centrada en los datos que necesita el dominio [8].
En esta aplicación la selección tiene efectos observables: Builder agrupa variantes y genera el borrador; Strategy decide la tarifa; Decorator acumula descuentos; State valida las acciones del pedido; Repository encapsula consultas y la llamada al procedimiento. Sus clases se utilizan en el flujo comercial y se muestran en los diagramas del capítulo 4.
## 3.3. Integridad, transacciones e índices
Una compra requiere atomicidad: si falla una línea, no deben quedar pagos, pedidos parciales ni inventarios descontados. InnoDB y la transacción del procedimiento coordinan esos cambios. Los bloqueos y las actualizaciones condicionadas de stock evitan que dos solicitudes consuman la misma última unidad. La confirmación se hace efectiva al completar la transacción; los errores revierten el conjunto [2].
Una vista conserva una definición de consulta y presenta datos calculados sin mantener otra tabla de resultados manualmente. Un procedimiento agrupa operaciones ejecutadas en el servidor; un trigger responde a una modificación de tabla. En este proyecto el trigger también protege frente a un UPDATE directo que intente saltar estados [2].
Los índices permiten localizar filas y apoyar uniones u ordenamientos concretos. Su utilidad depende de columnas, selectividad y plan de ejecución; por eso se aporta EXPLAIN. El índice de stock ayuda al filtro crítico y el compuesto por usuario/fecha apoya el historial. No se afirma que un índice B-tree acelere cualquier búsqueda textual con LOCATE.
## 3.4. SQL avanzado
JOIN combina relaciones por claves. Antes de cruzar ventas, reseñas y envíos es necesario respetar la granularidad: unir cada línea de venta con cada reseña multiplicaría importes. El diagnóstico calcula los agregados por separado y después los relaciona por vendedor.
Las CTE nombran resultados intermedios y facilitan expresar etapas de cálculo. WITH RECURSIVE recorre la jerarquía de categorías. Las funciones de ventana conservan las filas del resultado mientras calculan posiciones, valores anteriores o acumulados: RANK admite empates con saltos, DENSE_RANK evita esos saltos, LAG compara observaciones y SUM OVER calcula acumulaciones dentro de una partición [2].
## 3.5. Acceso Python y arquitectura web
FastAPI expone las operaciones HTTP; SQLAlchemy administra conexiones y consultas parametrizadas; PyMySQL comunica Python con MySQL [4, 9]. React presenta las vistas y el estado de interacción [10]. Los Repository reciben conexiones por constructor, lo que permite mantener las reglas de precio y estado independientes de la forma concreta de consultar los datos.
La parametrización separa valores de instrucciones SQL. La aplicación combina ese mecanismo con validaciones de entrada y permisos por usuario. Las sesiones locales usan cookies HttpOnly y las contraseñas se conservan mediante hashes, no como texto plano. Las claves de configuración se generan localmente y no forman parte del paquete de entrega.
## 3.6. Análisis con Pandas y NumPy
Pandas permite leer resultados SQL y transformar DataFrames con agrupación, uniones, tablas dinámicas y cálculo de indicadores [5]. NumPy aporta generación seudorrandómica con semilla, utilizada aquí para crear una carga reproducible y verificar invariantes sin alterar el histórico [6].
RFM describe recencia, frecuencia y valor monetario; una cohorte agrupa clientes según su primera compra y compara retornos en meses posteriores. La afinidad usa soporte, confianza y lift para describir coincidencias de productos en canastas [11]. Estas métricas permiten formular acciones comerciales que deberían evaluarse antes de aplicarse como decisiones definitivas.
La tasa de retraso es una proporción estimada. El intervalo de Wilson expresa incertidumbre de esa proporción, considerando tamaño de muestra [12]. Una correlación resume asociación lineal; no demuestra que el courier, el vendedor o un atraso concreto haya causado una reseña.

# 4. Modelo entidad-relación y diagramas UML
## 4.1. Arquitectura implementada
La interfaz solicita operaciones al backend académico, que aplica reglas de negocio y consulta MySQL. El cargador inicial transforma los archivos fuente al esquema normalizado. Pandas reutiliza la misma base para generar reportes. El diagrama identifica componentes reales; las rutas que no pertenecen a compras también pueden utilizar SQLAlchemy Core directamente.
![Arquitectura de ejecución local de Tickia. Elaboración propia sobre los módulos implementados.](diagramas/arquitectura.png)
## 4.2. Entidades y relaciones
El esquema tiene diecisiete tablas y veintidós claves foráneas. Los dos catálogos geográficos adicionales se derivan del archivo de distritos. El diagrama siguiente prioriza nombres y claves para mantener legibilidad; el anexo A incluye todos los atributos físicos y sus tipos. Las multiplicidades muestran restricciones de la base; las reglas de la aplicación añaden, por ejemplo, que una compra confirmada tenga al menos una línea.
![Modelo entidad-relación: diecisiete tablas; tablas puente destacadas y veintidós relaciones.](diagramas/modelo_er.png)
| Grupo | Tablas y propósito |
| --- | --- |
| Geografía | departamentos, provincias y distritos: ubicación jerárquica. |
| Personas | usuarios y vendedores: identidad, cuenta y perfil comercial. |
| Catálogo | categorias, productos y variantes: clasificación, publicación y stock. |
| Operación comercial | cupones, pedidos, pedido_detalle y pagos: condiciones e importes históricos. |
| Logística | couriers y envios: tarifa y fechas de seguimiento. |
| Comunidad | resenas, preguntas y favoritos: evaluación e interés sobre productos. |
`pedido_detalle` vincula pedidos y variantes mediante su PK `(id_pedido, id_variante)`. `favoritos` vincula usuarios y productos mediante `(id_usuario, id_producto)`. Las dos relaciones resuelven N:M con integridad referencial. Las categorías incluyen una FK a su categoría padre y permiten recorrer el árbol.
## 4.3. Dependencias funcionales y 3FN
En las tablas con identificador simple, este determina los atributos propios de la entidad. Por ejemplo, id_producto determina vendedor, categoría, título y precio actual; id_variante determina producto, talla, color y stock. Los atributos descriptivos del vendedor o de la categoría no se duplican en productos.
En `pedido_detalle`, cantidad y precio_unit dependen de la combinación completa pedido/variante. El precio del detalle es un valor pactado en esa compra, no una copia funcional del precio actual del producto. En `favoritos`, la fecha depende de la combinación usuario/producto. Así se evitan dependencias parciales en las claves compuestas.
La jerarquía geográfica se representa como distrito → provincia → departamento, guardando solo la FK de cada nivel. No se supone que el nombre de una provincia sea único en todo el país. La clave alternativa de provincias es `(id_departamento, nombre)` y la de departamentos es nombre.
Se retiran de pedidos los campos redundantes subtotal, descuento, costo_envio y destino JSON. La vista `v_pedidos_importes` los obtiene desde detalle, envío y geografía. El total acordado permanece como hecho histórico: no puede sustituirse por un precio actual que podría cambiar. El origen distingue que el total de los pedidos fuente excluye envío, mientras el de web y NumPy lo incluye.
`auth_email` es una columna generada para un índice de unicidad condicional de cuentas con contraseña. Es una representación técnica no editable, no otro origen lógico del email. El histórico contiene emails repetidos; por ello no se establece una unicidad global incorrecta sobre toda la fuente. La reputación registrada y el promedio calculado de estrellas se consideran medidas distintas.
Estas decisiones justifican 3FN según las dependencias del dominio. Las comprobaciones automáticas verifican PK, FK y estructura; no sustituyen esta explicación semántica. El documento complementario `NORMALIZACION_3FN.md` detalla las dependencias de las diecisiete relaciones y la migración comprobada.
## 4.4. UML y patrones utilizados
Los diagramas emplean compartimentos de atributos y operaciones, generalización mediante triángulo vacío y asociaciones de colaboración [13]. Se incluyen las clases que participan en los patrones, no todas las clases de las bibliotecas externas. Los métodos y relaciones corresponden a `patterns.py`, `repositories.py` y su integración en `commerce.py`.
![Clases de Builder, Strategy y Decorator en el flujo de cotización.](diagramas/uml_builder_strategy_decorator.png)
Builder permite añadir líneas, cupón y tarifa en pasos separados y producir un OrderDraft inmutable. La agrupación de variantes repetidas evita duplicar líneas. Strategy permite cambiar entre StandardShipping, ExpressShipping y EconomyShipping sin insertar sus fórmulas en el controlador HTTP.
Decorator usa una implementación base de precio y envolturas PercentageDiscount. La primera aplica 3% por tres unidades o más; la segunda aplica el cupón sobre el importe ya reducido. El desglose conserva cuánto descontó cada paso. No se suman porcentajes como si actuaran sobre una misma base.
![Clases State: contexto, clase base y cinco estados concretos del pedido.](diagramas/uml_state.png)
OrderContext delega la transición en el estado actual. PendingState permite pagar; PaidState permite despachar; ShippedState permite recibir. DeliveredState y CancelledState son terminales. La clase base OrderState hereda ABC, pero no declara métodos abstractos: el diagrama la identifica como clase base. El SQL también admite pendiente → cancelado, aunque el flujo web demostrado utiliza pago, despacho y recepción.
![Repository y sus conexiones con catálogo, pedidos y el módulo comercial.](diagramas/uml_repository.png)
CatalogRepository obtiene variantes, cupón, courier y distrito. OrderRepository consulta recibos, permisos e historial, bloquea estados y llama al procedimiento. Las conexiones se inyectan por constructor. La confirmación usa una conexión transaccional propia porque el procedimiento controla la transacción; los errores se propagan para que el controlador construya la respuesta HTTP.
![Ciclo del pedido y acciones de demostración; las transiciones inválidas se rechazan.](diagramas/ciclo_pedido.png)
| Patrón | Problema resuelto | Evidencia de integración |
| --- | --- | --- |
| Builder | Componer un pedido multítem coherente. | OrderBuilder usado al cotizar y confirmar. |
| Strategy | Variar tarifas sin modificar la composición del pedido. | Tres ShippingStrategy seleccionadas por courier. |
| Decorator | Aplicar descuentos secuenciales y conservar su desglose. | BasePrice y PercentageDiscount dentro de build. |
| State | Limitar acciones según el estado actual. | OrderContext en checkout y advance. |
| Repository | Aislar consultas de catálogo y compras. | CatalogRepository y OrderRepository usados por commerce. |

# 5. Capturas de funcionamiento del software
## 5.1. Condiciones de la demostración
Las capturas se obtuvieron el 18-11-2026 mediante Chromium sobre una copia independiente del dataset. Se utilizaron tres cuentas ficticias y dos productos universitarios. La sesión de evidencia se abrió en el puerto 5202 para mantener separado el trabajo cotidiano; el puerto mostrado en una captura no constituye un requisito de instalación.
La demostración recorre publicación, selección de variantes, carrito de dos vendedores, descuentos, compra, despacho, recepción y comunidad. Los mismos datos se incluyen en el respaldo. Las capturas siguientes son evidencia de ejecución de la aplicación; no son bocetos de interfaz.
![Catálogo Tickia con acceso al carrito en la esquina superior derecha.](figuras/01_catalogo.png)
![Pantalla de acceso con una cuenta ficticia de la demostración.](figuras/02_acceso.png)
![Formulario de publicación de un producto con categoría, precio y variantes.](figuras/03_publicacion.png)
![Detalle de la mochila y selección de talla, color y cantidad disponible.](figuras/04_detalle_variantes.png)
![Carrito con productos de dos vendedores y tres variantes.](figuras/05_carrito.png)
## 5.2. Cálculo del pedido de prueba
Se compraron dos mochilas medianas, una mochila grande y un cuaderno: cuatro unidades de dos productos y dos vendedores, distribuidas en tres líneas. El envío rápido corresponde al courier Shalom y al distrito de Cusco. Los importes se comprobaron en la cotización, el recibo y la copia restaurada.
| Concepto | Operación o valor en soles |
| --- | --- |
| Artículos | 3 × 89,90 + 1 × 12,50 = 282,20 |
| Descuento por volumen | 3% de 282,20, redondeado: 8,47 |
| Base tras volumen | 273,73 |
| Cupón INVIERNO981 | 5% de 273,73, redondeado: 13,69 |
| Artículos tras descuentos | 260,04 |
| Envío rápido fuera de Lima | 9,50 × 1,75 + 0,50 × 4 = 18,63, redondeado |
| Total confirmado | **278,67** |
El pedido 111017 registra ese total, un pago de demostración aprobado y un envío. Su estado final en el respaldo es entregado. Los stocks iniciales 5, 4 y 8 de las variantes utilizadas quedaron en 3, 3 y 7. La confirmación fue comprobada sin duplicar la compra al repetir la captura.
![Resumen de pago con cupón, descuento por volumen, destino y total de S/278,67.](figuras/06_resumen_pago.png)
![Compra confirmada y pago simulado aprobado.](figuras/07_compra_pagada.png)
![Seguimiento tras simular el despacho del pedido.](figuras/08_despacho.png)
![Confirmación de recepción y pedido entregado.](figuras/09_recepcion.png)
## 5.3. Comunidad y análisis en la interfaz
Después de recibir el pedido, el comprador calificó la mochila con cinco estrellas y formuló una pregunta sobre el compartimento para laptop. El propietario respondió desde su cuenta. También se marcó un producto como favorito. Estas acciones se conservan en las tablas de comunidad de la copia entregada.
![Comunidad del producto: reseña, pregunta y favorito del comprador.](figuras/10_comunidad.png)
![Respuesta del vendedor propietario a la pregunta sobre su producto.](figuras/11_respuesta_vendedor.png)
![Reporte de vendedores con ventas altas, mala reputación y entregas tardías.](figuras/12_diagnostico.png)
![Segmentación RFM disponible en la plataforma y exportación de resultados.](figuras/13_rfm_aplicacion.png)
![Catálogo en vista móvil; navegación y carrito adaptados al ancho disponible.](figuras/14_movil.png)

# 6. Script SQL de la base de datos
## 6.1. Organización y carga
Los scripts del proyecto utilizan MySQL 8.4 e InnoDB. `01_esquema.sql` crea tablas y restricciones; `05_indices.sql` agrega índices; `04_vistas.sql` define las tres vistas; `02_procedimientos.sql` contiene la confirmación transaccional; `06_trigger.sql` instala el control de estados. `03_consultas.sql` reúne las trece consultas analíticas.
La carga inicial no depende de Excel instalado. `academic/bootstrap.py` lee los quince CSV, valida relaciones, transforma los catálogos geográficos y conserva los identificadores. La huella de las fuentes permite detectar una importación existente. El proceso no vuelve a insertar el histórico en cada inicio ni sustituye el inventario que cambió con las compras.
La entrega incluye dos vías concretas: cargar los CSV con el inicializador del proyecto, o restaurar `tickia_universidad_completa.sql`. El respaldo contiene creación e INSERT de las 801.586 filas de la copia final, además de vistas, procedimiento y trigger. No se imprimen cientos de miles de INSERT en el cuerpo de Word; el archivo SQL íntegro forma parte del paquete. `SQL_estructura_objetos.sql` reúne el DDL y los objetos programables en un archivo ejecutable sobre una base vacía ya seleccionada.
La copia final tiene 67 filas más que las fuentes originales: 48 de catálogos geográficos derivados y 19 del recorrido de demostración. Contiene 111.017 pedidos, de los cuales 111.016 son originales y uno es web. Los 10.000 pedidos NumPy corresponden a la base de pruebas y no se añaden a esa copia para no alterar las métricas originales.
## 6.2. Creación, índices, vistas, procedimiento y trigger
El siguiente listado reproduce los scripts de estructura y objetos de la entrega. Los delimitadores permiten ejecutar los cuerpos compuestos del procedimiento y el trigger en un cliente MySQL que los interprete. Debe seleccionarse una base de trabajo vacía antes de ejecutar el listado.
{{ESTRUCTURA}}
## 6.3. Consultas avanzadas completas
Se incluyen trece consultas identificadas con `-- name:`. Diez reúnen al menos tres tablas base distintas; cinco emplean funciones de ventana y siete usan CTE. La auditoría distingue tablas físicas, vistas, alias y resultados intermedios para evitar inflar esos conteos.
| Consulta | Técnica y finalidad |
| --- | --- |
| categorias | CTE recursiva para ruta y profundidad del árbol. |
| ventas_distrito | Uniones de ventas, catálogo, usuario y geografía. |
| stock | Tres tablas para variantes agotadas o críticas. |
| diagnostico_sql | Agregados separados de ventas, opinión y entregas. |
| resenas_producto | Cuatro tablas para estrellas por producto y categoría. |
| favoritos_categoria | Interés por categoría y vendedor, con conteos distintos. |
| entregas_departamento | Courier, envío, pedido, usuario y geografía. |
| ranking_vendedores | RANK y acumulado SUM OVER. |
| ventas_mensuales | LAG y acumulación por vendedor. |
| clientes_inactivos | CTE encadenadas, LAG y prioridad DENSE_RANK. |
| participacion_categorias | Participación, ranking y concentración acumulada. |
| riesgo_courier | Muestras mínimas, Wilson, dispersión y ranking por departamento. |
| afinidad_sql | Canastas deduplicadas, autounión, soporte, confianza y lift. |
{{CONSULTAS}}
## 6.4. Decisiones de exactitud
Las consultas históricas filtran origen dataset y estados pagado, enviado o entregado. El reporte de stock muestra el inventario actual. Las ventas brutas son cantidad por precio acordado: no equivalen a utilidad y no incluyen costos de adquisición, que no están en la fuente.
LAG se particiona por vendedor o comprador para no cruzar historiales. En ventas mensuales compara meses observados y no agrega silenciosamente meses sin movimiento. Los acumulados usan un desempate por ID para que su orden sea determinista. La afinidad deduplica productos por pedido antes de combinar pares; varias tallas no se cuentan como productos diferentes.

# 7. Evidencias de base de datos, consultas y análisis Pandas
## 7.1. Ejecución reproducible
El cuaderno `Analisis_Tickia.ipynb` contiene diecinueve celdas de código ejecutadas sin errores. Se adjunta también su exportación HTML para consultar resultados sin instalar Jupyter. Las imágenes del cuaderno muestran código y salidas reales, obtenidos por nbclient sobre MySQL. No contienen contraseñas ni cadenas de conexión.
Se utilizaron Python 3.13, MySQL 8.4.13, Pandas 3.1.1 y NumPy 2.5.0. Las dependencias de la aplicación se conservan en requirements y package-lock; las herramientas de elaboración del informe se documentan por separado. Los CSV exportados incluyen las salidas completas, aunque las capturas presentan muestras para facilitar lectura.
![Consulta de conteos de las diecisiete tablas en la base de demostración.](figuras/15_bd_conteos.png)
![Claves foráneas consultadas desde information_schema; salida del cuaderno ejecutado.](figuras/16_bd_relaciones.png)
![Comprobación de las tres vistas, el procedimiento y el trigger en MySQL.](figuras/17_bd_objetos.png)
![Ranking de vendedores con función de ventana y ventas acumuladas.](figuras/18_sql_ranking.png)
![Resultados SQL de comparación temporal con LAG y acumulados.](figuras/19_sql_ventanas.png)
![Plan EXPLAIN de una consulta indexada; evidencia del plan elegido por MySQL.](figuras/20_sql_indices.png)
## 7.2. Población y preparación
El análisis histórico usa 45.000 clientes, 700 vendedores, 98.871 pedidos válidos, 40.071 reseñas y 96.288 entregas con fechas consistentes. Se excluyen pendientes y cancelados. Las tres cuentas ficticias y la compra web permanecen fuera de los indicadores históricos por los filtros de origen e identidad de la fuente.
La fecha de referencia para recencia es el 01-10-2026, día posterior a la última compra del conjunto. No se usa la fecha actual del equipo: así repetir el cuaderno no altera arbitrariamente la segmentación. Se comprueban fechas ausentes, recepciones anteriores al despacho y duplicaciones de productos o clientes dentro de cada unidad de análisis.
![Resumen de población y criterios calculados con Pandas.](figuras/21_pandas_resumen.png)
## 7.3. Segmentación RFM
Para cada cliente, R es la cantidad de días desde su última compra, F es el número de pedidos distintos y M es el total comprado. Los puntajes de uno a cinco se construyen con rangos percentiles y empates promediados; una recencia menor recibe un mejor puntaje. Los clientes sin compras se mantienen con frecuencia, valor y puntajes cero.
Las reglas se evalúan en orden: sin compras; campeones si la suma de puntajes alcanza trece; en riesgo si R es como máximo dos y F al menos tres; leales si F es al menos cuatro; nuevos si R es al menos cuatro y F como máximo dos; los demás son ocasionales. Son reglas del proyecto y deben calibrarse antes de usarse en un negocio real.
| Segmento | Clientes | Lectura comercial posible |
| --- | --- | --- |
| Sin compras | 20.714 | Revisar activación y barreras para la primera compra. |
| Ocasionales | 10.680 | Evaluar recomendaciones y recurrencia. |
| Campeones | 4.962 | Cuidar experiencia y continuidad de servicio. |
| Leales | 3.075 | Mantener disponibilidad y consistencia. |
| En riesgo | 2.796 | Investigar la interrupción de una frecuencia previa. |
| Nuevos | 2.773 | Acompañar la segunda compra. |
Las cantidades suman los 45.000 clientes. Un segmento no autoriza por sí mismo descuentos ni permite concluir por qué un cliente dejó de comprar.
![Tabla RFM calculada en el cuaderno con identificadores, indicadores y segmentos.](figuras/22_pandas_rfm.png)
![Distribución de los segmentos RFM del histórico original.](figuras/grafico_rfm.png)
## 7.4. Cohortes y retención
La cohorte corresponde al mes de la primera compra. La retención de un mes es clientes distintos que regresaron dividido entre clientes de esa cohorte. El mes cero tiene 100%; los meses observados sin retorno tienen cero y los meses todavía no expuestos se excluyen. La agregación global pondera por el tamaño expuesto de las cohortes, en vez de promediar porcentajes de bases distintas.
Se obtienen 33 cohortes de enero de 2024 a septiembre de 2026 y 561 celdas observadas. La retención ponderada es 22,26% al mes uno, 11,33% al mes tres y 12,15% al mes seis. Estas cifras describen poblaciones expuestas diferentes en cada horizonte; una diferencia entre meses no implica que un mismo conjunto completo de clientes haya recuperado actividad.
![Salida Pandas de cohortes con bases expuestas y retención.](figuras/23_pandas_cohortes.png)
![Mapa de retención de las doce cohortes recientes; meses futuros sin valor.](figuras/grafico_cohortes.png)
## 7.5. Afinidad de productos
Se construye un conjunto de productos por pedido y se cuentan pares distintos. Soporte(A,B) = pedidos con ambos / pedidos válidos con artículos; confianza(A→B) = pedidos con ambos / pedidos con A; lift = confianza(A→B) / proporción de pedidos con B. La dirección importa para la confianza y el lift compara la coincidencia con una referencia de independencia [11].
El primer par por número de pedidos conjuntos es Coches de bebé Huggies Edición Especial y Biberones Babysec Max: 563 pedidos, soporte 0,5694%, confianza A→B 24,50% y lift 22,1012. Una asociación alta con soporte bajo no garantiza una promoción rentable. Las coincidencias describen el conjunto suministrado y requieren validación comercial.
El reporte SQL entrega hasta cien pares con al menos cinco pedidos conjuntos. La salida completa Pandas conserva todos los pares calculados y permite examinar también los de menor frecuencia.
![Tabla de co-compras con soporte, confianza y lift, generada con Pandas.](figuras/24_pandas_afinidad.png)
![Pares con más pedidos conjuntos; el eje representa conteos, no causalidad.](figuras/grafico_cocompras.png)
## 7.6. Entregas y riesgo de courier
Los días de entrega se calculan como recepción menos despacho. Se excluyen fechas ausentes o incoherentes. La entrega el mismo día prometido es puntual y la tasa tardía se divide únicamente entre envíos con promesa conocida. La ubicación del histórico procede del distrito del usuario: la fuente no dispone de otra dirección histórica de entrega.
Entre los cruces con más observaciones, Chazki en Lima presenta 18.061 envíos, una media de 1,27 días y 12,01% tardíos. Olva Courier en Lima tiene 13.069 envíos, 2,34 días y 36,88% tardíos. Estos valores no están ajustados por distancia, tipo de producto o dificultad de ruta; no justifican por sí solos una comparación causal de desempeño.
La consulta avanzada conserva grupos courier/departamento con al menos treinta envíos y calcula un intervalo de Wilson al 95%, con z = 1,96 [12]. En la ejecución se obtienen 128 grupos elegibles. El intervalo supone observaciones aproximadamente independientes; factores compartidos y varios envíos de un pedido limitan su interpretación.
![Agrupación Pandas de entregas por courier y departamento, con denominadores.](figuras/25_pandas_entregas.png)
![Tasas tardías agregadas por courier; gráfico descriptivo del histórico.](figuras/grafico_couriers.png)
## 7.7. Ventas, reputación y retrasos
La pregunta central del caso es: ¿qué vendedores tienen buenas ventas y mala reputación asociada con entregas tardías? Se exigen al menos diez pedidos, ventas en el cuartil superior de vendedores elegibles, menos de 3,5 estrellas y al menos 25% de pedidos tardíos entre los de promesa conocida.
El umbral de ventas altas es S/42.644,91. Catorce vendedores cumplen simultáneamente los criterios. La correlación de Pearson entre estrellas promedio y porcentaje de retrasos es −0,751 sobre 393 vendedores elegibles con ambas medidas. El CSV diagnóstico conserva los catorce casos y sus conteos de pedidos y reseñas.
El resultado es una señal para investigar, no una prueba de causa. Las reseñas identifican producto y usuario, pero no pedido. Un pedido puede agrupar varios vendedores y su atraso se asocia una vez a cada vendedor participante. No se atribuye a un vendedor responsabilidad exclusiva ni se vincula una reseña concreta con un envío sin una relación que la fuente no contiene.
![Diagnóstico Pandas: criterios aplicados y muestra de vendedores detectados.](figuras/26_pandas_diagnostico.png)
![Asociación entre retrasos y estrellas; 393 vendedores y correlación descriptiva.](figuras/grafico_reputacion.png)
## 7.8. Ampliaciones analíticas
El ranking incorpora 676 vendedores con ventas; la serie mensual tiene 8.130 filas; la consulta de inactividad detecta 4.023 clientes. Esta última requiere al menos tres pedidos y recencia superior al máximo entre treinta días y el doble del intervalo medio entre compras. La prioridad refleja valor histórico; no es una predicción individual de abandono.
La participación de categorías genera 75 filas y su acumulado final alcanza 100%. La consulta de afinidad SQL devuelve cien pares conforme al límite establecido. Estos reportes amplían el mínimo académico y permiten comparar cálculos SQL con transformaciones Pandas sin confundir sus poblaciones o límites de presentación.
![Salidas ejecutadas de los reportes avanzados, incluida inactividad y riesgo.](figuras/27_sql_avanzado.png)

# 8. Conclusiones
El proyecto implementa un marketplace que permite publicar artículos y comprarlos dentro de la misma plataforma. La evidencia recorre una compra multivendedor con variantes, descuentos, pago simulado, despacho, recepción e interacción posterior. La operación persiste y el inventario se actualiza de forma consistente.
El modelo satisface los requisitos estructurales mediante diecisiete tablas, veintidós FK y dos relaciones N:M. La separación geográfica y la eliminación de importes redundantes en pedidos se justifican mediante dependencias funcionales. Las tres vistas permiten reconstruir información para lectura sin introducir otra fuente editable de los mismos datos.
Los cinco patrones están integrados en funciones reales. Builder y Decorator mantienen la composición y el desglose de la cotización; Strategy permite intercambiar tarifas; State limita acciones; Repository separa las consultas del flujo comercial. La transacción y el trigger refuerzan reglas críticas en la base.
Las consultas y el análisis aportan resultados reproducibles sobre la fuente: segmentación de 45.000 clientes, 33 cohortes, asociaciones de productos y catorce vendedores que cumplen el diagnóstico. Se controla la granularidad para evitar duplicar dinero y se explicitan filtros, fechas y denominadores.
La entrega incluye un respaldo restaurado y verificado en una instancia independiente, con los mismos conteos y objetos, así como el acceso y pedido de prueba comprobados. Esto permite evaluar el proyecto más allá de las capturas.
El alcance sigue siendo académico. Una puesta en producción requeriría proveedores reales de pago y logística, políticas completas de devolución, protección operativa de cuentas, trazabilidad por envío y mayor cobertura de monitoreo. Para mejorar el análisis convendría registrar la dirección de entrega histórica, vincular reseñas con compras cuando corresponda y disponer de costos para calcular margen. Las asociaciones observadas no demuestran causalidad ni rentabilidad.

# 9. Código fuente Python y archivos SQL
## 9.1. Organización entregada
El paquete contiene código ejecutable completo, no solo los fragmentos del informe. `codigo_fuente/Pagina Web/backend/academic` reúne el backend académico; `codigo_fuente/Pagina Web/frontend` contiene la interfaz; `codigo_fuente/Proyecto_PrograAvanzada` incluye dataset, SQL, documentación y lanzadores. Los directorios de entornos virtuales, node_modules, secretos y archivos temporales se excluyen.
| Archivo o módulo | Responsabilidad |
| --- | --- |
| academic/main.py | Aplicación FastAPI académica y configuración de rutas. |
| academic/bootstrap.py y schema_upgrade.py | Creación, importación y adecuación al modelo normalizado. |
| academic/catalog.py | Catálogo, publicaciones y variantes. |
| academic/auth.py | Acceso y cuentas locales. |
| academic/commerce.py | Cotización, confirmación, historial y estados. |
| academic/patterns.py | Builder, Strategy, Decorator y State. |
| academic/repositories.py | Acceso de catálogo y pedidos mediante clases. |
| academic/social.py | Reseñas, preguntas, respuestas y favoritos. |
| academic/analytics.py | Reportes Pandas y ejecución de reportes SQL. |
| academic/generation.py y audit.py | Generación reproducible y auditoría de requisitos. |
| sql/01 a 06 | Esquema, procedimiento, consultas, vistas, índices y trigger. |
| notebooks/Analisis_Tickia.ipynb | Ejecución y visualización reproducible del análisis. |
## 9.2. Implementación de los patrones del dominio
Se reproduce íntegramente `patterns.py`, por ser el núcleo de los patrones exigidos. Sus reglas se utilizan en el flujo de compras y están cubiertas por pruebas de comportamiento. El resto del código se entrega en sus archivos originales dentro del paquete.
{{PATRONES}}
## 9.3. Implementación de Repository
El siguiente listado corresponde al archivo completo `repositories.py`. Encapsula consultas parametrizadas y la confirmación transaccional. El módulo comercial decide las respuestas HTTP y las reglas de acceso, apoyándose en los métodos de estas clases.
{{REPOSITORIES}}
## 9.4. Reproducción del generador
La generación NumPy usa clientes recurrentes, popularidad desigual, cantidades variables y tiempos de entrega. La semilla permite repetir el mismo conjunto. El cargador restringe la escritura a `tickia_universidad_test` y comprueba si ya existe la carga. Ejecutar de nuevo no duplica los diez mil pedidos ni cambia el stock del histórico.
La evidencia de generación se adjunta en `codigo_fuente/Proyecto_PrograAvanzada/entregables/resultados/generacion_numpy.json`; la comprobación integral se invoca con `python Proyecto_PrograAvanzada/verificar.py` desde el entorno configurado. No se presupone que los CSV suministrados fueron creados con Faker o NumPy: el generador propio acredita esa parte de la rúbrica por separado.

# 10. Bibliografía
Las fuentes se utilizaron para conceptos y APIs; las cifras, capturas, diagramas y evaluaciones del proyecto proceden de su ejecución. Consulta de las referencias web: 18 de noviembre de 2026.
[1] Microsoft. Descripción de los aspectos básicos de la normalización de bases de datos. https://learn.microsoft.com/en-us/previous-versions/troubleshoot/microsoft-365/microsoft-365-apps/access/database-normalization-description
[2] Oracle. MySQL 8.4 Reference Manual. Secciones sobre InnoDB, vistas, procedimientos, triggers, CTE y funciones de ventana. https://dev.mysql.com/doc/refman/8.4/en/
[3] Python Software Foundation. The Python Tutorial, 9. Classes, Python 3.13. https://docs.python.org/3.13/tutorial/classes.html
[4] SQLAlchemy. Working with Engines and Connections, documentación 2.0. https://docs.sqlalchemy.org/en/20/core/connections.html
[5] The pandas development team. pandas.read_sql_query y documentación de análisis de datos. https://pandas.pydata.org/docs/reference/api/pandas.read_sql_query.html
[6] NumPy Developers. Random Generator, documentación de referencia. https://numpy.org/doc/stable/reference/random/generator.html
[7] Gamma, E.; Helm, R.; Johnson, R.; Vlissides, J. (1994). Design Patterns: Elements of Reusable Object-Oriented Software. Addison-Wesley. Ficha editorial: https://www.pearson.com/en-us/subject-catalog/p/design-patterns-elements-of-reusable-object-oriented-software/P200000009480
[8] Fowler, M. (2003). Repository. Patterns of Enterprise Application Architecture, catálogo en línea. Patrón atribuido en la ficha a Edward Hieatt y Rob Mee. https://martinfowler.com/eaaCatalog/repository.html
[9] FastAPI. Documentación oficial. https://fastapi.tiangolo.com/
[10] React. Learn React, documentación oficial. https://react.dev/learn
[11] Agrawal, R.; Srikant, R. (1994). Fast Algorithms for Mining Association Rules. Proceedings of the 20th VLDB Conference, pp. 487–499. https://www.vldb.org/conf/1994/P487.PDF
[12] NIST/SEMATECH. e-Handbook of Statistical Methods, 7.2.4.1. Confidence intervals. Método de Wilson para proporciones. https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm
[13] Object Management Group (2017). Unified Modeling Language, versión 2.5.1. https://www.omg.org/spec/UML/2.5.1/

# 11. Anexos
## 11.1. Anexo A: diccionario físico de datos
El diccionario se obtuvo de information_schema sobre la copia respaldada. PRI indica pertenencia a PK; UNI indica índice único individual según la representación del motor y MUL un índice no único o participación en una clave compuesta. Las FK y restricciones compuestas se definen con precisión en el DDL del capítulo 6; la etiqueta MUL aislada no sustituye esa definición. La columna generada auth_email se interpreta como representación técnica del índice condicional.
{{DICCIONARIO}}
## 11.2. Anexo B: respaldo y restauración comprobada
El respaldo utiliza el nombre portable `tickia_universidad` e incluye datos y objetos programables. Se retiraron cláusulas DEFINER para evitar depender de una cuenta del equipo de desarrollo. No contiene cuentas personales de trabajo: las únicas cuentas con autenticación son las tres ficticias de la demostración. La configuración y las contraseñas de conexión se generan en el equipo receptor.
{{RESPALDO}}
La prueba levantó un contenedor MySQL temporal independiente, importó el archivo íntegro y comparó los conteos de las diecisiete tablas. Se comprobaron tres vistas, veintidós FK, un procedimiento y un trigger. Una actualización inválida de estado fue rechazada. Después se inicializó el backend sobre esa copia, se inició sesión con el comprador ficticio y se verificó el pedido entregado por S/278,67. El contenedor temporal se cerró al concluir; el resultado completo se adjunta en `respaldo/validacion_respaldo.json`.
## 11.3. Anexo C: pruebas del software
| Verificación | Resultado y alcance |
| --- | --- |
| Pruebas académicas puras | 13 correctas: reglas, importes, denominadores y patrones. |
| Integración MySQL real | 14 correctas: FK, compra, rollback, concurrencia, migración y trigger. |
| Regresión backend | 208 pruebas registradas, 35 omitidas en ese comando por configuración de bases de prueba; MySQL académico se ejecutó aparte. |
| Frontend | 28 pruebas correctas; compilación y lint correctos. |
| Navegador | Recorrido de compra, publicación, comunidad, reportes, exportación y vista móvil. |
| Instalación limpia | Importación desde cero: 17 tablas y 111.016 pedidos originales. |
| Cuaderno | 19 celdas de código ejecutadas, cero errores. |
| Respaldo | Restauración integral, conteos y funcionamiento de cuenta/pedido verificados. |
Las pruebas de concurrencia verifican que dos compradores no obtengan la misma última unidad. El rollback multítem verifica que una variante sin stock no deje otra descontada. La idempotencia comprueba que un reintento no duplique el pedido. Las pruebas de análisis cubren granularidad, fechas, meses expuestos y denominadores. Los informes JSON originales se incluyen junto con el código fuente para revisar el alcance exacto de cada verificación.
## 11.4. Anexo D: instalación y contenido de la entrega
Se requiere Python 3.13, Node.js de versión compatible con package.json y Docker Desktop en ejecución, o un MySQL 8.4 configurado de forma equivalente. El archivo `README_ENTREGA.md` del paquete contiene los comandos completos. El lanzador de entrega restaura la copia en un proyecto Docker independiente, utiliza por defecto MySQL 3308, API 8002 y web 5175, y evita volver a importar una base que ya contiene tablas.
La instalación crea un entorno virtual del backend, instala requirements y ejecuta npm ci en frontend. El lanzador de la entrega utiliza las fuentes suministradas y el respaldo verificado; no requiere Supabase. El lanzamiento habitual del repositorio sigue disponible en `Proyecto_PrograAvanzada/iniciar.py` y carga el dataset si se usa una base nueva.
| Elemento | Contenido |
| --- | --- |
| Informe_Tickia.docx y PDF | Informe editable con índice y copia de consulta. |
| codigo_fuente/ | Python, TypeScript, archivos de datos, pruebas y manuales. |
| sql/ | Seis scripts originales y estructura consolidada. |
| respaldo/ | Dump SQL completo y verificación de restauración. |
| notebooks/ | Cuaderno ejecutado y HTML con resultados. |
| analisis_csv/ | Salidas completas de los reportes ejecutados. |
| evidencias/ | Capturas y diagramas PNG, SVG y DOT. |
| MANIFEST.json y SHA256SUMS.txt | Procedencia de la entrega y huellas para comprobar archivos. |
Las cuentas ficticias son comprador.demo@example.com, vendedor.campus@example.com y papeleria.demo@example.com. Su contraseña compartida de demostración es `TickiaDemo2026!`. Son credenciales públicas de un entorno académico local, no accesos a un servicio real. Para la evaluación puede utilizarse el comprador y consultar el pedido 111017 ya entregado, o crear otras cuentas para nuevas compras.
## 11.5. Anexo E: glosario y notas de lectura
PK: clave primaria. FK: clave foránea. N:M: relación muchos a muchos. 3FN: tercera forma normal. CTE: expresión de tabla común. RFM: recencia, frecuencia y valor monetario. UUID: identificador usado para distinguir solicitudes. Lift: razón entre afinidad observada y referencia de independencia. Idempotencia: repetir una operación con la misma identidad no repite sus efectos.
La primera hoja del documento se reserva completamente en blanco para que el grupo elabore su carátula. El índice comienza en la hoja siguiente. Los capítulos utilizan numeración propia y las figuras mantienen una secuencia única. Los scripts y archivos adjuntos son parte integrante de la entrega y permiten ampliar cualquier captura o listado presentado en el informe.
'''


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    for file in (BUILD / 'resultados').glob('grafico_*.png'):
        shutil.copy2(file, OUT / 'figuras' / file.name)
    content = INTRO
    names = ['modelo_er', 'uml_builder_strategy_decorator', 'uml_state', 'uml_repository', 'arquitectura', 'ciclo_pedido']
    for number, name in enumerate(names, 1):
        content = content.replace('diagramas/'+name+'.png', f'diagramas/{number:02}_{name}.png')
    content = content.replace('{{ESTRUCTURA}}', '```sql\n' + (OUT/'SQL_estructura_objetos.sql').read_text(encoding='utf-8') + '\n```')
    content = content.replace('{{CONSULTAS}}', '```sql\n' + (PROJECT/'sql/03_consultas.sql').read_text(encoding='utf-8') + '\n```')
    for tag, name in [('PATRONES','patterns.py'),('REPOSITORIES','repositories.py')]:
        code = (ROOT/'Pagina Web/backend/academic'/name).read_text(encoding='utf-8')
        content = content.replace('{{'+tag+'}}', '```python\n'+code+'\n```')
    dictionary = json.loads((BUILD/'diccionario_bd.json').read_text(encoding='utf-8'))
    grouped = defaultdict(list)
    for entry in dictionary: grouped[entry['tabla']].append(entry)
    tables = []
    for name, columns in grouped.items():
        tables.append(f'### {name}\n\n| Columna | Tipo MySQL | NULL | Índice |\n| --- | --- | --- | --- |')
        tables.extend('| '+ ' | '.join([c['columna'],c['tipo'],c['permite_null'],c['clave'] or '—'])+' |' for c in columns)
        tables.append('')
    content = content.replace('{{DICCIONARIO}}', '\n'.join(tables))
    manifest = json.loads((BUILD/'respaldo_manifest.json').read_text(encoding='utf-8'))
    rows = ['| Tabla | Filas en el respaldo |','| --- | --- |']
    rows += [f"| {name} | {count:,} |".replace(',', '.') for name,count in manifest['counts'].items()]
    rows += [f"| **Total** | **{manifest['rows']:,}** |".replace(',', '.'), '',
             f"Tamaño del archivo SQL: {manifest['backup_bytes']:,} bytes. SHA-256:".replace(',', '.'),
             '`'+manifest['backup_sha256']+'`', '']
    content = content.replace('{{RESPALDO}}', '\n'.join(rows))
    assert '{{' not in content, 'Quedaron campos sin completar'
    (OUT/'Informe_Tickia.md').write_text(content, encoding='utf-8')
    print('Informe editable generado:', len(content.split()), 'palabras incluyendo código.')


if __name__ == '__main__': run()
