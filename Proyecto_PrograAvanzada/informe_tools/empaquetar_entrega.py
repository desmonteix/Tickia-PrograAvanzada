"""Empaqueta código, informe, evidencia y dump; excluye credenciales y entornos."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / 'Proyecto_PrograAvanzada'
BUILD = PROJECT / '.local/informe-build'
REPORT = PROJECT / 'entregables/informe'
DEST = PROJECT / '.local/entrega_final/Tickia_PrograAvanzada'

README = '''# Entrega de Tickia — Programación Avanzada

El informe Word deja la primera hoja completamente en blanco para la carátula.
El PDF facilita revisar la paginación. El índice ya está calculado en Word;
después de editar el documento, usar Ctrl+A y F9 para actualizar los campos.

## Abrir la aplicación con la base de datos entregada

Requisitos: Python 3.13, Node.js >=22.16 y Docker Desktop abierto, con
contenedores Linux. Extraer TODO el ZIP a una carpeta propia. Desde esa carpeta,
en PowerShell:

```powershell
python -m venv "codigo_fuente/Pagina Web/backend/venv"
& ".\\codigo_fuente\\Pagina Web\\backend\\venv\\Scripts\\python.exe" -m pip install -r "codigo_fuente/Pagina Web/backend/requirements.txt"
npm.cmd ci --prefix "codigo_fuente/Pagina Web/frontend"
python iniciar_entrega.py
```

La primera ejecución descarga MySQL 8.4 y restaura el respaldo completo. Abre:

* Aplicación: http://127.0.0.1:5175
* API y Swagger: http://127.0.0.1:8002/docs
* MySQL: 127.0.0.1:3308, base tickia_universidad.

El lanzador usa el proyecto Docker **tickia-entrega**, con su propio volumen,
y credenciales aleatorias en `.entrega_config/mysql.env`. La instalación del
repositorio en 3307/5174 no se modifica. No compartas `.entrega_config` después
de generar sus claves. Ctrl+C cierra los procesos web; MySQL conserva los datos.
Repetir el lanzador no vuelve a importar la copia si ya existen sus 17 tablas.
Para cerrar únicamente el MySQL de esta entrega, sin eliminar el volumen:

```powershell
docker compose -p tickia-entrega --env-file .entrega_config/mysql.env -f .entrega_config/compose.entrega.yml stop
```

Si necesitas otros puertos/proyecto, usa por ejemplo:

```powershell
python iniciar_entrega.py --project tickia-evaluacion --mysql-port 3309 --api-port 8003 --web-port 5176
```

Para otra instalación independiente, extrae otra copia en una carpeta nueva y
elige otro nombre de proyecto y puertos. Si una base existente tiene una
estructura inesperada, el lanzador se detiene y no la sobrescribe.

## Cuentas ficticias y recorrido

Contraseña pública para las tres cuentas: **TickiaDemo2026!**

* comprador.demo@example.com — comprador de demostración.
* vendedor.campus@example.com — Tienda Campus, propietario de la mochila.
* papeleria.demo@example.com — Papelería Universitaria, propietario del cuaderno.

El comprador conserva el pedido **111017**, entregado, por **S/278,67**.
La mochila tiene pregunta, respuesta del propietario y una reseña de prueba.
Puedes crear nuevas cuentas, publicar variantes y comprar otros productos.
El carrito está en la esquina superior derecha. Los pagos y envíos son simulados.

## SQL, datos y restauración

* `sql/01_esquema.sql` a `06_trigger.sql`: scripts originales del proyecto.
* `sql/SQL_estructura_objetos.sql`: estructura y objetos consolidados; requiere
  una base vacía seleccionada. Los índices adicionales se ejecutan una vez.
* `respaldo/tickia_universidad_completa.sql`: creación, datos y objetos en un
  solo dump, ya probado en otra instancia MySQL 8.4.
* `respaldo/validacion_respaldo.json`: conteos, SHA-256 y comprobaciones reales.

El dump incluye 17 tablas y **801.586 filas**, 3 vistas, 22 FK, 1 procedimiento
y 1 trigger. Hay **111.016 pedidos fuente y un pedido de demostración**.
Las 15 fuentes CSV (801.519 filas) se conservan en `codigo_fuente/Proyecto_PrograAvanzada`.
Los 48 registros geográficos adicionales y las 19 filas del recorrido explican
la diferencia. Los 10.000 pedidos NumPy se verificaron en una base de pruebas
separada; su generador, evidencia y pruebas están incluidos en las fuentes.

El respaldo conserva una huella de los CSV en el esquema. Se mantuvieron sus
bytes exactos al empaquetar, para que el inicializador reconozca la carga. No
conviertas los CSV ni cambies sus finales de línea antes de la primera revisión.
El dump se restaura en una base propia; contiene instrucciones DROP TABLE de
mysqldump y no debe ejecutarse sobre una base de trabajo que quieras conservar.

## Ejecutar el análisis Python

`notebooks/Analisis_Tickia.ipynb` tiene 19 celdas de código ejecutadas y cero
errores. El HTML permite revisar todas las salidas sin Jupyter.
Para repetir, primero preparar MySQL con `python iniciar_entrega.py --solo-bd`.
Después, desde esta misma carpeta:

```powershell
& ".\\codigo_fuente\\Pagina Web\\backend\\venv\\Scripts\\python.exe" -m pip install -c "codigo_fuente/Pagina Web/backend/requirements.txt" matplotlib==3.11.1 nbconvert==7.17.2 nbclient==0.11.0 ipykernel==7.4.0
& ".\\codigo_fuente\\Pagina Web\\backend\\venv\\Scripts\\python.exe" -m ipykernel install --user --name tickia-entrega
& ".\\codigo_fuente\\Pagina Web\\backend\\venv\\Scripts\\python.exe" -m nbconvert --to notebook --execute notebooks/Analisis_Tickia.ipynb --ExecutePreprocessor.kernel_name=tickia-entrega --ExecutePreprocessor.timeout=600 --output Analisis_Tickia_repetido.ipynb
```

El cuaderno detecta la configuración de `.entrega_config` sin mostrar claves.
Los resultados históricos filtran `origen='dataset'`, por lo que no incorporan
la operación web de demostración. Las capturas de conteos sí muestran la copia
completa. `analisis_csv` contiene los resultados completos de la ejecución.

## Código, evidencias y comprobación de integridad

El código Python está en `codigo_fuente/Pagina Web/backend`, con el backend
académico en `academic/`. El frontend se entrega completo con package-lock.
Los diagramas originales incluyen PNG, SVG y DOT; las capturas proceden de
Chromium y del cuaderno ejecutado. `MANIFEST.json` documenta esta entrega y
`SHA256SUMS.txt` permite comprobar cada archivo, sin incluirse a sí mismo.

El código base corresponde al commit indicado en el manifiesto; los generadores
y documentos de esta entrega se incorporan desde el árbol actual. No se incluyen
venv, node_modules, secretos, la base personal del desarrollador ni archivos .git.
La rama universitaria está separada del repositorio original y no se hace merge.
'''


def digest(file):
    value = hashlib.sha256()
    with file.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''): value.update(part)
    return value.hexdigest()


def copy_files(source, target, predicate=lambda path: True):
    for file in sorted(source.rglob('*')):
        if file.is_file() and predicate(file):
            dest = target / file.relative_to(source); dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(file, dest)


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    assert (DEST / 'respaldo/tickia_universidad_completa.sql').is_file(), 'Prepara y restaura primero el respaldo.'
    commit = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
    archive = BUILD / 'fuentes_git.tar'
    with archive.open('wb') as stream:
        subprocess.run(['git','archive','--format=tar','HEAD','--','Pagina Web/backend','Pagina Web/frontend',
                        'Pagina Web/tests','Proyecto_PrograAvanzada','README.md','.gitignore'], cwd=ROOT, stdout=stream, check=True)
    sources = DEST / 'codigo_fuente'; sources.mkdir(exist_ok=True)
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        for member in members:
            relative = Path(member.name)
            assert not relative.is_absolute() and '..' not in relative.parts and not member.issym() and not member.islnk()
        tar.extractall(sources, filter='data')
    # git archive convierte CRLF a LF. El marcador de carga usa los bytes de los CSV.
    originals = list(PROJECT.glob('*.csv'))
    assert len(originals) == 15
    for csv in originals: shutil.copyfile(csv, sources / 'Proyecto_PrograAvanzada' / csv.name)
    copy_files(PROJECT/'informe_tools', sources/'Proyecto_PrograAvanzada/informe_tools', lambda p: p.suffix in ('.py','.txt','.md'))
    copy_files(REPORT, sources/'Proyecto_PrograAvanzada/entregables/informe',
               lambda p: p.suffix in ('.md','.sql','.png','.dot','.svg','.docx','.pdf','.ipynb','.html'))
    for extension in ('docx','pdf'): shutil.copy2(REPORT/f'Informe_Tickia.{extension}', DEST/f'Informe_Tickia.{extension}')
    copy_files(PROJECT/'sql', DEST/'sql')
    shutil.copy2(REPORT/'SQL_estructura_objetos.sql', DEST/'sql/SQL_estructura_objetos.sql')
    (DEST/'notebooks').mkdir(exist_ok=True)
    for suffix in ('ipynb','html'): shutil.copy2(REPORT/f'Analisis_Tickia.{suffix}', DEST/f'notebooks/Analisis_Tickia.{suffix}')
    copy_files(REPORT/'figuras', DEST/'evidencias/capturas')
    copy_files(REPORT/'diagramas', DEST/'evidencias/diagramas')
    copy_files(BUILD/'resultados', DEST/'analisis_csv', lambda p: p.suffix in ('.csv','.json'))
    shutil.copy2(PROJECT/'informe_tools/iniciar_entrega.py', DEST/'iniciar_entrega.py')
    (DEST/'README_ENTREGA.md').write_text(README, encoding='utf-8')
    backup = json.loads((BUILD/'respaldo_manifest.json').read_text(encoding='utf-8'))
    report = json.loads((BUILD/'validacion_informe.json').read_text(encoding='utf-8'))
    notebook = json.loads((BUILD/'cuaderno_ejecucion.json').read_text(encoding='utf-8'))
    versions = {name:importlib.metadata.version(name) for name in ('python-docx','matplotlib','PyMuPDF','nbformat','nbclient','nbconvert','ipykernel','pandas','numpy','PyMySQL','SQLAlchemy','playwright')}
    manifest = dict(project='Tickia — Programación Avanzada', date='18-11-2026', branch='proyecto_progra_avanzada',
                    source_git_commit=commit, source_extras='informe_tools y documentos elaborados en esta entrega',
                    repo='https://github.com/desmonteix/Tickia-PrograAvanzada', report=report, notebook=notebook,
                    backup=backup, tool_versions=versions, csv_raw_bytes_preserved=True,
                    payments_and_shipments_simulated=True, personal_accounts_included=False)
    (DEST/'MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    forbidden = {'.git','.local','.entrega_config','venv','node_modules','__pycache__','.env'}
    for file in DEST.rglob('*'):
        if file.is_file():
            assert not forbidden.intersection(file.relative_to(DEST).parts), f'Archivo excluido encontrado: {file.name}'
            assert file.name not in ('mysql.env','secrets.json'), 'Se encontró un secreto local.'
    files = sorted(p for p in DEST.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.txt')
    hashes = '\n'.join(digest(file)+'  '+file.relative_to(DEST).as_posix() for file in files)+'\n'
    (DEST/'SHA256SUMS.txt').write_text(hashes, encoding='utf-8')
    output = PROJECT/'entregables/Entrega_Tickia_PrograAvanzada.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive_zip:
        for file in sorted(DEST.rglob('*')):
            if file.is_file(): archive_zip.write(file, Path(DEST.name)/file.relative_to(DEST))
    with zipfile.ZipFile(output) as archive_zip:
        assert archive_zip.testzip() is None
        count = len(archive_zip.infolist())
    validation = dict(file=output.name, bytes=output.stat().st_size, sha256=digest(output), files=count,
                      zip_crc_ok=True, csv_raw_bytes_preserved=True, backup_restore=backup['restore_validation']['success'])
    (BUILD/'validacion_paquete.json').write_text(json.dumps(validation, indent=2), encoding='utf-8')
    print(json.dumps(validation, ensure_ascii=False))


if __name__ == '__main__': main()
