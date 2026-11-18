# Herramientas del informe

Estas herramientas documentan la elaboración del informe y el paquete. La
aplicación no las ejecuta al iniciar. El Word y las evidencias ya generadas se
encuentran en `../entregables/informe`.

El informe utiliza una copia de demostración aislada y solo cuentas ficticias.
Los puertos de evidencia son 8032/5202. El respaldo portable se llama
`tickia_universidad`, con todas las filas del histórico y una compra de prueba.
No se exporta la base cotidiana del desarrollador.

## Dependencias

Usar el Python del backend y mantener las versiones de la aplicación:

```powershell
& ".\Pagina Web\backend\venv\Scripts\python.exe" -m pip install -c "Pagina Web/backend/requirements.txt" -r Proyecto_PrograAvanzada/informe_tools/requirements-informe.txt
& ".\Pagina Web\backend\venv\Scripts\python.exe" -m playwright install chromium
```

Playwright y Chromium se utilizan para las capturas. Los diagramas usan
`@viz-js/viz@3.31.0` en
`Proyecto_PrograAvanzada/.local/informe-build/viz/node_modules`, instalado con
npm en esa carpeta temporal. La actualización del índice y la exportación PDF
requieren Windows con Microsoft Word de escritorio; `--sin-word` construye el
DOCX sin actualizar campos ni exportar el PDF.

## Archivos

* `capturar_demo.py`: recorrido real e idempotente sobre la copia de demostración.
* `crear_diagramas.py`: PNG, SVG y DOT de las entidades y clases implementadas.
* `crear_cuaderno.py`: cuaderno ejecutado, HTML y capturas de SQL/Pandas.
* `preparar_respaldo.py`: exportación sin DEFINER, restauración en un MySQL
  temporal y comprobación de objetos, conteos y funcionamiento de cuenta/pedido.
* `contenido_informe.py`: redacción y ensamblaje de Markdown con scripts reales.
* `crear_informe.py`: maquetación Word, primera hoja vacía, índice nativo, PDF
  y comprobaciones de paginación.
* `empaquetar_entrega.py`: fuentes desde Git, CSV con sus bytes originales,
  documentos, SQL, dump, evidencias y hashes en un ZIP.
* `iniciar_entrega.py`: se copia a la raíz del ZIP; crea una instancia MySQL
  propia y restaura solo una base inicialmente vacía.

Para editar el texto final, modificar `Informe_Tickia.md` y ejecutar
`crear_informe.py`. Volver a ejecutar `contenido_informe.py` reconstruye ese
Markdown a partir de su redacción fuente y metadatos: reemplaza las ediciones
manuales del Markdown. Después hay que volver a empaquetar.

La primera hoja permanece vacía y el índice comienza en la segunda. La
validación abre el PDF exportado por Word para comprobar esos requisitos,
detectar páginas vacías inesperadas y verificar contenido esencial. Los
metadatos completos y logs están en `.local/informe-build`, fuera de Git.

El ZIP grande no se incorpora al repositorio: se entrega como archivo local.
El Word, PDF, cuaderno, scripts de estructura, imágenes y generadores sí se
conservan en la rama universitaria.
