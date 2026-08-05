import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8001/api',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor para manejar tokens expirados (401)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      // Forzar recarga o redirección al home para que la UI de react refleje el estado deslogueado
      if (window.location.pathname !== '/') {
         window.location.href = '/'; 
      }
    }
    return Promise.reject(error);
  }
);

export default api;
