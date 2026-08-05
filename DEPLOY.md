# Guía de Despliegue a la Nube (Producción)

Para que tu aplicación web sea accesible desde cualquier dispositivo, hemos preparado los archivos necesarios para un despliegue gratuito y escalable.

## 1. Backend (FastAPI) en Render.com

Render ofrece una base de datos PostgreSQL gratuita temporal, pero como ya tienes Supabase, simplemente conectaremos el servicio web.

1. Regístrate en [Render.com](https://render.com)
2. Crea un nuevo **Web Service**
3. Conecta tu repositorio de GitHub (o Gitlab)
4. Render leerá automáticamente el archivo `render.yaml` y preconfigurará todo.
5. **MUY IMPORTANTE**: En el panel de Render, debes ir a **Environment Variables** y copiar todos los valores secretos que tienes en tu `.env` local (`SUPABASE_URL`, `SUPABASE_KEY`, `QR_ENCRYPTION_KEY`, `QR_HMAC_SECRET`, etc.).
6. Añade la variable `FRONTEND_PROD_URL` con la URL que te dará Vercel en el siguiente paso.

## 2. Frontend (React) en Vercel

Vercel es la mejor opción para aplicaciones hechas con Vite/React.

1. Regístrate en [Vercel.com](https://vercel.com)
2. Haz clic en **Add New Project** y selecciona tu repositorio.
3. En **Framework Preset**, asegúrate de que diga **Vite**.
4. El archivo `vercel.json` se encargará de que el enrutamiento de React (React Router) funcione correctamente al recargar la página.
5. En **Environment Variables**, añade:
   - `VITE_API_URL`: Aquí pondrás la URL de tu backend en Render (ej: `https://tu-backend.onrender.com/api`).
6. Despliega (Deploy).

## 3. Base de Datos (Supabase)

Tu base de datos de Supabase ya está en la nube.
Asegúrate de:
- No compartir las claves de Supabase.
- En tu panel de Supabase, en la sección de **Storage**, asegúrate de que el bucket `qr-encrypted` sea **Privado**, no público.

## 4. Pruebas Finales
Una vez desplegado:
1. Entra a tu app desde un celular (usando el link de Vercel).
2. Regístrate con un nuevo correo.
3. Sube una entrada ficticia y verifica que funcione rápido.
4. Compra la entrada desde otro usuario y verifica que se genera el QR dinámico (sin capturas de pantalla).
