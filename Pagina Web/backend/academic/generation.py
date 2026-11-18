"""Generador NumPy reproducible de hechos comerciales, cargados solo en la BD de pruebas."""
import argparse
from dataclasses import dataclass
from datetime import date as CalendarDate,datetime,timedelta
from decimal import Decimal
import hashlib
import json
import uuid
import numpy as np
from .patterns import OrderBuilder,SHIPPING_STRATEGIES


@dataclass(frozen=True)
class GeneratedOrder:
    user_id:int
    district_id:int
    date:datetime
    state:str
    total:Decimal
    items:tuple[tuple[int,int,Decimal],...]
    courier_id:int
    shipping_cost:Decimal
    estimated:CalendarDate
    sent:datetime|None
    received:datetime|None


def generate_orders(users,variants,couriers,count=10000,seed=20261118):
    if not isinstance(count,int) or not 1<=count<=100000 or not users or not variants or not couriers:
        raise ValueError('Se requieren dimensiones pobladas y entre 1 y 100.000 pedidos.')
    rng=np.random.default_rng(seed)
    customers=rng.gamma(1.3,1,len(users));customers/=customers.sum()
    popularity=rng.pareto(1.5,len(variants))+1;popularity/=popularity.sum()
    buyers=rng.choice(len(users),size=count,p=customers)
    start=datetime(2024,1,1)
    days=(datetime(2026,10,1)-start).days
    result=[]
    for buyer in buyers:
        user=users[int(buyer)]
        selected=rng.choice(len(variants),size=min(1+int(rng.poisson(1.4)),5,len(variants)),replace=False,p=popularity)
        builder=OrderBuilder();items=[]
        for index in selected:
            variant=variants[int(index)]
            quantity=min(int(rng.geometric(.65)),5)
            price=Decimal(str(variant['precio']))
            items.append((variant['id_variante'],quantity,price))
            builder.add_item(variant['id_variante'],quantity,price)
        courier=couriers[int(rng.integers(len(couriers)))]
        draft=builder.shipping(SHIPPING_STRATEGIES[courier['estrategia']](),courier['costo_base'],user['departamento']).build()
        date=start+timedelta(days=int(rng.integers(days)),seconds=int(rng.integers(86400)))
        state=str(rng.choice(['pagado','enviado','entregado'],p=[.1,.1,.8]))
        sent=date+timedelta(days=1) if state!='pagado' else None
        duration=max(1,int(round(rng.gamma(2,1.4)*(1 if user['departamento']=='Lima' else 1.5))))
        received=sent+timedelta(days=duration) if state=='entregado' else None
        promise={'estandar':5,'rapido':2,'economico':7}[courier['estrategia']]
        result.append(GeneratedOrder(user['id_usuario'],user['id_distrito'],date,state,draft.total,
            tuple(items),courier['id_courier'],draft.shipping_cost,(date+timedelta(days=promise)).date(),sent,received))
    return result


def load_generated(target,count=10000,seed=20261118):
    """Carga atómica e idempotente. No se invoca al arrancar la aplicación principal."""
    from sqlalchemy import text
    from .database import row,rows
    if target.url.database!='tickia_universidad_test':
        raise ValueError('La generación solo se carga en tickia_universidad_test.')
    if not isinstance(count,int) or not 1<=count<=100000:
        raise ValueError('Cantidad fuera de rango.')
    batch_hash=hashlib.sha256(f'tickia-numpy-v1:{seed}:{count}'.encode()).hexdigest()
    metadata=dict(database=target.url.database,pedidos=count,seed=seed,numpy_version=np.__version__,batch_hash=batch_hash)
    lock='tickia-numpy:'+target.url.database
    with target.connect() as db:
        if row(db,'SELECT GET_LOCK(:name,30) acquired',{'name':lock})['acquired']!=1:
            raise RuntimeError('Otra generación está cargando datos.')
        db.commit()
        try:
            with db.begin():
                existing=row(db,"SELECT COUNT(*) n FROM pedidos WHERE origen='numpy' AND solicitud_hash=:hash",{'hash':batch_hash})['n']
                if existing:
                    if existing!=count:
                        raise RuntimeError('La carga existente está incompleta; no se reemplazó.')
                    return dict(metadata,loaded=False)
                users=rows(db,'''SELECT u.id_usuario,u.id_distrito,d.departamento FROM usuarios u
                    JOIN v_distritos d USING(id_distrito) WHERE u.auth_uuid IS NULL
                    AND NOT EXISTS(SELECT 1 FROM vendedores s WHERE s.id_usuario=u.id_usuario) ORDER BY u.id_usuario''')
                variants=rows(db,"SELECT v.id_variante,p.precio FROM variantes v JOIN productos p USING(id_producto) WHERE p.origen='dataset' ORDER BY v.id_variante")
                couriers=rows(db,'SELECT * FROM couriers ORDER BY id_courier')
                records=generate_orders(users,variants,couriers,count,seed)
                first=row(db,'SELECT COALESCE(MAX(id_pedido),0)+1 n FROM pedidos')['n']
                orders=[];details=[];payments=[];shipments=[]
                for index,record in enumerate(records):
                    identifier=first+index
                    request=str(uuid.uuid5(uuid.NAMESPACE_URL,f'tickia-numpy:{seed}:{count}:{index}'))
                    orders.append(dict(id=identifier,user=record.user_id,date=record.date,state=record.state,
                        total=record.total,district=record.district_id,request=request,hash=batch_hash))
                    details.extend(dict(id=identifier,variant=variant,quantity=quantity,price=price) for variant,quantity,price in record.items)
                    payments.append(dict(id=identifier,total=record.total,date=record.date))
                    shipments.append(dict(id=identifier,courier=record.courier_id,cost=record.shipping_cost,
                        sent=record.sent,received=record.received,estimated=record.estimated))
                statements=[
                    ("INSERT INTO pedidos(id_pedido,id_usuario,fecha,estado,total,id_distrito_entrega,solicitud_uuid,solicitud_hash,origen) VALUES(:id,:user,:date,:state,:total,:district,:request,:hash,'numpy')",orders),
                    ('INSERT INTO pedido_detalle(id_pedido,id_variante,cantidad,precio_unit) VALUES(:id,:variant,:quantity,:price)',details),
                    ("INSERT INTO pagos(id_pedido,metodo,monto,estado,simulado,fecha) VALUES(:id,'numpy_demo',:total,'aprobado',TRUE,:date)",payments),
                    ('INSERT INTO envios(id_pedido,id_courier,fecha_envio,fecha_entrega,fecha_estimada,costo_envio) VALUES(:id,:courier,:sent,:received,:estimated,:cost)',shipments),
                ]
                for sql,values in statements:
                    for offset in range(0,len(values),5000):
                        db.execute(text(sql),values[offset:offset+5000])
                metadata.update(detalles=len(details),primer_id=first,ultimo_id=first+count-1)
            return dict(metadata,loaded=True)
        finally:
            db.execute(text('SELECT RELEASE_LOCK(:name)'),{'name':lock})
            db.commit()


if __name__=='__main__':
    from .database import engine,make_engine
    from .bootstrap import initialize
    from .settings import LOCAL_DIR
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count',type=int,default=10000)
    parser.add_argument('--seed',type=int,default=20261118)
    args=parser.parse_args()
    target=make_engine(engine.url.set(database='tickia_universidad_test'))
    initialize(target)
    metadata=load_generated(target,args.count,args.seed)
    (LOCAL_DIR/'generacion_numpy.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(metadata,ensure_ascii=False,indent=2))
