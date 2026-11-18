"""Configuración exclusiva del repositorio universitario; nunca usa Supabase."""
import os
from pathlib import Path
import secrets
from ..dataset import SOURCE_DIR, LOCAL_DIR
from ..local_config import configure_local

SQL_DIR = SOURCE_DIR / 'sql'


def mysql_env_file():
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCAL_DIR / 'mysql.env'
    try:
        with path.open('x', encoding='utf-8') as stream:
            stream.write('MYSQL_DATABASE=tickia_universidad\nMYSQL_USER=tickia\n'
                         'MYSQL_PASSWORD=' + secrets.token_urlsafe(24) + '\n'
                         'MYSQL_ROOT_PASSWORD=' + secrets.token_urlsafe(32) + '\n')
    except FileExistsError:
        pass
    return path


def mysql_settings():
    values = dict(line.split('=', 1) for line in mysql_env_file().read_text(encoding='utf-8').splitlines()
                  if line and not line.startswith('#') and '=' in line)
    return {**values, 'MYSQL_HOST': os.getenv('TICKIA_MYSQL_HOST', '127.0.0.1'),
            'MYSQL_PORT': int(os.getenv('TICKIA_MYSQL_PORT', '3307'))}


def configure_security():
    configure_local()


if __name__ == '__main__':
    print(mysql_env_file())
