"""Publicaciones, variantes, preguntas, reseñas y favoritos del modelo MySQL."""
import json
import re
import uuid
from decimal import Decimal
from typing import Annotated
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from ..dataset import LOCAL_DIR
from .auth import get_current_user
from .database import get_db, row
from .catalog import product_detail

router = APIRouter(prefix='/api/marketplace', tags=['vendedores y comunidad'])


def save_photo(photo):
    if photo is None:
        return None
    from ..qr_utils import MAX_FILE_BYTES, validate_image_file
    import cv2
    import numpy as np
    content = photo.file.read(MAX_FILE_BYTES+1)
    if not validate_image_file(content,photo.content_type):
        raise HTTPException(422,'La foto debe ser PNG o JPEG y pesar como máximo 5 MB.')
    try:
        image = cv2.imdecode(np.frombuffer(content,np.uint8),cv2.IMREAD_COLOR)
        if image is None or image.shape[0]*image.shape[1]>20_000_000:
            raise ValueError('Dimensiones inválidas')
        valid,encoded = cv2.imencode('.jpg',image)
        if not valid:
            raise ValueError('Imagen inválida')
    except (ValueError,cv2.error):
        raise HTTPException(422,'No se pudo leer la foto.')
    directory = LOCAL_DIR/'product-images'
    directory.mkdir(parents=True,exist_ok=True)
    filename = uuid.uuid4().hex+'.jpg'
    (directory/filename).write_bytes(encoded.tobytes())
    return filename


@router.get('/images/{filename}')
def image(filename:str):
    if not re.fullmatch(r'[0-9a-f]{32}\.jpg',filename) or not (LOCAL_DIR/'product-images'/filename).is_file():
        raise HTTPException(404,'Imagen no encontrada.')
    return FileResponse(LOCAL_DIR/'product-images'/filename,media_type='image/jpeg')


class VariantInput(BaseModel):
    talla:str = Field(default='Única',max_length=60)
    color:str = Field(default='No especificado',max_length=60)
    stock:int = Field(ge=0,le=1000000)


@router.post('/products',status_code=201)
def publish(titulo:Annotated[str,Form(min_length=3,max_length=160)],
            precio:Annotated[Decimal,Form(gt=0,le=1000000,decimal_places=2,allow_inf_nan=False)],
            stock:Annotated[int,Form(ge=0,le=1000000)],id_categoria:Annotated[int,Form(ge=1)],
            descripcion:Annotated[str,Form(max_length=2000)]='',talla:Annotated[str,Form(max_length=60)]='Única',
            color:Annotated[str,Form(max_length=60)]='No especificado',
            variantes_json:Annotated[str|None,Form(max_length=12000)]=None,foto:UploadFile|None=File(default=None),
            user=Depends(get_current_user),db=Depends(get_db, scope="function")):
    category = row(db,'SELECT * FROM categorias WHERE id_categoria=:id',{'id':id_categoria})
    if not category or len(titulo.strip())<3:
        raise HTTPException(422,'Revisa el título y la categoría.')
    try:
        supplied = json.loads(variantes_json) if variantes_json else [dict(talla=talla,color=color,stock=stock)]
        if not isinstance(supplied,list) or not 1<=len(supplied)<=20:
            raise ValueError('Agrega entre 1 y 20 variantes.')
        variants = [VariantInput.model_validate(value) for value in supplied]
        if sum(value.stock for value in variants)<1:
            raise ValueError('El producto necesita al menos una unidad disponible.')
        if len({(value.talla.strip().casefold(),value.color.strip().casefold()) for value in variants})!=len(variants):
            raise ValueError('No repitas una combinación de talla y color.')
    except (ValueError,ValidationError) as error:
        raise HTTPException(422,'Revisa las variantes: '+str(error).splitlines()[0])
    row(db,'SELECT id_usuario FROM usuarios WHERE id_usuario=:id FOR UPDATE',{'id':user.id_usuario})
    seller = row(db,'SELECT id_vendedor FROM vendedores WHERE id_usuario=:id ORDER BY id_vendedor LIMIT 1',{'id':user.id_usuario})
    if not seller:
        result = db.execute(text('INSERT INTO vendedores(id_usuario,razon_social,reputacion) VALUES(:id,:name,4.00)'),
                            dict(id=user.id_usuario,name=user.nombre))
        seller = {'id_vendedor':result.lastrowid}
    filename = save_photo(foto)
    try:
        result = db.execute(text('''INSERT INTO productos(id_vendedor,id_categoria,titulo,precio,descripcion,imagen,origen)
            VALUES(:seller,:category,:title,:price,:description,:image,'web')'''),
            dict(seller=seller['id_vendedor'],category=id_categoria,title=titulo.strip(),price=precio,description=descripcion.strip(),image=filename))
        product_id = result.lastrowid
        db.execute(text('INSERT INTO variantes(id_producto,talla,color,stock) VALUES(:product,:size,:color,:stock)'),
                   [dict(product=product_id,size=value.talla.strip(),color=value.color.strip(),stock=value.stock) for value in variants])
        return product_detail(product_id,user,db)
    except Exception:
        if filename:
            (LOCAL_DIR/'product-images'/filename).unlink(missing_ok=True)
        raise


class FavoriteInput(BaseModel):
    enabled:bool


@router.put('/products/{product_id}/favorite')
def favorite(product_id:int,data:FavoriteInput,user=Depends(get_current_user),db=Depends(get_db, scope="function")):
    if not row(db,'SELECT id_producto FROM productos WHERE id_producto=:id',{'id':product_id}):
        raise HTTPException(404,'Producto no encontrado.')
    params = dict(user=user.id_usuario,product=product_id)
    if data.enabled:
        db.execute(text("INSERT INTO favoritos(id_usuario,id_producto,fecha) VALUES(:user,:product,DATE(CONVERT_TZ(UTC_TIMESTAMP(),'+00:00','-05:00'))) ON DUPLICATE KEY UPDATE fecha=favoritos.fecha"),params)
    else:
        db.execute(text('DELETE FROM favoritos WHERE id_usuario=:user AND id_producto=:product'),params)
    return {'favorito':data.enabled}


class QuestionInput(BaseModel):
    texto:str = Field(min_length=3,max_length=2000)


@router.post('/products/{product_id}/questions',status_code=201)
def question(product_id:int,data:QuestionInput,user=Depends(get_current_user),db=Depends(get_db, scope="function")):
    if not row(db,'SELECT id_producto FROM productos WHERE id_producto=:id',{'id':product_id}):
        raise HTTPException(404,'Producto no encontrado.')
    if len(data.texto.strip())<3:
        raise HTTPException(422,'Escribe una pregunta.')
    result = db.execute(text('INSERT INTO preguntas(id_producto,id_usuario,texto,fecha) VALUES(:product,:user,:question,UTC_TIMESTAMP())'),
                        dict(product=product_id,user=user.id_usuario,question=data.texto.strip()))
    return {'id_pregunta':result.lastrowid}


@router.put('/questions/{question_id}/answer')
def answer(question_id:int,data:QuestionInput,user=Depends(get_current_user),db=Depends(get_db, scope="function")):
    owned = row(db,'''SELECT q.id_pregunta FROM preguntas q JOIN productos p USING(id_producto)
        JOIN vendedores s USING(id_vendedor) WHERE q.id_pregunta=:id AND s.id_usuario=:user''',dict(id=question_id,user=user.id_usuario))
    if not owned:
        raise HTTPException(404,'Pregunta no encontrada en tus publicaciones.')
    if len(data.texto.strip())<3:
        raise HTTPException(422,'Escribe una respuesta.')
    db.execute(text('UPDATE preguntas SET respuesta=:answer WHERE id_pregunta=:id'),dict(answer=data.texto.strip(),id=question_id))
    return {'id_pregunta':question_id,'respuesta':data.texto.strip()}


class ReviewInput(BaseModel):
    estrellas:int = Field(ge=1,le=5)
    comentario:str = Field(min_length=3,max_length=2000)


@router.post('/products/{product_id}/reviews',status_code=201)
def review(product_id:int,data:ReviewInput,user=Depends(get_current_user),db=Depends(get_db, scope="function")):
    row(db,'SELECT id_usuario FROM usuarios WHERE id_usuario=:id FOR UPDATE',{'id':user.id_usuario})
    bought = row(db,'''SELECT 1 FROM pedidos pe JOIN pedido_detalle de USING(id_pedido) JOIN variantes va USING(id_variante)
        WHERE pe.id_usuario=:user AND pe.estado='entregado' AND va.id_producto=:product LIMIT 1''',dict(user=user.id_usuario,product=product_id))
    if not bought:
        raise HTTPException(403,'Solo puedes reseñar productos que recibiste.')
    if len(data.comentario.strip())<3:
        raise HTTPException(422,'Escribe un comentario.')
    if row(db,'SELECT id_resena FROM resenas WHERE id_producto=:product AND id_usuario=:user LIMIT 1',dict(product=product_id,user=user.id_usuario)):
        raise HTTPException(409,'Ya dejaste una reseña para este producto.')
    result = db.execute(text("INSERT INTO resenas(id_producto,id_usuario,estrellas,comentario,fecha) VALUES(:product,:user,:stars,:comment,DATE(CONVERT_TZ(UTC_TIMESTAMP(),'+00:00','-05:00')))"),
                        dict(product=product_id,user=user.id_usuario,stars=data.estrellas,comment=data.comentario.strip()))
    seller = row(db,'SELECT id_vendedor FROM productos WHERE id_producto=:id',{'id':product_id})['id_vendedor']
    row(db,'SELECT id_vendedor FROM vendedores WHERE id_vendedor=:id FOR UPDATE',{'id':seller})
    average = row(db,'SELECT AVG(r.estrellas) rating FROM resenas r JOIN productos p USING(id_producto) WHERE p.id_vendedor=:id',{'id':seller})['rating']
    db.execute(text('UPDATE vendedores SET reputacion=:rating WHERE id_vendedor=:id'),dict(rating=average,id=seller))
    return {'id_resena':result.lastrowid,'estrellas':data.estrellas}
