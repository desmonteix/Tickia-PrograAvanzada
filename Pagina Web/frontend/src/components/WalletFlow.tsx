import React, { useState, useEffect } from 'react';
import api from '../api';

interface Ticket {
  id: string;
  price: number;
  estado: string;
  created_at: string;
  event_name?: string;
  zone?: string;
}

const WalletFlow: React.FC = () => {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  const [activeQR, setActiveQR] = useState<string | null>(null);
  const [qrLoading, setQrLoading] = useState(false);
  const [currentTime, setCurrentTime] = useState(new Date().toLocaleTimeString('es-PE', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }));

  const fetchMyTickets = async () => {
    try {
      const res = await api.get('/tickets/me');
      setTickets(res.data);
    } catch (err: any) {
      console.log("No se pudo obtener mis tickets, usando mocks:", err.message);
      setTickets([
        { id: 'uuid-mio-1', price: 150.0, estado: 'VENDIDA', created_at: new Date().toISOString(), event_name: 'Concierto Mock (Tu Entrada)', zone: 'VIP' }
      ]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMyTickets();
  }, []);

  useEffect(() => {
    // Reloj en tiempo real para evitar pantallazos
    let interval: number;
    if (activeQR) {
      interval = window.setInterval(() => {
        setCurrentTime(new Date().toLocaleTimeString('es-PE', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }));
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [activeQR]);

  const handleShowQR = async (ticketId: string) => {
    setQrLoading(true);
    setError('');
    
    try {
      const res = await api.get(`/download/${ticketId}`);
      setActiveQR(res.data.qr_base64);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Error al descargar tu entrada segura.');
    } finally {
      setQrLoading(false);
    }
  };


  if (loading) return <div>Cargando tu billetera segura...</div>;

  return (
    <div className="wallet-view animate-fade-in" style={{maxWidth: '800px', margin: '0 auto'}}>
      <h2 style={{fontSize: '2rem', marginBottom: '0.5rem'}}>Mis Entradas</h2>
      <p style={{color: 'var(--color-text-secondary)', marginBottom: '2rem'}}>Tus tickets seguros listos para el evento.</p>

      {error && <div className="glass-panel" style={{color: 'var(--color-danger)', border: '1px solid var(--color-danger)', marginBottom: '1.5rem', padding: '1rem', background: 'rgba(239, 68, 68, 0.1)'}}>{error}</div>}
      
      {activeQR ? (
        <div className="active-qr-container animate-fade-in">
          <button className="btn btn-ghost" onClick={() => setActiveQR(null)} style={{marginBottom: '1rem'}}>
            ← Volver a mis entradas
          </button>
          
          <div className="digital-ticket">
            <div className="ticket-header">
              <img src="/festival_poster.jpg" alt="Event Cover" className="ticket-header-bg" />
              <div className="ticket-header-content">
                <h3>{tickets.find(t => t.id === activeQR)?.event_name || 'Evento VIP'}</h3>
                <span className="badge badge-success">VÁLIDA</span>
              </div>
            </div>
            
            <div className="qr-body">
              <p className="qr-warning">Este QR es dinámico y de uso único. No tomes capturas de pantalla.</p>
              
              <div className="qr-code-wrapper">
                <img src={`data:image/png;base64,${activeQR}`} alt="Ticket QR" />
                <div className="scan-line"></div>
              </div>
              
              <div className="timer-display">
                <span className="timer-label">HORA ACTUAL</span>
                <span className="timer-value">{currentTime}</span>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="wallet-grid">
          {tickets.length === 0 ? (
            <div className="glass-panel" style={{textAlign: 'center', padding: '3rem 2rem', gridColumn: '1/-1'}}>
              <p style={{color: 'var(--color-text-secondary)'}}>No tienes entradas compradas.</p>
            </div>
          ) : (
            tickets.map(ticket => (
              <div key={ticket.id} className="wallet-card glass-panel">
                <div className="wallet-card-header">
                  <h3 style={{margin: 0}}>{ticket.event_name || 'Entrada'}</h3>
                  <span className="badge badge-primary">COMPRADA</span>
                </div>
                
                <div className="wallet-card-body">
                  <p style={{margin: '0 0 1rem 0', color: 'var(--color-text-secondary)'}}>{ticket.zone || 'General'}</p>
                  
                  <button 
                    className="btn btn-primary w-100" 
                    onClick={() => handleShowQR(ticket.id)}
                    disabled={qrLoading}
                    style={{width: '100%', justifyContent: 'center'}}
                  >
                    {qrLoading ? 'Generando QR Dinámico...' : 'Mostrar QR de Ingreso'}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      <style>{`
        .wallet-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
          gap: 1.5rem;
        }
        
        .wallet-card {
          padding: 1.5rem;
        }
        
        .wallet-card-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 0.5rem;
        }
        
        .digital-ticket {
          background: #000;
          border-radius: var(--border-radius-lg);
          overflow: hidden;
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
          max-width: 400px;
          margin: 0 auto;
          border: 1px solid rgba(255,255,255,0.1);
        }
        
        .ticket-header {
          position: relative;
          height: 120px;
          display: flex;
          align-items: flex-end;
          padding: 1.5rem;
        }
        
        .ticket-header-bg {
          position: absolute;
          top: 0; left: 0; width: 100%; height: 100%;
          object-fit: cover;
          opacity: 0.5;
          z-index: 1;
        }
        
        .ticket-header::after {
          content: '';
          position: absolute;
          top: 0; left: 0; width: 100%; height: 100%;
          background: linear-gradient(to top, #000 0%, transparent 100%);
          z-index: 2;
        }
        
        .ticket-header-content {
          position: relative;
          z-index: 3;
          width: 100%;
          display: flex;
          justify-content: space-between;
          align-items: flex-end;
        }
        
        .ticket-header-content h3 {
          margin: 0;
          color: white;
          font-size: 1.5rem;
          text-shadow: 0 2px 4px rgba(0,0,0,0.5);
        }
        
        .qr-body {
          padding: 2rem;
          display: flex;
          flex-direction: column;
          align-items: center;
          background: #111;
        }
        
        .qr-warning {
          color: #FF5A25;
          font-size: 0.85rem;
          text-align: center;
          font-weight: 600;
          margin-bottom: 2rem;
          background: rgba(255, 90, 37, 0.1);
          padding: 8px 12px;
          border-radius: var(--border-radius-sm);
          width: 100%;
          box-sizing: border-box;
        }
        
        .qr-code-wrapper {
          background: white;
          padding: 1.5rem;
          border-radius: var(--border-radius-md);
          position: relative;
          overflow: hidden;
          box-shadow: 0 0 30px rgba(255,255,255,0.1);
        }
        
        .qr-code-wrapper img {
          display: block;
          width: 220px;
          height: 220px;
        }
        
        .scan-line {
          position: absolute;
          top: 0; left: 0; width: 100%; height: 4px;
          background: var(--color-primary);
          box-shadow: 0 0 10px var(--color-primary), 0 0 20px var(--color-primary);
          animation: scan 2s cubic-bezier(0.4, 0, 0.2, 1) infinite alternate;
          opacity: 0.7;
        }
        
        @keyframes scan {
          0% { top: 10%; }
          100% { top: 90%; }
        }
        
        .timer-display {
          margin-top: 2rem;
          text-align: center;
        }
        
        .timer-label {
          display: block;
          color: #888;
          font-size: 0.75rem;
          letter-spacing: 0.1em;
          margin-bottom: 4px;
        }
        
        .timer-value {
          color: white;
          font-family: monospace;
          font-size: 1.75rem;
          font-weight: bold;
          text-shadow: 0 0 10px rgba(255,255,255,0.5);
        }
      `}</style>
    </div>
  );
};

export default WalletFlow;
