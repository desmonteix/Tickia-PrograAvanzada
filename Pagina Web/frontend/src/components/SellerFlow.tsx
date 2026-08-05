import React, { useState, useEffect } from 'react';
import api from '../api';

const SellerFlow: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'upload' | 'sales'>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [price, setPrice] = useState('');
  const [eventName, setEventName] = useState('');
  const [zone, setZone] = useState('');
  
  const [ticketType, setTicketType] = useState('no_nominada');
  const [isRenominated, setIsRenominated] = useState(false);

  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');
  
  const [sales, setSales] = useState<any[]>([]);
  const [salesLoading, setSalesLoading] = useState(false);

  useEffect(() => {
    if (activeTab === 'sales') {
      fetchSales();
    }
  }, [activeTab]);

  const fetchSales = async () => {
    setSalesLoading(true);
    try {
      const res = await api.get('/tickets/my-sales');
      setSales(res.data);
    } catch(err) {
      console.error(err);
    } finally {
      setSalesLoading(false);
    }
  };

  const handleRenominateUpload = async (ticketId: string, e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || !e.target.files[0]) return;
    const file = e.target.files[0];
    const formData = new FormData();
    formData.append('file', file);
    try {
      await api.post(`/tickets/${ticketId}/renominate`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      alert('Renominación exitosa.');
      fetchSales();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Error al renominar la entrada');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("Debes seleccionar una imagen/PDF de la entrada.");
      return;
    }
    
    setError('');
    setSuccess('');
    setLoading(true);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('price', price);
    formData.append('event_name', eventName);
    formData.append('zone', zone);
    formData.append('ticket_type', ticketType);
    if (ticketType === 'nominada') {
      formData.append('is_renominated', isRenominated.toString());
    }

    try {
      await api.post('/tickets/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setSuccess("¡Entrada publicada y verificada exitosamente! Ya está en el catálogo.");
      setFile(null);
      setPrice('');
      setEventName('');
      setZone('');
      
    } catch (err: any) {
      setError(err.response?.data?.detail || "Error al subir la entrada.");
    } finally {
      setLoading(false);
    }
  };

  const handleBoostShare = async (sale: any) => {
    const shareUrl = `${window.location.origin}/?ref_ticket=${sale.id}`;
    
    const canvas = document.createElement('canvas');
    canvas.width = 1080;
    canvas.height = 1920;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    ctx.fillStyle = '#0f0f13';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    const grad = ctx.createLinearGradient(0, 0, 1080, 1920);
    grad.addColorStop(0, '#ff5a25');
    grad.addColorStop(1, '#0f0f13');
    ctx.globalAlpha = 0.3;
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.globalAlpha = 1.0;
    
    ctx.fillStyle = '#ff5a25';
    ctx.font = 'bold 80px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Tickia', 540, 300);
    
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 120px sans-serif';
    ctx.fillText(sale.event_name, 540, 800);
    
    ctx.font = 'normal 60px sans-serif';
    ctx.fillText(`Zona: ${sale.zone}`, 540, 950);
    
    ctx.fillStyle = '#10b981';
    ctx.font = 'bold 100px sans-serif';
    ctx.fillText(`S/ ${sale.price}`, 540, 1150);
    
    ctx.fillStyle = '#ff5a25';
    ctx.beginPath();
    ctx.roundRect(240, 1400, 600, 150, 75);
    ctx.fill();
    
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 60px sans-serif';
    ctx.fillText('Comprar Seguro', 540, 1495);
    
    canvas.toBlob((blob) => {
      if (!blob) return;
      const file = new File([blob], 'tickia_story.jpg', { type: 'image/jpeg' });
      
      const text = `¡Vendo entrada para ${sale.event_name}! Compra segura con garantía: ${shareUrl}`;
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        navigator.share({ title: 'Entrada Segura', text: text, files: [file] }).catch(err => console.error(err));
      } else {
        navigator.clipboard.writeText(text);
        const link = document.createElement('a');
        link.download = 'tickia_story.jpg';
        link.href = URL.createObjectURL(blob);
        link.click();
        alert('Se copió el link a tu portapapeles y se descargó la imagen. ¡Súbela a tu historia de IG con el sticker de "Enlace"!');
      }
    }, 'image/jpeg');
  };

  return (
    <div className="seller-view animate-fade-in" style={{display: 'flex', flexDirection: 'column', alignItems: 'center', minHeight: '60vh'}}>
      <div style={{display: 'flex', gap: '1rem', marginBottom: '2rem'}}>
        <button className={`btn ${activeTab === 'upload' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setActiveTab('upload')}>Publicar Entrada</button>
        <button className={`btn ${activeTab === 'sales' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setActiveTab('sales')}>Mis Ventas (Renominación)</button>
      </div>

      {activeTab === 'upload' && (
        <div className="glass-panel" style={{maxWidth: '600px', width: '100%', padding: '2.5rem', position: 'relative', overflow: 'hidden'}}>
          <div style={{position: 'absolute', top: '-100px', left: '-100px', width: '250px', height: '250px', background: 'var(--color-primary)', borderRadius: '50%', filter: 'blur(100px)', opacity: 0.2, zIndex: 0}}></div>
          
          <div style={{position: 'relative', zIndex: 1}}>
            <h2 style={{fontSize: '2rem', marginBottom: '0.5rem'}}>Vender una Entrada</h2>
            <p style={{color: 'var(--color-text-secondary)', marginBottom: '2rem'}}>
              Sube el archivo original con el QR. Lo verificaremos y cifraremos instantáneamente.
            </p>

            {error && <div className="badge badge-warning" style={{width: '100%', boxSizing: 'border-box', marginBottom: '1.5rem', padding: '12px', justifyContent: 'center', fontSize: '0.85rem'}}>{error}</div>}
            {success && <div className="badge badge-success" style={{width: '100%', boxSizing: 'border-box', marginBottom: '1.5rem', padding: '12px', justifyContent: 'center', fontSize: '0.85rem'}}>{success}</div>}

            <form onSubmit={handleSubmit}>
              <div className="input-group">
                <label className="input-label">Archivo de la Entrada (Imagen)</label>
                <div style={{border: '2px dashed var(--color-border)', borderRadius: 'var(--border-radius-md)', padding: '2rem', textAlign: 'center', background: 'var(--color-bg-surface-glass)', transition: 'border-color 0.3s'}}
                     onDragOver={e => { e.preventDefault(); e.currentTarget.style.borderColor = 'var(--color-primary)'; }}
                     onDragLeave={e => { e.currentTarget.style.borderColor = 'var(--color-border)'; }}
                     onDrop={e => { e.preventDefault(); e.currentTarget.style.borderColor = 'var(--color-border)'; if(e.dataTransfer.files && e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); }}>
                  
                  <div style={{fontSize: '3rem', opacity: 0.5, marginBottom: '1rem'}}>📄</div>
                  <input 
                    type="file" 
                    accept="image/png, image/jpeg" 
                    onChange={e => setFile(e.target.files ? e.target.files[0] : null)} 
                    style={{display: 'none'}}
                    id="file-upload"
                  />
                  <label htmlFor="file-upload" className="btn btn-secondary" style={{cursor: 'pointer'}}>
                    Seleccionar Archivo
                  </label>
                  {file && <p style={{marginTop: '1rem', color: 'var(--color-success)', fontWeight: 'bold'}}>✓ {file.name}</p>}
                  <p style={{marginTop: '0.5rem', fontSize: '0.8rem', color: 'var(--color-text-secondary)'}}>Arrastra el archivo o haz clic. (Max 5MB)</p>
                </div>
              </div>

              <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem'}}>
                <div className="input-group">
                  <label className="input-label">Nombre del Evento</label>
                  <input className="input-field" type="text" required value={eventName} onChange={e => setEventName(e.target.value)} placeholder="Ej. Concierto Ultra" />
                </div>

                <div className="input-group">
                  <label className="input-label">Zona o Sector</label>
                  <input className="input-field" type="text" required value={zone} onChange={e => setZone(e.target.value)} placeholder="Ej. VIP" />
                </div>
              </div>

              <div className="input-group">
                <label className="input-label">Precio de Venta (S/)</label>
                <input className="input-field" type="number" step="0.10" min="1" max="5000" required value={price} onChange={e => setPrice(e.target.value)} placeholder="0.00" style={{fontSize: '1.5rem', fontWeight: 'bold'}} />
                <p style={{fontSize: '0.75rem', color: 'var(--color-text-secondary)', marginTop: '0.5rem'}}>Comisión de plataforma (10%) será cargada al comprador.</p>
              </div>

              <div className="input-group" style={{background: 'var(--color-bg-elevated)', padding: '1.5rem', borderRadius: 'var(--border-radius-md)', border: '1px solid var(--color-border)'}}>
                <label className="input-label" style={{marginBottom: '1rem'}}>Tipo de Entrada</label>
                
                <div style={{display: 'flex', gap: '1rem', marginBottom: '1rem'}}>
                  <label style={{display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer'}}>
                    <input type="radio" value="no_nominada" checked={ticketType === 'no_nominada'} onChange={() => setTicketType('no_nominada')} />
                    <span>Al portador (No Nominada)</span>
                  </label>
                  <label style={{display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer'}}>
                    <input type="radio" value="nominada" checked={ticketType === 'nominada'} onChange={() => setTicketType('nominada')} />
                    <span>Nominada (Con nombre)</span>
                  </label>
                </div>

                {ticketType === 'nominada' && (
                  <div className="animate-fade-in" style={{paddingTop: '1rem', borderTop: '1px solid var(--color-border)'}}>
                    <label style={{display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', color: 'var(--color-warning)'}}>
                      <input type="checkbox" checked={isRenominated} onChange={(e) => setIsRenominated(e.target.checked)} />
                      <strong>Esta entrada requiere Renominación y pagué por ella.</strong>
                    </label>
                    <p style={{fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginTop: '0.5rem', marginLeft: '1.5rem'}}>
                      Nosotros gestionaremos el cambio de nombre de forma segura antes de entregarla al comprador.
                    </p>
                  </div>
                )}
              </div>

              <button type="submit" className="btn btn-primary" style={{width: '100%', padding: '16px', fontSize: '1.1rem'}} disabled={loading}>
                {loading ? 'Cifrando y Publicando...' : 'Publicar Entrada'}
              </button>
            </form>
          </div>
        </div>
      )}

      {activeTab === 'sales' && (
        <div style={{maxWidth: '800px', width: '100%'}}>
          <h2 style={{fontSize: '2rem', marginBottom: '1.5rem'}}>Mis Ventas Recientes</h2>
          
          {salesLoading ? (
            <p>Cargando ventas...</p>
          ) : sales.length === 0 ? (
            <div className="glass-panel" style={{padding: '3rem', textAlign: 'center'}}>
              <p style={{color: 'var(--color-text-secondary)'}}>No has vendido ninguna entrada recientemente.</p>
            </div>
          ) : (
            <div style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
              {sales.map(sale => (
                <div key={sale.id} className="glass-panel animate-fade-in" style={{padding: '1.5rem', borderRadius: 'var(--border-radius-md)', display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                  <div>
                    <h3 style={{margin: '0 0 0.5rem 0', fontSize: '1.2rem'}}>{sale.event_name} <span style={{fontSize: '0.9rem', color: 'var(--color-text-secondary)', fontWeight: 'normal'}}>| {sale.zone}</span></h3>
                    <p style={{margin: 0, fontWeight: 'bold', color: 'var(--color-primary)'}}>S/ {sale.price}</p>
                    {sale.estado === 'PENDIENTE_RENOMINACION' && (
                      <div style={{marginTop: '1rem', padding: '1rem', background: 'rgba(245, 158, 11, 0.1)', border: '1px solid var(--color-warning)', borderRadius: 'var(--border-radius-sm)'}}>
                        <p style={{margin: '0 0 0.5rem 0', color: 'var(--color-warning)', fontWeight: 'bold'}}>⚠️ Acción Requerida: Renomina esta entrada</p>
                        {sale.buyer && (
                          <p style={{margin: 0, fontSize: '0.9rem'}}>
                            Comprador: <strong>{sale.buyer.full_name}</strong> (DNI: {sale.buyer.dni})
                          </p>
                        )}
                        <p style={{margin: '0.5rem 0 0 0', fontSize: '0.85rem'}}>
                          Tienes hasta: {new Date(sale.renomination_deadline).toLocaleString()}
                        </p>
                      </div>
                    )}
                  </div>
                  
                  <div style={{textAlign: 'right', display: 'flex', flexDirection: 'column', gap: '0.5rem'}}>
                    {sale.estado === 'DISPONIBLE' && (
                      <button onClick={() => handleBoostShare(sale)} className="btn btn-secondary" style={{borderColor: 'var(--color-primary)', color: 'var(--color-primary)', background: 'transparent'}}>
                        🚀 Boostear (Compartir)
                      </button>
                    )}
                    {sale.estado === 'PENDIENTE_RENOMINACION' ? (
                      <div>
                        <input 
                          type="file" 
                          id={`upload-${sale.id}`} 
                          style={{display: 'none'}} 
                          accept="image/png, image/jpeg"
                          onChange={(e) => handleRenominateUpload(sale.id, e)}
                        />
                        <label htmlFor={`upload-${sale.id}`} className="btn btn-primary" style={{cursor: 'pointer'}}>
                          Subir PDF Renominado
                        </label>
                      </div>
                    ) : sale.estado !== 'DISPONIBLE' ? (
                      <span className="badge badge-success">Venta Completada</span>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SellerFlow;
