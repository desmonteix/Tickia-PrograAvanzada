# Tickia · Marketplace multivendedor

Proyecto universitario de Programación Avanzada. Conserva la interfaz Tickia y
utiliza **MySQL 8.4 y 17 tablas normalizadas**, a partir de 15 CSV con 801.519 filas originales. Incluye productos
con variantes, carrito multivendedor, cupones, pedidos, reseñas, preguntas,
favoritos y análisis con Pandas. Los pagos y envíos son simulados.

Repositorio independiente: `desmonteix/Tickia-PrograAvanzada`.
Rama de trabajo y predeterminada: `proyecto_progra_avanzada`.

## Ejecutar

Python 3.13, Node.js 22.16 o posterior y Docker Desktop iniciado con contenedores Linux.
Desde la raíz, en PowerShell:

```powershell
python -m venv "Pagina Web/backend/venv"
& ".\Pagina Web\backend\venv\Scripts\python.exe" -m pip install -r "Pagina Web/backend/requirements.txt"
npm.cmd ci --prefix "Pagina Web/frontend"
python Proyecto_PrograAvanzada/iniciar.py
```

Abre **http://127.0.0.1:5174**. La primera carga tarda unos minutos. Los siguientes
arranques conservan cuentas, pedidos y stock. No requiere Supabase ni credenciales de pagos.

## Entrega

- [Manual de ejecución y pruebas](Proyecto_PrograAvanzada/COMO_EJECUTAR.md).
- [Matriz de cumplimiento](Proyecto_PrograAvanzada/entregables/MATRIZ_CUMPLIMIENTO.md).
- [Auditoría de requisitos](Proyecto_PrograAvanzada/entregables/AUDITORIA_REQUISITOS.md).
- [Normalización a 3FN](Proyecto_PrograAvanzada/entregables/NORMALIZACION_3FN.md).
- [Consultas avanzadas](Proyecto_PrograAvanzada/entregables/CONSULTAS_AVANZADAS.md).
- [Modelo de datos](Proyecto_PrograAvanzada/entregables/ERD.md).
- [Los cuatro patrones](Proyecto_PrograAvanzada/entregables/PATRONES.md).
- [Informe de análisis](Proyecto_PrograAvanzada/entregables/INFORME_ANALISIS.md).
- [Guion de sustentación](Proyecto_PrograAvanzada/entregables/SUSTENTACION.md).
- [Esquema, procedimiento y consultas SQL](Proyecto_PrograAvanzada/sql/).

La API principal está en `Pagina Web/backend/academic/`. Los módulos originales
de entradas y la versión SQLite anterior quedan como referencia y respaldo.
El lanzador usa MySQL por defecto.
