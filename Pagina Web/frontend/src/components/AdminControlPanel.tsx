import { useState } from 'react';
import AdminCampaigns from './AdminCampaigns';
import AdminSettings from './AdminSettings';
import AdminRewards from './AdminRewards';
import AdminAudit from './AdminAudit';
import './AdminControls.css';

export default function AdminControlPanel({ onChanged }: { onChanged: () => void }) {
  const [section, setSection] = useState('');
  return (
    <section aria-labelledby="admin-config-title" className="admin-controls">
      <h2 id="admin-config-title">Configuración y beneficios</h2>
      <div className="actions" aria-label="Secciones de configuración">
        {(
          [
            ['campaigns', 'Campañas'],
            ['settings', 'Operación'],
            ['rewards', 'Beneficios'],
            ['audit', 'Auditoría'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            className={`btn ${section === key ? 'btn-primary' : 'btn-secondary'}`}
            aria-pressed={section === key}
            onClick={() => setSection((value) => (value === key ? '' : key))}
          >
            {label}
          </button>
        ))}
      </div>
      {section === 'campaigns' && <AdminCampaigns onChanged={onChanged} />}
      {section === 'settings' && <AdminSettings onChanged={onChanged} />}
      {section === 'rewards' && <AdminRewards onChanged={onChanged} />}
      {section === 'audit' && <AdminAudit />}
    </section>
  );
}
