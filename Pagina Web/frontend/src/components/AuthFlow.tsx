import { useState } from 'react';
import type { FormEvent } from 'react';
import api, { errorMessage } from '../api';

export default function AuthFlow({ onLoginSuccess }: { onLoginSuccess: () => Promise<void> }) {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (loading) return;
    setError('');
    setLoading(true);
    try {
      if (!isLogin)
        await api.post('/auth/register', {
          email: email.trim(),
          password,
          phone_number: phone.trim(),
        });
      await api.post('/auth/login', new URLSearchParams({ username: email.trim(), password }), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      await onLoginSuccess();
    } catch (failure) {
      setError(errorMessage(failure, 'No pudimos iniciar tu sesión. Revisa tus datos.'));
    } finally {
      setLoading(false);
    }
  }
  return (
    <section className="form-card narrow" aria-labelledby="auth-title">
      <p className="eyebrow">Tu próximo plan empieza aquí</p>
      <h1 id="auth-title">{isLogin ? 'Bienvenido a Tickia' : 'Crea tu cuenta'}</h1>
      <p>
        {isLogin
          ? 'Ingresa para comprar, vender y seguir tus entradas.'
          : 'Compra y vende entradas con otras personas.'}
      </p>
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={(event) => void submit(event)}>
        <div className="input-group">
          <label htmlFor="auth-email">Correo electrónico</label>
          <input
            id="auth-email"
            className="input-field"
            type="email"
            autoComplete="email"
            maxLength={254}
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        {!isLogin && (
          <div className="input-group">
            <label htmlFor="auth-phone">Teléfono</label>
            <input
              id="auth-phone"
              className="input-field"
              type="tel"
              autoComplete="tel"
              minLength={6}
              maxLength={20}
              pattern="[+0-9 ()-]{6,20}"
              required
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
            />
          </div>
        )}
        <div className="input-group">
          <label htmlFor="auth-password">Contraseña</label>
          <input
            id="auth-password"
            className="input-field"
            type="password"
            autoComplete={isLogin ? 'current-password' : 'new-password'}
            minLength={isLogin ? 1 : 8}
            maxLength={72}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-describedby={!isLogin ? 'password-hint' : undefined}
          />
          {!isLogin && <small id="password-hint">Usa al menos 8 caracteres.</small>}
        </div>
        <button type="submit" className="btn btn-primary full-width" disabled={loading}>
          {loading ? 'Procesando…' : isLogin ? 'Iniciar sesión' : 'Registrarse'}
        </button>
      </form>
      <button
        className="btn btn-ghost full-width"
        disabled={loading}
        onClick={() => {
          setIsLogin((value) => !value);
          setError('');
        }}
      >
        {isLogin ? '¿No tienes cuenta? Regístrate' : '¿Ya tienes cuenta? Inicia sesión'}
      </button>
    </section>
  );
}
