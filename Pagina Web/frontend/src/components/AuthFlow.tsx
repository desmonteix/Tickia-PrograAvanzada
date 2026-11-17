import { useState } from 'react';
import type { FormEvent } from 'react';
import api, { errorMessage } from '../api';
import { rememberReferral, referralCode, clearReferral } from '../promotions';

export default function AuthFlow({
  onLoginSuccess,
  signedIn = false,
  registrationsEnabled = true,
  academicMode = false,
}: {
  onLoginSuccess: () => Promise<void>;
  signedIn?: boolean;
  registrationsEnabled?: boolean;
  academicMode?: boolean;
}) {
  const [referral, setReferral] = useState(() =>
    rememberReferral(window.location.search, {
      getItem: (key) => window.sessionStorage.getItem(key),
      setItem: (key, value) => window.sessionStorage.setItem(key, value),
    }),
  );
  const [isLogin, setIsLogin] = useState(signedIn || !referral);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (loading) return;
    setError('');
    setLoading(true);
    try {
      if (!isLogin) {
        if (!registrationsEnabled)
          throw new Error(
            'Los nuevos registros están pausados. Si ya tienes cuenta, puedes ingresar.',
          );
        await api.post('/auth/register', {
          email: email.trim(),
          password,
          phone_number: phone.trim(),
          ...(referral ? { referral_code: referralCode(referral) } : {}),
        });
        clearReferral({ removeItem: (key) => window.sessionStorage.removeItem(key) });
        setReferral('');
        const url = new URL(window.location.href);
        url.searchParams.delete('ref');
        window.history.replaceState({}, '', url);
        // Registration is committed even if login or the session check fails.
        setIsLogin(true);
        setNotice('Tu cuenta ya está creada. Usa tu correo y contraseña para ingresar.');
      }
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
        {academicMode
          ? 'Ingresa con tu cuenta local del proyecto académico.'
          : isLogin
            ? 'Ingresa para comprar, vender y seguir tus entradas.'
            : 'Compra y vende entradas con otras personas.'}
      </p>
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {!isLogin && !registrationsEnabled && (
        <p className="notice">
          Los nuevos registros están pausados. Puedes ingresar con una cuenta existente.
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
        {!isLogin && (
          <div className="input-group">
            <label htmlFor="auth-referral">Código de invitación (opcional)</label>
            <input
              id="auth-referral"
              className="input-field"
              value={referral}
              onChange={(event) => setReferral(event.target.value)}
              pattern="[A-Za-z0-9_-]{6,64}"
              minLength={6}
              maxLength={64}
              autoComplete="off"
              aria-describedby="referral-hint"
            />
            <small id="referral-hint">
              El beneficio es para quien te invitó, si te registras durante la campaña.
            </small>
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
        <button
          type="submit"
          className="btn btn-primary full-width"
          disabled={loading || (!isLogin && !registrationsEnabled)}
        >
          {loading ? 'Procesando…' : isLogin ? 'Iniciar sesión' : 'Registrarse'}
        </button>
      </form>
      <button
        className="btn btn-ghost full-width"
        disabled={loading}
        onClick={() => {
          setIsLogin((value) => !value);
          setError('');
          setNotice('');
        }}
      >
        {isLogin ? '¿No tienes cuenta? Regístrate' : '¿Ya tienes cuenta? Inicia sesión'}
      </button>
    </section>
  );
}
