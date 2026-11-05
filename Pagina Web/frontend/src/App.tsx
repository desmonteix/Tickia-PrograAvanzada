import { useEffect, useRef, useState } from 'react';
import api, { errorMessage } from './api';
import type { User } from './types';
import SellerFlow from './components/SellerFlow';
import BuyerFlow from './components/BuyerFlow';
import AuthFlow from './components/AuthFlow';
import WalletFlow from './components/WalletFlow';
import AdminDashboard from './components/AdminDashboard';

type View = 'catalog' | 'seller' | 'login' | 'wallet' | 'admin';
const getView = (): View => {
  const view = window.location.hash.slice(1);
  return ['seller', 'login', 'wallet', 'admin'].includes(view) ? (view as View) : 'catalog';
};

export default function App() {
  const [view, setView] = useState<View>(getView);
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');
  const [isDark, setIsDark] = useState(true);
  const nextView = useRef<View>('catalog');
  const heading = useRef<HTMLElement>(null);
  function navigate(destination: View) {
    window.location.hash = destination;
  }
  useEffect(() => {
    document.documentElement.dataset.theme = isDark ? 'dark' : 'light';
  }, [isDark]);
  useEffect(() => {
    const controller = new AbortController();
    api
      .get<User>('/auth/me', { signal: controller.signal })
      .then((response) => setUser(response.data))
      .catch((error) => {
        if (!controller.signal.aborted && error?.response?.status !== 401)
          setNotice(
            errorMessage(error, 'No pudimos comprobar tu sesión. Intenta ingresar de nuevo.'),
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setCheckingSession(false);
      });
    const onHash = () => {
      if (
        ['catalog', 'seller', 'login', 'wallet', 'admin'].includes(window.location.hash.slice(1))
      ) {
        setView(getView());
        heading.current?.focus();
      }
    };
    const onExpired = () => {
      setUser(null);
      setNotice('Tu sesión terminó. Ingresa de nuevo para continuar.');
      navigate('login');
    };
    window.addEventListener('hashchange', onHash);
    window.addEventListener('tickia:session-expired', onExpired);
    const url = new URL(window.location.href);
    const referral = url.searchParams.get('ref_ticket');
    if (referral && /^[0-9a-f-]{36}$/i.test(referral)) {
      void api.post(`/tickets/${referral}/track-visit`).catch(() => undefined);
      url.searchParams.delete('ref_ticket');
      window.history.replaceState({}, '', url);
    }
    return () => {
      controller.abort();
      window.removeEventListener('hashchange', onHash);
      window.removeEventListener('tickia:session-expired', onExpired);
    };
  }, []);
  async function logout() {
    try {
      await api.post('/auth/logout');
      setUser(null);
      setNotice('Cerraste tu sesión.');
      navigate('catalog');
    } catch (error) {
      setNotice(errorMessage(error, 'No se pudo cerrar la sesión. Inténtalo otra vez.'));
    }
  }
  function requireLogin(destination: View) {
    nextView.current = destination;
    navigate('login');
  }
  const protectedView = ['seller', 'wallet', 'admin'].includes(view);
  const visibleView = protectedView && !user ? 'login' : view;
  return (
    <div className="app-container">
      <a className="skip-link" href="#main-content">
        Saltar al contenido
      </a>
      <header className="site-header">
        <nav className="navbar container" aria-label="Navegación principal">
          <button
            className="brand-link"
            aria-label="Tickia, inicio"
            onClick={() => navigate('catalog')}
          >
            <img
              src={isDark ? '/brand/tickia-dark.png' : '/brand/tickia-light.png'}
              alt="tickia"
              width="158"
              height="36"
            />
          </button>
          <div className="nav-links">
            <button
              className="btn btn-ghost"
              aria-current={view === 'catalog' ? 'page' : undefined}
              onClick={() => navigate('catalog')}
            >
              Explorar
            </button>
            <button
              className="btn btn-ghost"
              aria-current={view === 'seller' ? 'page' : undefined}
              onClick={() => (user ? navigate('seller') : requireLogin('seller'))}
            >
              Vender
            </button>
            {user && (
              <button className="btn btn-ghost" onClick={() => navigate('wallet')}>
                Mis compras
              </button>
            )}
            {user?.is_admin && (
              <button className="btn btn-ghost" onClick={() => navigate('admin')}>
                Administración
              </button>
            )}
            <button
              className="btn btn-ghost theme-toggle"
              aria-label={isDark ? 'Activar tema claro' : 'Activar tema oscuro'}
              onClick={() => setIsDark((value) => !value)}
            >
              {isDark ? '◐' : '◑'}
            </button>
            {user ? (
              <button className="btn btn-secondary" onClick={() => void logout()}>
                Salir
              </button>
            ) : (
              <button className="btn btn-primary" onClick={() => requireLogin('catalog')}>
                Ingresar
              </button>
            )}
          </div>
        </nav>
      </header>
      <main id="main-content" ref={heading} tabIndex={-1} className="main-content container">
        {notice && (
          <div className="notice" role="status">
            {notice}
            <button
              className="btn btn-ghost"
              aria-label="Cerrar aviso"
              onClick={() => setNotice('')}
            >
              ×
            </button>
          </div>
        )}
        {checkingSession && protectedView ? (
          <p role="status">Comprobando tu sesión…</p>
        ) : (
          <>
            {visibleView === 'catalog' && (
              <>
                <section className="hero-section" aria-labelledby="hero-title">
                  <p className="eyebrow">Entradas entre personas</p>
                  <h1 id="hero-title">
                    Tu entrada,
                    <br />
                    <span>su próximo plan.</span>
                  </h1>
                  <p>Tickia conecta a quien ya no puede ir con quien sí quiere ir.</p>
                  <div className="hero-actions">
                    <a className="btn btn-primary" href="#events">
                      Buscar mi evento <span aria-hidden="true">↗</span>
                    </a>
                    <button
                      className="btn btn-secondary"
                      onClick={() => (user ? navigate('seller') : requireLogin('seller'))}
                    >
                      Vender mi entrada
                    </button>
                  </div>
                  <div className="brand-ticket" aria-hidden="true">
                    <img src="/brand/tickia-symbol-lime.png" alt="" />
                    <span>
                      Si tú no vas,
                      <br />
                      que vaya alguien.
                    </span>
                    <small>UNA ENTRADA · DOS PERSONAS · UN PLAN</small>
                  </div>
                </section>
                <section id="events" aria-labelledby="events-title">
                  <div className="section-heading">
                    <div>
                      <p className="eyebrow">Encuentra tu próximo plan</p>
                      <h2 id="events-title">Entradas disponibles</h2>
                    </div>
                    <div className="search-field">
                      <label className="sr-only" htmlFor="event-search">
                        Buscar eventos o zonas
                      </label>
                      <input
                        id="event-search"
                        type="search"
                        className="input-field"
                        placeholder="Busca un evento o una zona"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                      />
                    </div>
                  </div>
                  <div className="catalog-results">
                    <BuyerFlow
                      searchQuery={search}
                      onRequireLogin={() => requireLogin('catalog')}
                    />
                  </div>
                </section>
              </>
            )}
            {visibleView === 'seller' && <SellerFlow />}
            {visibleView === 'wallet' && <WalletFlow />}
            {visibleView === 'admin' &&
              (user?.is_admin ? (
                <AdminDashboard />
              ) : (
                <p role="alert">No tienes acceso a administración.</p>
              ))}
            {visibleView === 'login' && (
              <AuthFlow
                onLoginSuccess={async () => {
                  const response = await api.get<User>('/auth/me');
                  setUser(response.data);
                  setNotice('Ya puedes comprar y vender entradas.');
                  navigate(protectedView ? view : nextView.current);
                }}
              />
            )}
          </>
        )}
      </main>
      <footer className="site-footer container">
        <p>tickia · Tu entrada, su próximo plan.</p>
        <p>Entradas entre personas. Tickia no es una tiquetera oficial.</p>
        <a href="https://www.instagram.com/tickia.lat/" target="_blank" rel="noopener noreferrer">
          @tickia.lat ↗
        </a>
      </footer>
    </div>
  );
}
