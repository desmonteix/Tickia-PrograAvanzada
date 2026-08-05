import { useState, useEffect } from 'react';
import api from './api';
import './index.css';
import SellerFlow from './components/SellerFlow';
import BuyerFlow from './components/BuyerFlow';
import AuthFlow from './components/AuthFlow';
import WalletFlow from './components/WalletFlow';
import AdminDashboard from './components/AdminDashboard';
import WaitlistView from './components/WaitlistView';

function App() {
  const [currentView, setCurrentView] = useState('catalog'); // 'catalog', 'seller', 'login', 'wallet', 'admin'
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [waitlistStatus, setWaitlistStatus] = useState<any>(null);
  
  // Theme state (default dark)
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  useEffect(() => {
    // Checkear url por params de tracking
    const urlParams = new URLSearchParams(window.location.search);
    const refTicket = urlParams.get('ref_ticket');
    if (refTicket) {
      api.post(`/tickets/${refTicket}/track-visit`).catch(() => {});
      // Limpiar URL
      window.history.replaceState({}, '', window.location.pathname);
    }
    
    // Checkear sesión con el backend usando cookies
    const checkAuth = async () => {
      try {
        const response = await api.get('/auth/me');
        setIsAuthenticated(true);
        if (response.data?.is_admin) {
          setIsAdmin(true);
        }
        
        try {
          const wlResponse = await api.get('/auth/waitlist/status');
          setWaitlistStatus(wlResponse.data);
          if (!wlResponse.data.has_access && !response.data?.is_admin) {
            setCurrentView('waitlist');
          }
        } catch(e) {}
        
      } catch (err) {
        setIsAuthenticated(false);
        setIsAdmin(false);
      }
    };
    checkAuth();
  }, []);

  const handleLogout = async () => {
    try {
      await api.post('/auth/logout');
    } catch (err) {
      console.error("Error logging out", err);
    }
    setIsAuthenticated(false);
    setIsAdmin(false);
    setCurrentView('catalog');
  };

  return (
    <div className="app-container">
      <nav className="navbar glass-panel">
        <div className="logo-container" onClick={() => {
          if (isAuthenticated && !waitlistStatus?.has_access && !isAdmin) {
            setCurrentView('waitlist');
          } else {
            setCurrentView('catalog');
          }
        }} style={{cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px', transition: 'transform 0.2s', flexShrink: 0}} onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.05)'} onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}>
          <svg width="36" height="36" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M 4 20 L 14 20" stroke="var(--color-primary)" strokeWidth="3.5" strokeLinecap="round"/>
            <path d="M 7 14 L 15 14" stroke="var(--color-primary)" strokeWidth="3.5" strokeLinecap="round"/>
            <path d="M 10 26 L 16 26" stroke="var(--color-primary)" strokeWidth="3.5" strokeLinecap="round"/>
            <path d="M 2 17 L 9 17" stroke="var(--color-primary)" strokeWidth="3.5" strokeLinecap="round"/>
            <path d="M 5 23 L 11 23" stroke="var(--color-primary)" strokeWidth="3.5" strokeLinecap="round"/>
            <g transform="rotate(-8, 24, 20)">
              <path d="M 14 10 C 14 8.5 15.5 7.5 17 7.5 L 32 7.5 C 34 7.5 35 9 35 11 L 35 16 A 3 3 0 0 0 35 24 L 35 29 C 35 31 34 32.5 32 32.5 L 17 32.5 C 15.5 32.5 14 31.5 14 30 L 14 10 Z" fill="var(--color-primary)"/>
              <path d="M 20 20 L 23 23 L 29 15" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
            </g>
          </svg>
          <span style={{color: 'var(--color-text-title)', fontWeight: '800', fontSize: '1.8rem', letterSpacing: '-0.03em'}}>Tickia</span>
        </div>

        {currentView === 'catalog' && (!isAuthenticated || waitlistStatus?.has_access || isAdmin) && (
          <div style={{flex: 1, maxWidth: '600px', margin: '0 2rem'}}>
            <input 
              type="text"
              placeholder="Buscar eventos o zonas (ej. Bad Bunny)"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: '100%', 
                padding: '1rem 1.8rem', 
                fontSize: '1.15rem',
                fontWeight: '500',
                borderRadius: '50px',
                border: '2px solid rgba(0,0,0,0.1)',
                background: '#FFFFFF',
                color: '#0A0A0A',
                outline: 'none',
                boxShadow: '0 4px 15px rgba(0,0,0,0.08)',
                transition: 'all 0.2s ease'
              }}
              onFocus={(e) => {
                e.target.style.boxShadow = '0 6px 20px rgba(255, 90, 37, 0.15)';
                e.target.style.borderColor = 'var(--color-primary)';
              }}
              onBlur={(e) => {
                e.target.style.boxShadow = '0 4px 15px rgba(0,0,0,0.08)';
                e.target.style.borderColor = 'rgba(0,0,0,0.1)';
              }}
            />
          </div>
        )}

        <div className="nav-links" style={{flexShrink: 0}}>
          {(!isAuthenticated || (waitlistStatus?.has_access || isAdmin)) && (
            <>
              <button 
                className={`btn ${currentView === 'catalog' ? 'btn-secondary' : 'btn-ghost'}`} 
                onClick={() => setCurrentView('catalog')}
              >
                Explorar
              </button>
              
              {isAuthenticated && (
                <button 
                  className={`btn ${currentView === 'wallet' ? 'btn-secondary' : 'btn-ghost'}`} 
                  onClick={() => setCurrentView('wallet')} 
                >
                  Mis Entradas
                </button>
              )}

              {isAdmin && (
                <button 
                  className={`btn ${currentView === 'admin' ? 'btn-secondary' : 'btn-ghost'}`} 
                  onClick={() => setCurrentView('admin')} 
                  style={{color: 'var(--color-danger)'}}
                >
                  Admin Panel
                </button>
              )}

              <button 
                className={`btn ${currentView === 'seller' ? 'btn-secondary' : 'btn-ghost'}`} 
                onClick={() => {
                  if (!isAuthenticated) return setCurrentView('login');
                  setCurrentView('seller');
                }}
              >
                Vender
              </button>

              <div style={{width: '1px', height: '24px', background: 'var(--color-border)', margin: '0 8px'}}></div>
            </>
          )}

          <button 
            className="btn btn-ghost" 
            onClick={() => setIsDark(!isDark)}
            title="Cambiar Tema"
            style={{padding: '8px', borderRadius: '50%'}}
          >
            {isDark ? '☀️' : '🌙'}
          </button>
          
          {isAuthenticated ? (
            <button className="btn btn-ghost" onClick={handleLogout}>Salir</button>
          ) : (
            <button className="btn btn-primary" onClick={() => setCurrentView('login')}>Ingresar</button>
          )}
        </div>
      </nav>

      <main className="main-content container animate-fade-in" style={{marginTop: '100px'}}>
        {currentView === 'catalog' && (
           <>
             <div className="hero-section" style={{textAlign: 'center', padding: '4rem 0 3rem 0'}}>
               <h1 style={{fontSize: '3.5rem', margin: '0'}}>
                 El marketplace <span className="text-gradient-primary">infalible</span> para tus entradas.
               </h1>
             </div>
             <BuyerFlow searchQuery={searchQuery} onRequireLogin={() => setCurrentView('login')} />
           </>
        )}
        {currentView === 'waitlist' && waitlistStatus && <WaitlistView status={waitlistStatus} />}
        {currentView === 'seller' && <SellerFlow />}
        {currentView === 'wallet' && <WalletFlow />}
        {currentView === 'admin' && <AdminDashboard />}
        {currentView === 'login' && (
          <AuthFlow onLoginSuccess={async () => {
            setIsAuthenticated(true);
            try {
              const res = await api.get('/auth/me');
              const isAdmin = res.data?.is_admin;
              setIsAdmin(isAdmin);
              const wlResponse = await api.get('/auth/waitlist/status');
              setWaitlistStatus(wlResponse.data);
              if (!wlResponse.data.has_access && !isAdmin) {
                setCurrentView('waitlist');
              } else {
                setCurrentView('catalog');
              }
            } catch(e) {
              setCurrentView('catalog');
            }
          }} />
        )}
      </main>

      <style>{`
        .app-container {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
        }
        .navbar {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          z-index: 100;
          margin: 1rem 2rem;
          padding: 1rem 1.5rem;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .nav-links {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .main-content {
          padding: 2rem;
          max-width: 1200px;
          margin: 0 auto;
          flex: 1;
          width: 100%;
          box-sizing: border-box;
        }
        .mock-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
          gap: 1.5rem;
          margin-top: 2rem;
        }
        .ticket-card, .form-card {
          background: white;
          padding: 1.5rem;
          border-radius: var(--border-radius-lg);
          border: 1px solid var(--color-border);
          box-shadow: 0 4px 6px rgba(0,0,0,0.05);
          transition: transform 0.2s ease;
        }
        .ticket-card:hover {
          transform: translateY(-5px);
          border-color: var(--color-primary);
        }
        .price-tag {
          font-size: 1.5rem;
          font-weight: bold;
          color: var(--color-text-title);
          margin: 1rem 0;
        }
        input.input-field, input[type="number"], input[type="file"] {
            border: 1px solid var(--color-border);
            border-radius: var(--border-radius-sm);
            padding: 0.5rem;
        }
      `}</style>
    </div>
  );
}

export default App;
