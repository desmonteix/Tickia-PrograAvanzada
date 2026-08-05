import React, { useState, useEffect } from 'react';
import api from '../api';
import Fuse from 'fuse.js';

declare global {
  interface Window {
    Culqi: any;
    culqi: () => void;
  }
}

interface Ticket {
  id: string;
  price: number;
  estado: string;
  created_at: string;
  event_name?: string;
  zone?: string;
  ticket_type?: string;
  ticket_type?: string;
  is_renominated?: boolean;
  boosted_until?: string;
}

interface BuyerFlowProps {
  onRequireLogin?: () => void;
  searchQuery?: string;
}

const BuyerFlow: React.FC<BuyerFlowProps> = ({ onRequireLogin, searchQuery = '' }) => {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reservingId, setReservingId] = useState<string | null>(null);
  
  const [filteredTickets, setFilteredTickets] = useState<Ticket[]>([]);

  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredTickets(tickets);
      return;
    }
    const fuse = new Fuse(tickets, {
      keys: ['event_name', 'zone'],
      threshold: 0.4,
    });
    const results = fuse.search(searchQuery);
    setFilteredTickets(results.map(r => r.item));
  }, [searchQuery, tickets]);

  const fetchTickets = async () => {
    try {
      const res = await api.get('/tickets');
      setTickets(res.data);
    } catch (err: any) {
      console.log("No se pudo obtener tickets, usando mocks:", err.message);
      setTickets([
        { id: 'uuid-mock-1', price: 150.0, estado: 'ACTIVO', created_at: new Date().toISOString(), event_name: 'Concierto Mock', zone: 'VIP', ticket_type: 'nominada', is_renominated: false },
        { id: 'uuid-mock-2', price: 200.0, estado: 'ACTIVO', created_at: new Date().toISOString(), event_name: 'Festival Mock', zone: 'General', ticket_type: 'no_nominada', is_renominated: true }
      ]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTickets();
    
    // Configurar Culqi global callback
    window.culqi = async () => {
      if (window.Culqi.token) {
        const token = window.Culqi.token.id;
        try {
          const ticketId = window.sessionStorage.getItem('culqi_ticket_id');
          if (!ticketId) throw new Error("No hay un ticket activo para procesar el pago");

          await api.post('/payments/charge', {
            ticket_id: ticketId,
            culqi_token: token
          });
          
          alert(`¡Pago Exitoso! Tu entrada ha sido comprada.`);
          fetchTickets();
        } catch (err: any) {
          setError(err.response?.data?.detail || 'Error al procesar el cargo en el backend.');
        }
      } else {
        if (window.Culqi.error && window.Culqi.error.user_message) {
          setError(`Error de pago: ${window.Culqi.error.user_message}`);
        } else {
          setError('El modal de pago fue cerrado sin completar la compra.');
        }
      }
      setReservingId(null);
    };

  }, []);

  const handleBuy = async (ticket: Ticket) => {
    setReservingId(ticket.id);
    setError('');
    const publicKey = 'pk_test_3ed9b6b772c84218'; 
    
    try {
      // 1. Bloqueo atómico
      await api.post(`/tickets/${ticket.id}/buy`);
      
      // 2. Configurar Culqi para este ticket
      window.sessionStorage.setItem('culqi_ticket_id', ticket.id);
      
      // eslint-disable-next-line
      window.Culqi.publicKey = publicKey;
      window.Culqi.settings({
        title: 'Tickia',
        currency: 'PEN',
        amount: ticket.price * 100, 
        order: '' 
      });
      window.Culqi.options({
        lang: 'auto',
        modal: true,
        installments: false,
        customButton: 'Pagar Entrada'
      });
      
      // 3. Abrir el modal
      window.Culqi.open();
      
    } catch (err: any) {
      if (err.response?.status === 401 && onRequireLogin) {
        onRequireLogin();
        return;
      }
      setError(err.response?.data?.detail || 'Error al intentar comprar la entrada.');
      setReservingId(null);
      fetchTickets();
    }
  };

  if (loading) return <div>Cargando entradas seguras...</div>;

  return (
    <div className="catalog-view animate-fade-in">
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem'}}>
        <div>
          <h2 style={{fontSize: '2rem', margin: '0'}}>Próximos Eventos</h2>
        </div>
      </div>
      
      {error && (
        <div className="glass-panel" style={{color: 'var(--color-danger)', border: '1px solid var(--color-danger)', marginBottom: '1.5rem', padding: '1rem', background: 'rgba(239, 68, 68, 0.1)'}}>
          <strong style={{marginRight: '8px'}}>⚠ Error:</strong> {error}
        </div>
      )}

      <div className="ticket-grid">
        {filteredTickets.length === 0 ? (
          <div className="glass-panel" style={{textAlign: 'center', padding: '4rem 2rem', gridColumn: '1 / -1'}}>
             <div style={{fontSize: '3rem', opacity: 0.5, marginBottom: '1rem'}}>🎫</div>
             <h3>No hay entradas disponibles</h3>
             <p style={{color: 'var(--color-text-secondary)'}}>Sé el primero en vender una entrada para tu evento favorito.</p>
          </div>
        ) : (
          filteredTickets.map(ticket => (
            <div key={ticket.id} className="ticket-card glass-panel">
              <div className="ticket-image-container">
                <img src="/festival_poster.jpg" alt="Event Cover" className="ticket-image" />
                <div className="ticket-badge-overlay">
                  <span className="badge badge-success" style={{backdropFilter: 'blur(8px)', background: 'rgba(16, 185, 129, 0.2)'}}>
                    ✓ Verificado
                  </span>
                </div>
              </div>
              
              <div className="ticket-info">
                {ticket.boosted_until && new Date(ticket.boosted_until) > new Date() && (
                  <div style={{marginBottom: '0.8rem'}}>
                    <span className="badge badge-warning" style={{background: 'rgba(255, 90, 37, 0.15)', color: 'var(--color-primary)', border: '1px solid var(--color-primary)'}}>🔥 Destacado</span>
                  </div>
                )}
                <h3 className="ticket-title">{ticket.event_name || 'Festival Ultra 2026'}</h3>
                <p className="ticket-zone">{ticket.zone || 'Zona VIP'}</p>
                
                <div className="ticket-details">
                  <div className="detail-item">
                    <span className="detail-label">TIPO</span>
                    <span className="detail-value">{ticket.ticket_type === 'nominada' ? 'Nominada' : 'No Nominada'}</span>
                  </div>
                  {ticket.ticket_type === 'nominada' && (
                    <div className="detail-item">
                      <span className="detail-label">RENOMINADA</span>
                      <span className="detail-value">{ticket.is_renominated ? 'Sí' : 'No'}</span>
                    </div>
                  )}
                  <div className="detail-item">
                    <span className="detail-label">ID SEGURO</span>
                    <span className="detail-value" style={{fontFamily: 'monospace'}}>{ticket.id.split('-')[0]}</span>
                  </div>
                </div>

                <div className="ticket-footer">
                  <div className="ticket-price">
                    <span className="currency">S/</span>
                    <span className="amount">{ticket.price.toFixed(2)}</span>
                  </div>
                  <button 
                    className="btn btn-primary"
                    onClick={() => handleBuy(ticket)}
                    disabled={reservingId === ticket.id}
                  >
                    {reservingId === ticket.id ? 'Reservando...' : 'Comprar'}
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      <style>{`
        .ticket-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
          gap: 2rem;
        }
        
        .ticket-card {
          border-radius: var(--border-radius-lg);
          overflow: hidden;
          transition: transform var(--transition-normal), box-shadow var(--transition-normal);
          display: flex;
          flex-direction: column;
        }
        
        .ticket-card:hover {
          transform: translateY(-5px);
          box-shadow: var(--shadow-lg);
          border-color: var(--color-primary-glow);
        }
        
        .ticket-image-container {
          position: relative;
          width: 100%;
          height: 200px;
          overflow: hidden;
        }
        
        .ticket-image {
          width: 100%;
          height: 100%;
          object-fit: cover;
          transition: transform var(--transition-slow);
        }
        
        .ticket-card:hover .ticket-image {
          transform: scale(1.05);
        }
        
        .ticket-badge-overlay {
          position: absolute;
          top: 1rem;
          left: 1rem;
          z-index: 2;
        }
        
        .ticket-info {
          padding: 1.5rem;
          display: flex;
          flex-direction: column;
          flex: 1;
        }
        
        .ticket-title {
          font-size: 1.25rem;
          margin: 0 0 0.25rem 0;
          line-height: 1.3;
          color: var(--color-text-title);
          font-weight: 800;
        }
        
        .ticket-zone {
          color: var(--color-primary);
          font-weight: 600;
          font-size: 0.95rem;
          margin: 0 0 1.25rem 0;
        }
        
        .ticket-details {
          display: flex;
          flex-wrap: wrap;
          gap: 1rem;
          margin-bottom: 1.5rem;
          padding-bottom: 1.5rem;
          border-bottom: 1px dashed var(--color-border);
        }
        
        .detail-item {
          display: flex;
          flex-direction: column;
        }
        
        .detail-label {
          font-size: 0.75rem;
          color: #000000 !important;
          font-weight: 800;
          letter-spacing: 0.05em;
          margin-bottom: 0.2rem;
        }
        
        .detail-value {
          font-size: 0.9rem;
          color: #000000 !important;
          font-weight: 700;
        }
        
        .ticket-footer {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: auto;
        }
        
        .ticket-price {
          display: flex;
          align-items: baseline;
          gap: 0.25rem;
        }
        
        .ticket-price .currency {
          font-size: 1.2rem;
          color: var(--color-text-title);
          font-weight: 700;
        }
        
        .ticket-price .amount {
          font-size: 2rem;
          font-weight: 800;
          color: var(--color-text-title);
          letter-spacing: -0.05em;
        }
      `}</style>
    </div>
  );
};

export default BuyerFlow;
