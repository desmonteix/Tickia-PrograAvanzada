import { useCallback, useEffect, useRef, useState } from 'react';
import api, { errorMessage } from './api';
import type { User } from './types';
import SellerFlow from './components/SellerFlow';
import BuyerFlow from './components/BuyerFlow';
import ProductCatalog from './components/ProductCatalog';
import AuthFlow from './components/AuthFlow';
import WalletFlow from './components/WalletFlow';
import AdminDashboard from './components/AdminDashboard';
import { paymentTransaction } from './payments';
import { rememberReferral } from './promotions';
import { operationAllowed, percent } from './promotions';
import type { Campaign, Referrals } from './promotions';
import { useResource } from './useResource';
import ReferralPanel from './components/ReferralPanel';

type View = 'catalog' | 'seller' | 'login' | 'wallet' | 'admin';
const getView = (): View => {
  const view = window.location.hash.slice(1);
  if (!view && paymentTransaction(window.location.search)) return 'wallet';
  return ['seller', 'login', 'wallet', 'admin'].includes(view) ? (view as View) : 'catalog';
};

export default function App() {
  const [view, setView] = useState<View>(getView);
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');
  const [isDark, setIsDark] = useState(true);
  const campaign = useResource<Campaign>('/promotions');
  const runtime = useResource<{ data_mode: 'dataset' | 'remote' }>('/runtime');
  const datasetMode = runtime.data?.data_mode === 'dataset';
  const [referrals, setReferrals] = useState<Referrals | null>(null);
  const [referralError, setReferralError] = useState('');
  const [referralRevision, setReferralRevision] = useState(0);
  const refreshReferrals = useCallback(() => setReferralRevision((value) => value + 1), []);
  const nextView = useRef<View>(getView() === 'login' ? 'catalog' : getView());
  const heading = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    api
      .get<Referrals>('/referrals', { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted) {
          setReferrals(response.data);
          setReferralError('');
        }
      })
      .catch((failure) => {
        if (!controller.signal.aborted) {
          setReferrals(null);
          setReferralError(errorMessage(failure, 'No pudimos consultar tu beneficio.'));
        }
      });
    return () => controller.abort();
  }, [user, referralRevision]);
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
      const current = getView();
      if (current !== 'login') nextView.current = current;
      setUser(null);
      setReferrals(null);
      setNotice('Tu sesión terminó. Ingresa de nuevo para continuar.');
      navigate('login');
    };
    window.addEventListener('hashchange', onHash);
    window.addEventListener('tickia:session-expired', onExpired);
    const url = new URL(window.location.href);
    rememberReferral(url.search, {
      getItem: (key) => window.sessionStorage.getItem(key),
      setItem: (key, value) => window.sessionStorage.setItem(key, value),
    });
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
      setReferrals(null);
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
            {!datasetMode && (
              <button
                className="btn btn-ghost"
                aria-current={view === 'seller' ? 'page' : undefined}
                onClick={() => (user ? navigate('seller') : requireLogin('seller'))}
              >
                Vender
              </button>
            )}
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
        {campaign.data?.settings?.announcement && (
          <p className="notice">{campaign.data.settings.announcement}</p>
        )}
        {campaign.data?.settings?.maintenance_mode && (
          <p className="notice" role="status">
            Las nuevas operaciones están pausadas por mantenimiento. Puedes ingresar, consultar
            compras y presentar reclamos existentes.
          </p>
        )}
        {checkingSession && (protectedView || view === 'login') ? (
          <p role="status">Comprobando tu sesión…</p>
        ) : (
          <>
            {visibleView === 'catalog' && (
              <>
                <section className="hero-section" aria-labelledby="hero-title">
                  <p className="eyebrow">
                    {datasetMode ? 'Proyecto de Programación Avanzada' : 'Entradas entre personas'}
                  </p>
                  <h1 id="hero-title">
                    {datasetMode ? 'Tu próximo' : 'Tu entrada,'}
                    <br />
                    <span>{datasetMode ? 'gran hallazgo.' : 'su próximo plan.'}</span>
                  </h1>
                  <p>
                    {datasetMode
                      ? 'Explora productos, compara precios y conoce a sus vendedores.'
                      : 'Tickia conecta a quien ya no puede ir con quien sí quiere ir.'}
                  </p>
                  <div className="hero-actions">
                    <a className="btn btn-primary" href="#events">
                      {datasetMode ? 'Explorar productos' : 'Buscar mi evento'}{' '}
                      <span aria-hidden="true">↗</span>
                    </a>
                    {!datasetMode && (
                      <button
                        className="btn btn-secondary"
                        onClick={() => (user ? navigate('seller') : requireLogin('seller'))}
                      >
                        Vender mi entrada
                      </button>
                    )}
                  </div>
                  <div className="brand-ticket" aria-hidden="true">
                    <img src="/brand/tickia-symbol-lime.png" alt="" />
                    <span>
                      {datasetMode ? 'Encuentra eso' : 'Si tú no vas,'}
                      <br />
                      {datasetMode ? 'que buscabas.' : 'que vaya alguien.'}
                    </span>
                    <small>
                      {datasetMode
                        ? 'PRODUCTOS · VENDEDORES · HISTORIAS'
                        : 'UNA ENTRADA · DOS PERSONAS · UN PLAN'}
                    </small>
                  </div>
                </section>
                {campaign.data?.active && (
                  <p className="notice">
                    Comisión actual: {percent(campaign.data.current_commission_rate)} % para las
                    entradas que publiques durante la campaña. La tasa se conserva al vender
                    después.
                  </p>
                )}
                {user && (
                  <ReferralPanel
                    data={referrals}
                    error={referralError}
                    refresh={refreshReferrals}
                  />
                )}
                <section id="events" aria-labelledby="events-title">
                  <div className="section-heading">
                    <div>
                      <p className="eyebrow">
                        {datasetMode
                          ? 'Encuentra tu próximo favorito'
                          : 'Encuentra tu próximo plan'}
                      </p>
                      <h2 id="events-title">
                        {datasetMode ? 'Catálogo de productos' : 'Entradas disponibles'}
                      </h2>
                    </div>
                    <div className="search-field">
                      <label className="sr-only" htmlFor="event-search">
                        {datasetMode
                          ? 'Buscar productos, categorías o vendedores'
                          : 'Buscar eventos o zonas'}
                      </label>
                      <input
                        id="event-search"
                        type="search"
                        className="input-field"
                        placeholder={
                          datasetMode
                            ? 'Busca un producto, categoría o vendedor'
                            : 'Busca un evento o una zona'
                        }
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                      />
                    </div>
                  </div>
                  <div className="catalog-results">
                    {runtime.loading ? (
                      <p role="status">Cargando catálogo…</p>
                    ) : runtime.error ? (
                      <p className="error-message" role="alert">
                        {runtime.error}{' '}
                        <button className="btn btn-secondary" onClick={runtime.refresh}>
                          Reintentar
                        </button>
                      </p>
                    ) : datasetMode ? (
                      <ProductCatalog searchQuery={search} />
                    ) : (
                      <BuyerFlow
                        searchQuery={search}
                        onRequireLogin={() => requireLogin('catalog')}
                        referrals={user ? referrals : null}
                        onPaymentUpdated={refreshReferrals}
                        settings={campaign.data?.settings}
                      />
                    )}
                  </div>
                </section>
              </>
            )}
            {visibleView === 'seller' && (
              <>
                <SellerFlow campaign={campaign.data} />
                {user && (
                  <ReferralPanel
                    data={referrals}
                    error={referralError}
                    refresh={refreshReferrals}
                  />
                )}
              </>
            )}
            {visibleView === 'wallet' && (
              <>
                <WalletFlow onPaymentUpdated={refreshReferrals} />
                {user && (
                  <ReferralPanel
                    data={referrals}
                    error={referralError}
                    refresh={refreshReferrals}
                  />
                )}
              </>
            )}
            {visibleView === 'admin' &&
              (user?.is_admin ? (
                <AdminDashboard
                  onConfigurationChanged={() => {
                    campaign.refresh();
                    refreshReferrals();
                  }}
                />
              ) : (
                <p role="alert">No tienes acceso a administración.</p>
              ))}
            {visibleView === 'login' && (
              <AuthFlow
                academicMode={datasetMode}
                signedIn={!!user}
                registrationsEnabled={operationAllowed(campaign.data?.settings, 'registrations')}
                onLoginSuccess={async () => {
                  const response = await api.get<User>('/auth/me');
                  setUser(response.data);
                  setNotice(
                    datasetMode
                      ? 'Ingresaste a la versión académica de Tickia.'
                      : 'Ya puedes comprar y vender entradas.',
                  );
                  navigate(
                    paymentTransaction(window.location.search)
                      ? 'wallet'
                      : protectedView
                        ? view
                        : nextView.current,
                  );
                }}
              />
            )}
          </>
        )}
      </main>
      <footer className="site-footer container">
        <p>
          tickia ·{' '}
          {datasetMode ? 'Proyecto de Programación Avanzada.' : 'Tu entrada, su próximo plan.'}
        </p>
        <p>
          {datasetMode
            ? 'Catálogo académico · 13 tablas de datos · Sin cobros reales.'
            : 'Entradas entre personas. Tickia no es una tiquetera oficial.'}
        </p>
        <a href="https://www.instagram.com/tickia.lat/" target="_blank" rel="noopener noreferrer">
          @tickia.lat ↗
        </a>
      </footer>
    </div>
  );
}
