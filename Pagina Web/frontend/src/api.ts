import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 20000,
  withCredentials: true,
});

export function errorMessage(
  error: unknown,
  fallback = 'No pudimos completar la operación. Inténtalo otra vez.',
): string {
  if (!axios.isAxiosError(error)) return error instanceof Error ? error.message : fallback;
  const detail: unknown = error.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return 'Revisa los campos del formulario y vuelve a intentarlo.';
  if (!error.response)
    return 'No pudimos conectar con Tickia. Revisa tu conexión e inténtalo otra vez.';
  return fallback;
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const path = error.config?.url as string | undefined;
    if (error.response?.status === 401 && path && !path.startsWith('/auth/'))
      window.dispatchEvent(new Event('tickia:session-expired'));
    return Promise.reject(error);
  },
);
export default api;
