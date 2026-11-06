#!/bin/sh
set -eu

# Validate before envsubst; never print values from the private environment.
if [ -z "${API_UPSTREAM:-}" ]; then
    echo 'API_UPSTREAM es obligatorio: configura el origen interno real del backend en Easypanel (http://NOMBRE_INTERNO:8000), sin ruta ni barra final.' >&2
    exit 1
fi
case "$API_UPSTREAM" in
    *[!A-Za-z0-9_./:-]*)
        echo 'API_UPSTREAM debe ser un origen HTTP(S) con nombre DNS o IPv4, sin credenciales, ruta ni barra final.' >&2
        exit 1 ;;
esac
if ! printf '%s\n' "$API_UPSTREAM" | grep -Eq '^https?://[A-Za-z0-9_]([A-Za-z0-9_.-]*[A-Za-z0-9_])?(:[0-9]{1,5})?$'; then
    echo 'API_UPSTREAM debe ser un origen HTTP(S) con nombre DNS o IPv4, sin credenciales, ruta ni barra final.' >&2
    exit 1
fi

PROXY_SHARED_SECRET=${PROXY_SHARED_SECRET:-}
secret_length=${#PROXY_SHARED_SECRET}
case "${PROXY_SHARED_SECRET:-}" in
    ''|*[!A-Za-z0-9_-]*) secret_length=0 ;;
esac
if [ "$secret_length" -lt 32 ] || [ "$secret_length" -gt 128 ]; then
    echo 'PROXY_SHARED_SECRET requiere 32-128 caracteres URL-safe (A-Z, a-z, 0-9, _ y -); usa exactamente la misma clave privada en frontend y backend.' >&2
    exit 1
fi
