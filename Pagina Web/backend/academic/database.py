"""Conexiones MySQL del proyecto; no usa el engine de la aplicación original."""
import os
from sqlalchemy import URL, create_engine, text
from .settings import mysql_settings


def make_engine(url=None):
    config = mysql_settings()
    url = url or os.getenv('TICKIA_ACADEMIC_MYSQL_URL') or URL.create('mysql+pymysql',
        username=config['MYSQL_USER'], password=config['MYSQL_PASSWORD'],
        host=config['MYSQL_HOST'], port=config['MYSQL_PORT'], database=config['MYSQL_DATABASE'])
    return create_engine(url, pool_pre_ping=True, isolation_level='READ COMMITTED',
                         connect_args={'charset': 'utf8mb4', 'connect_timeout': 5})


engine = make_engine()


def get_db():
    with engine.begin() as connection:
        yield connection


def rows(connection, sql, params=None):
    return [dict(row) for row in connection.execute(text(sql), params or {}).mappings()]


def row(connection, sql, params=None):
    result = connection.execute(text(sql), params or {}).mappings().first()
    return dict(result) if result else None
