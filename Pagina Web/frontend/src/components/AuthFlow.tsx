import React, { useState } from 'react';
import api from '../api';

interface AuthFlowProps {
  onLoginSuccess: () => void;
}

const AuthFlow: React.FC<AuthFlowProps> = ({ onLoginSuccess }) => {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [dni, setDni] = useState('');
  
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isLogin) {
        // Enviar form data per OAuth2 specs
        const formData = new URLSearchParams();
        formData.append('username', email);
        formData.append('password', password);
        
        await api.post('/auth/login', formData, {
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
        });
        
        onLoginSuccess();
      } else {
        await api.post('/auth/register', {
          email,
          password,
          full_name: fullName,
          dni
        });
        
        // Auto-login post registration
        const formData = new URLSearchParams();
        formData.append('username', email);
        formData.append('password', password);
        await api.post('/auth/login', formData, {
           headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
        });
        
        onLoginSuccess();
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Error en autenticación');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container animate-fade-in" style={{display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh'}}>
      <div className="glass-panel" style={{maxWidth: '450px', width: '100%', padding: '2.5rem', position: 'relative', overflow: 'hidden'}}>
        
        <div style={{position: 'absolute', top: '-50px', right: '-50px', width: '150px', height: '150px', background: 'var(--color-primary)', borderRadius: '50%', filter: 'blur(80px)', opacity: 0.5, zIndex: 0}}></div>
        <div style={{position: 'absolute', bottom: '-50px', left: '-50px', width: '150px', height: '150px', background: 'var(--color-success)', borderRadius: '50%', filter: 'blur(80px)', opacity: 0.3, zIndex: 0}}></div>

        <div style={{position: 'relative', zIndex: 1}}>
          <h2 style={{fontSize: '2rem', marginBottom: '0.5rem', textAlign: 'center'}}>
            {isLogin ? 'Bienvenido a Tickia' : 'Crea tu cuenta'}
          </h2>
          <p style={{color: 'var(--color-text-secondary)', textAlign: 'center', marginBottom: '2rem'}}>
            {isLogin ? 'Ingresa para gestionar tus entradas.' : 'Únete al marketplace más seguro de entradas.'}
          </p>

          {error && <div className="badge badge-warning" style={{width: '100%', boxSizing: 'border-box', marginBottom: '1.5rem', padding: '12px', justifyContent: 'center', fontSize: '0.85rem'}}>{error}</div>}

          <form onSubmit={handleSubmit}>
            {!isLogin && (
              <>
                <div className="input-group">
                  <label className="input-label">Nombre Completo</label>
                  <input className="input-field" type="text" required value={fullName} onChange={e => setFullName(e.target.value)} placeholder="Ej. Juan Pérez" />
                </div>
                <div className="input-group">
                  <label className="input-label">DNI / Documento</label>
                  <input className="input-field" type="text" required value={dni} onChange={e => setDni(e.target.value)} placeholder="8 dígitos" />
                </div>
              </>
            )}

            <div className="input-group">
              <label className="input-label">Correo Electrónico</label>
              <input className="input-field" type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="correo@ejemplo.com" />
            </div>

            <div className="input-group">
              <label className="input-label">Contraseña</label>
              <input className="input-field" type="password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" />
            </div>

            <button type="submit" className="btn btn-primary" style={{width: '100%', marginTop: '1rem', padding: '16px'}} disabled={loading}>
              {loading ? 'Procesando...' : (isLogin ? 'Iniciar Sesión' : 'Registrarse')}
            </button>
          </form>

          <div style={{marginTop: '2rem', textAlign: 'center'}}>
            <button className="btn btn-ghost" onClick={() => setIsLogin(!isLogin)} style={{fontSize: '0.9rem'}}>
              {isLogin ? '¿No tienes cuenta? Regístrate' : '¿Ya tienes cuenta? Inicia Sesión'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AuthFlow;
