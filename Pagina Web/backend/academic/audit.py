"""Auditoría reproducible y de solo lectura de los requisitos de la entrega."""
import argparse
import ast
from datetime import datetime,timezone
import json
from pathlib import Path
import re
from sqlalchemy.exc import SQLAlchemyError
from .database import engine,make_engine,row,rows
from .analytics import sql_queries
from .schema_upgrade import columns
from .settings import LOCAL_DIR,SQL_DIR


def build_audit(target=engine,generated_target=None):
    with target.connect() as db:
        tables=[r['TABLE_NAME'] for r in rows(db,"SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")]
        primary=rows(db,"SELECT TABLE_NAME FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() AND CONSTRAINT_TYPE='PRIMARY KEY'")
        foreign=rows(db,'''SELECT TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME
            FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL
            ORDER BY TABLE_NAME,COLUMN_NAME''')
        indexes=rows(db,'''SELECT TABLE_NAME,INDEX_NAME,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) columnas
            FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() GROUP BY TABLE_NAME,INDEX_NAME ORDER BY TABLE_NAME,INDEX_NAME''')
        views=[r['TABLE_NAME'] for r in rows(db,'SELECT TABLE_NAME FROM information_schema.VIEWS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME')]
        view_usage=rows(db,'SELECT VIEW_NAME,TABLE_NAME FROM information_schema.VIEW_TABLE_USAGE WHERE VIEW_SCHEMA=DATABASE() AND TABLE_SCHEMA=DATABASE()')
        procedures=[r['ROUTINE_NAME'] for r in rows(db,"SELECT ROUTINE_NAME FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=DATABASE() AND ROUTINE_TYPE='PROCEDURE'")]
        triggers=rows(db,'SELECT TRIGGER_NAME,EVENT_MANIPULATION,ACTION_TIMING,EVENT_OBJECT_TABLE FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE()')
        facts=row(db,'SELECT COUNT(*) pedidos FROM pedidos')
        facts['detalle']=row(db,'SELECT COUNT(*) n FROM pedido_detalle')['n']
        facts['por_origen']=rows(db,'SELECT origen,COUNT(*) pedidos FROM pedidos GROUP BY origen ORDER BY origen')
        bridges={}
        for table in ('pedido_detalle','favoritos'):
            keys=rows(db,"SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:table AND CONSTRAINT_NAME='PRIMARY' ORDER BY ORDINAL_POSITION",{'table':table})
            bridges[table]=dict(primary_key=[r['COLUMN_NAME'] for r in keys],foreign_keys=[r for r in foreign if r['TABLE_NAME']==table])
        normalized=('id_provincia' in columns(db,'distritos'),not ({'provincia','departamento'}&columns(db,'distritos')),
            not ({'subtotal','descuento','costo_envio','destino'}&columns(db,'pedidos')),
            'id_distrito_entrega' in columns(db,'pedidos'))
        plans={
            'stock':rows(db,'EXPLAIN SELECT id_variante FROM variantes WHERE stock<=3'),
            'compras_usuario':rows(db,'EXPLAIN SELECT id_pedido FROM pedidos WHERE id_usuario=1 ORDER BY fecha DESC,id_pedido DESC LIMIT 24'),
        }
    queries={}
    for name,sql in sql_queries().items():
        clean=re.sub(r'^\s*--.*$','',sql,flags=re.MULTILINE)
        sources=set(re.findall(r'\b(?:FROM|JOIN)\s+([a-z_]\w*)',clean,re.IGNORECASE))
        # Una CTE o tres alias no equivalen por sí solos a tres tablas base.
        expanded=set(sources)
        for _ in range(len(views)+1):
            expanded.update(r['TABLE_NAME'] for r in view_usage if r['VIEW_NAME'] in expanded)
        base_tables=sorted(expanded&set(tables))
        joins=len(re.findall(r'\bJOIN\b',clean,re.IGNORECASE))
        queries[name]=dict(joins=joins,tablas_base=base_tables,join_tres_tablas=joins>=2 and len(base_tables)>=3,
            ventana=bool(re.search(r'\bOVER\s*\(',clean,re.IGNORECASE)),cte=bool(re.search(r'\bWITH\s+(?:RECURSIVE\s+)?\w+\s+AS',clean,re.IGNORECASE)))
    code=ast.parse((Path(__file__).parent/'commerce.py').read_text(encoding='utf-8'))
    calls={node.func.id for node in ast.walk(code) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)}
    expected_indexes=set(re.findall(r'CREATE INDEX (\w+)',(SQL_DIR/'05_indices.sql').read_text(encoding='utf-8')))
    generation=None
    if generated_target is not None:
        try:
            with generated_target.connect() as db:
                generation=row(db,"SELECT COUNT(*) pedidos,COUNT(DISTINCT solicitud_uuid) solicitudes FROM pedidos WHERE origen='numpy'")
                generation['database']=generated_target.url.database
        except SQLAlchemyError:
            generation={'pedidos':0,'database':generated_target.url.database,'estado':'No disponible. Ejecutar verificar.py.'}
    checks=dict(
        minimo_12_tablas=len(tables)>=12,
        todas_con_pk=len(primary)==len(tables),
        integridad_fk=len(foreign)>=22,
        estructura_normalizada=all(normalized),
        dos_puentes_nm=all(len(b['primary_key'])==2 and len(b['foreign_keys'])==2 for b in bridges.values()),
        minimo_10000_hechos=facts['pedidos']>=10000,
        indices_consultas_frecuentes=expected_indexes<={r['INDEX_NAME'] for r in indexes},
        cinco_consultas_join_3_tablas=sum(q['join_tres_tablas'] for q in queries.values())>=5,
        dos_consultas_ventana=sum(q['ventana'] for q in queries.values())>=2,
        subconsulta_o_cte=any(q['cte'] for q in queries.values()),
        dos_vistas=len(views)>=2,
        procedimiento='confirmar_pedido' in procedures,
        trigger=any(t['TRIGGER_NAME']=='tr_pedido_validar_estado' for t in triggers),
        repository_usado={'CatalogRepository','OrderRepository'}<=calls,
        patrones_integrados={'OrderBuilder','OrderContext'}<=calls,
    )
    if generation is not None:
        checks['generacion_numpy_cargada_en_pruebas']=generation['pedidos']>=10000
    return dict(generated_at=datetime.now(timezone.utc).isoformat(),database=target.url.database,
        cumple=all(checks.values()),checks=checks,tablas=tables,foreign_keys=foreign,puentes=bridges,
        indices=indexes,vistas=views,procedimientos=procedures,triggers=triggers,hechos=facts,
        consultas=queries,generacion_numpy=generation,explain=plans,
        revision_3fn='Ver entregables/NORMALIZACION_3FN.md: dependencias funcionales y excepciones técnicas.',
        patrones=['Builder','Strategy','Decorator','State','Repository'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--incluir-pruebas',action='store_true')
    parser.add_argument('--export',type=Path,default=LOCAL_DIR/'auditoria-requisitos.json')
    args=parser.parse_args()
    test=make_engine(engine.url.set(database='tickia_universidad_test')) if args.incluir_pruebas else None
    report=build_audit(generated_target=test)
    args.export.parent.mkdir(parents=True,exist_ok=True)
    args.export.write_text(json.dumps(report,ensure_ascii=False,default=str,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(cumple=report['cumple'],database=report['database'],checks=report['checks'],archivo=str(args.export)),ensure_ascii=False,indent=2))
    raise SystemExit(0 if report['cumple'] else 1)
