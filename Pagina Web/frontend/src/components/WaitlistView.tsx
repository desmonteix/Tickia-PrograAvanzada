import React, { useState } from 'react';

interface WaitlistStatusProps {
  status: {
    position: number;
    referral_code: string;
    referral_count: number;
    has_access: boolean;
  }
}

const WaitlistView: React.FC<WaitlistStatusProps> = ({ status }) => {
  const [copied, setCopied] = useState(false);
  const [timeLeft, setTimeLeft] = useState('');
  const shareUrl = `${window.location.origin}?ref=${status.referral_code}`;

  React.useEffect(() => {
    // Fecha de lanzamiento: 1 de Agosto de 2026 (por ejemplo)
    const launchDate = new Date('2026-08-01T12:00:00');
    
    const interval = setInterval(() => {
      const now = new Date();
      const diff = launchDate.getTime() - now.getTime();
      
      if (diff <= 0) {
        setTimeLeft('¡Lanzamiento en breve!');
        clearInterval(interval);
        return;
      }
      
      const d = Math.floor(diff / (1000 * 60 * 60 * 24));
      const h = Math.floor((diff / (1000 * 60 * 60)) % 24);
      const m = Math.floor((diff / 1000 / 60) % 60);
      const s = Math.floor((diff / 1000) % 60);
      
      setTimeLeft(`${d}d ${h.toString().padStart(2, '0')}h ${m.toString().padStart(2, '0')}m ${s.toString().padStart(2, '0')}s`);
    }, 1000);
    
    return () => clearInterval(interval);
  }, []);

  const handleCopy = () => {
    navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleShare = () => {
    if (navigator.share) {
      navigator.share({
        title: 'Únete a Tickia',
        text: '¡Entra conmigo a Tickia! El único marketplace 100% seguro de entradas nominadas en Perú.',
        url: shareUrl,
      }).catch(console.error);
    } else {
      handleCopy();
    }
  };

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '70vh', textAlign: 'center' }}>
      <div className="glass-panel" style={{ maxWidth: '600px', width: '100%', padding: '4rem 2.5rem', position: 'relative', overflow: 'hidden' }}>
        
        <div style={{ position: 'absolute', top: '-100px', left: '50%', transform: 'translateX(-50%)', width: '300px', height: '300px', background: 'var(--color-primary)', borderRadius: '50%', filter: 'blur(100px)', opacity: 0.15, zIndex: 0 }}></div>
        
        <div style={{ position: 'relative', zIndex: 1 }}>
          <h2 style={{ fontSize: '2.5rem', marginBottom: '1rem', background: 'linear-gradient(to right, var(--color-primary), #ff8a00)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            Estás en la fila
          </h2>
          
          <p style={{ fontSize: '1.2rem', color: 'var(--color-text-secondary)', marginBottom: '2rem' }}>
            Estamos liberando el acceso poco a poco para garantizar la mejor experiencia.
          </p>

          <div style={{ background: 'rgba(255, 90, 37, 0.1)', border: '1px solid var(--color-primary)', borderRadius: 'var(--border-radius)', padding: '1rem', marginBottom: '2rem' }}>
            <div style={{ fontSize: '0.9rem', color: 'var(--color-primary)', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: 'bold', marginBottom: '0.5rem' }}>Lanzamiento Oficial En</div>
            <div style={{ fontSize: '2rem', fontWeight: 'bold', fontFamily: 'monospace', color: 'var(--color-text-title)' }}>
              {timeLeft || 'Calculando...'}
            </div>
          </div>

          <div style={{ background: 'var(--color-bg-elevated)', borderRadius: 'var(--border-radius-lg)', padding: '2rem', marginBottom: '3rem', border: '1px solid var(--color-border)' }}>
            <div style={{ fontSize: '1rem', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '2px', fontWeight: 'bold' }}>Tu Posición</div>
            <div style={{ fontSize: '5rem', fontWeight: '900', lineHeight: '1', margin: '1rem 0', color: 'var(--color-text-title)' }}>
              #{status.position.toLocaleString()}
            </div>
            <div style={{ color: 'var(--color-text-secondary)' }}>
              Amigos invitados: <strong style={{ color: 'var(--color-primary)' }}>{status.referral_count}</strong>
            </div>
          </div>

          <h3 style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>Sube posiciones más rápido 🚀</h3>
          <p style={{ color: 'var(--color-text-secondary)', marginBottom: '1.5rem' }}>
            Por cada amigo que se una con tu enlace único, saltarás lugares en la fila.
          </p>
          
          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
            <button className="btn btn-primary" style={{ padding: '1rem 2rem', fontSize: '1.1rem' }} onClick={handleShare}>
              {typeof navigator.share === 'function' ? 'Compartir Enlace' : copied ? '¡Enlace Copiado!' : 'Copiar Enlace'}
            </button>
          </div>
          
        </div>
      </div>
    </div>
  );
};

export default WaitlistView;
