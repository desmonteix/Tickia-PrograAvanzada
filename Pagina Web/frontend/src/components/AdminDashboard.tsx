import React, { useState, useEffect } from 'react';
import api from '../api';

interface Metrics {
  total_users: number;
  total_tickets: number;
  total_transactions: number;
  total_revenue: number;
}

interface User {
  id: string;
  email: string;
  trust_score: number;
  is_suspended: boolean;
  banned_until: string | null;
  is_admin: boolean;
}

const AdminDashboard: React.FC = () => {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [metricsRes, usersRes] = await Promise.all([
        api.get('/admin/metrics'),
        api.get('/admin/users')
      ]);
      setMetrics(metricsRes.data);
      setUsers(usersRes.data);
      setError('');
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Error loading admin data');
    } finally {
      setLoading(false);
    }
  };

  const handleBanUser = async (userId: string, days: number) => {
    if (!window.confirm(`¿Seguro que quieres banear a este usuario por ${days} días?`)) return;
    try {
      await api.post(`/admin/users/${userId}/ban?days=${days}`);
      alert(`Usuario baneado exitosamente por ${days} días.`);
      fetchData();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Error al banear usuario');
    }
  };

  if (loading) {
    return <div style={{textAlign: 'center', padding: '4rem'}}>Cargando panel de administración...</div>;
  }

  if (error) {
    return <div style={{textAlign: 'center', padding: '4rem', color: 'var(--color-danger)'}}>{error}</div>;
  }

  return (
    <div className="admin-dashboard animate-fade-in" style={{padding: '2rem'}}>
      <h1 style={{marginBottom: '2rem'}}>Panel de Administración</h1>
      
      <div className="metrics-grid" style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '3rem'}}>
        <div className="glass-panel" style={{padding: '1.5rem', borderRadius: 'var(--border-radius-lg)', textAlign: 'center'}}>
          <h3 style={{color: 'var(--color-text-secondary)', margin: '0 0 0.5rem 0'}}>Usuarios Totales</h3>
          <p style={{fontSize: '2rem', fontWeight: 'bold', margin: '0'}}>{metrics?.total_users}</p>
        </div>
        <div className="glass-panel" style={{padding: '1.5rem', borderRadius: 'var(--border-radius-lg)', textAlign: 'center'}}>
          <h3 style={{color: 'var(--color-text-secondary)', margin: '0 0 0.5rem 0'}}>Entradas Publicadas</h3>
          <p style={{fontSize: '2rem', fontWeight: 'bold', margin: '0'}}>{metrics?.total_tickets}</p>
        </div>
        <div className="glass-panel" style={{padding: '1.5rem', borderRadius: 'var(--border-radius-lg)', textAlign: 'center'}}>
          <h3 style={{color: 'var(--color-text-secondary)', margin: '0 0 0.5rem 0'}}>Transacciones</h3>
          <p style={{fontSize: '2rem', fontWeight: 'bold', margin: '0'}}>{metrics?.total_transactions}</p>
        </div>
        <div className="glass-panel" style={{padding: '1.5rem', borderRadius: 'var(--border-radius-lg)', textAlign: 'center'}}>
          <h3 style={{color: 'var(--color-text-secondary)', margin: '0 0 0.5rem 0'}}>Ingresos Plataforma</h3>
          <p style={{fontSize: '2rem', fontWeight: 'bold', margin: '0', color: 'var(--color-success)'}}>S/ {metrics?.total_revenue.toFixed(2)}</p>
        </div>
      </div>

      <h2>Gestión de Usuarios</h2>
      <div className="glass-panel" style={{borderRadius: 'var(--border-radius-lg)', overflow: 'hidden'}}>
        <table style={{width: '100%', borderCollapse: 'collapse', textAlign: 'left'}}>
          <thead>
            <tr style={{background: 'rgba(0,0,0,0.1)'}}>
              <th style={{padding: '1rem'}}>Email</th>
              <th style={{padding: '1rem'}}>Trust Score</th>
              <th style={{padding: '1rem'}}>Estado</th>
              <th style={{padding: '1rem'}}>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {users.map(user => (
              <tr key={user.id} style={{borderTop: '1px solid var(--color-border)'}}>
                <td style={{padding: '1rem'}}>
                  {user.email}
                  {user.is_admin && <span style={{marginLeft: '8px', fontSize: '0.8rem', background: 'var(--color-primary)', color: 'white', padding: '2px 6px', borderRadius: '4px'}}>ADMIN</span>}
                </td>
                <td style={{padding: '1rem'}}>
                  <span style={{color: user.trust_score < 50 ? 'var(--color-danger)' : 'var(--color-success)'}}>
                    {user.trust_score}
                  </span>
                </td>
                <td style={{padding: '1rem'}}>
                  {user.banned_until && new Date(user.banned_until) > new Date() ? (
                    <span style={{color: 'var(--color-danger)'}}>Baneado hasta {new Date(user.banned_until).toLocaleDateString()}</span>
                  ) : user.is_suspended ? (
                    <span style={{color: 'var(--color-danger)'}}>Suspendido</span>
                  ) : (
                    <span style={{color: 'var(--color-success)'}}>Activo</span>
                  )}
                </td>
                <td style={{padding: '1rem'}}>
                  {!user.is_admin && (
                    <button 
                      className="btn" 
                      style={{background: 'transparent', border: '1px solid var(--color-danger)', color: 'var(--color-danger)', padding: '0.4rem 0.8rem'}}
                      onClick={() => handleBanUser(user.id, 7)}
                      disabled={!!(user.banned_until && new Date(user.banned_until) > new Date())}
                    >
                      Ban 7 Días
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default AdminDashboard;
