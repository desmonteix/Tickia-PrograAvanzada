import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import api, { errorMessage } from '../api';
import { useResource } from '../useResource';
import { money } from '../types';
import type { Product } from './ProductCatalog';
import MarketplaceOrders from './MarketplaceOrders';

interface Listings {
  items: Product[];
  total: number;
  page: number;
  pages: number;
}

function MyProducts({
  page,
  onPage,
  onSelect,
}: {
  page: number;
  onPage: (page: number) => void;
  onSelect: (id: number) => void;
}) {
  const { data, loading, error, refresh } = useResource<Listings>(
    `/marketplace/my-products?page=${page}`,
  );
  if (loading) return <p role="status">Cargando publicaciones…</p>;
  if (error)
    return (
      <p className="error-message" role="alert">
        {error}{' '}
        <button className="btn btn-secondary" onClick={refresh}>
          Reintentar
        </button>
      </p>
    );
  return (
    <>
      {!data?.items.length && <p>Tus productos publicados aparecerán aquí.</p>}
      <div className="marketplace-orders">
        {data?.items.map((product) => (
          <article className="form-card" key={product.id_producto}>
            <h3>{product.titulo}</h3>
            <p>
              {money(product.precio)} · {product.stock} unidades disponibles
            </p>
            <button className="btn btn-secondary" onClick={() => onSelect(product.id_producto)}>
              Ver publicación
            </button>
          </article>
        ))}
      </div>
      {data && data.pages > 1 && (
        <nav className="catalog-pagination" aria-label="Páginas de publicaciones">
          <button
            className="btn btn-secondary"
            disabled={page <= 1}
            onClick={() => onPage(page - 1)}
          >
            Anterior
          </button>
          <span>
            Página {page} de {data.pages}
          </span>
          <button
            className="btn btn-secondary"
            disabled={page >= data.pages}
            onClick={() => onPage(page + 1)}
          >
            Siguiente
          </button>
        </nav>
      )}
    </>
  );
}

export default function MarketplaceSeller({ onSelect }: { onSelect: (id: number) => void }) {
  const categories = useResource<{ id_categoria: number; nombre: string }[]>('/dataset/categories');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [published, setPublished] = useState<Product | null>(null);
  const [revision, setRevision] = useState(0);
  const [page, setPage] = useState(1);
  const submitting = useRef(false);
  async function publish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    const form = event.currentTarget;
    const payload = new FormData(form);
    const photo = payload.get('foto');
    if (photo instanceof File && photo.size > 5 * 1024 * 1024) {
      setError('La foto no debe superar 5 MB.');
      return;
    }
    if (photo instanceof File && photo.size === 0) payload.delete('foto');
    submitting.current = true;
    setBusy(true);
    setError('');
    setPublished(null);
    try {
      const response = await api.post<Product>('/marketplace/products', payload);
      setPublished(response.data);
      form.reset();
      setPage(1);
      setRevision((value) => value + 1);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <div className="marketplace-seller">
      <section className="form-card" aria-labelledby="sell-product-title">
        <p className="eyebrow">Tu próximo comprador está aquí</p>
        <h1 id="sell-product-title">Publicar un producto</h1>
        <p>
          Agrega los datos de tu artículo. Aparecerá en el catálogo para que otras personas puedan
          comprarlo.
        </p>
        {error && (
          <p className="error-message" role="alert">
            {error}
          </p>
        )}
        {categories.error && (
          <p className="error-message" role="alert">
            {categories.error}{' '}
            <button className="btn btn-secondary" onClick={categories.refresh}>
              Reintentar categorías
            </button>
          </p>
        )}
        {published && (
          <div className="notice" role="status">
            <strong>Producto publicado</strong>
            <p>{published.titulo} ya está disponible.</p>
            <button className="btn btn-primary" onClick={() => onSelect(published.id_producto)}>
              Ver en el catálogo
            </button>
          </div>
        )}
        <form onSubmit={(event) => void publish(event)}>
          <fieldset disabled={busy} className="marketplace-fieldset">
            <div className="input-group">
              <label htmlFor="sell-title">Nombre del producto</label>
              <input
                id="sell-title"
                name="titulo"
                className="input-field"
                minLength={3}
                maxLength={160}
                required
              />
            </div>
            <div className="input-group">
              <label htmlFor="sell-description">Descripción</label>
              <textarea
                id="sell-description"
                name="descripcion"
                className="input-field"
                maxLength={2000}
                rows={4}
              />
            </div>
            <div className="form-row">
              <div className="input-group">
                <label htmlFor="sell-price">Precio (S/)</label>
                <input
                  id="sell-price"
                  name="precio"
                  className="input-field"
                  type="number"
                  min="0.01"
                  max="1000000"
                  step="0.01"
                  required
                />
              </div>
              <div className="input-group">
                <label htmlFor="sell-stock">Stock disponible</label>
                <input
                  id="sell-stock"
                  name="stock"
                  className="input-field"
                  type="number"
                  min="1"
                  max="1000000"
                  step="1"
                  required
                />
              </div>
            </div>
            <div className="input-group">
              <label htmlFor="sell-category">Categoría del producto</label>
              <select
                id="sell-category"
                name="id_categoria"
                className="input-field"
                required
                defaultValue=""
                disabled={categories.loading || !!categories.error}
              >
                <option value="" disabled>
                  Selecciona una categoría
                </option>
                {categories.data?.map((category) => (
                  <option key={category.id_categoria} value={category.id_categoria}>
                    {category.nombre}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-row">
              <div className="input-group">
                <label htmlFor="sell-size">Talla o tamaño</label>
                <input
                  id="sell-size"
                  name="talla"
                  className="input-field"
                  maxLength={60}
                  defaultValue="Única"
                />
              </div>
              <div className="input-group">
                <label htmlFor="sell-color">Color</label>
                <input
                  id="sell-color"
                  name="color"
                  className="input-field"
                  maxLength={60}
                  defaultValue="No especificado"
                />
              </div>
            </div>
            <div className="input-group">
              <label htmlFor="sell-photo">Foto del producto (opcional)</label>
              <input
                id="sell-photo"
                name="foto"
                className="input-field"
                type="file"
                accept="image/png,image/jpeg"
                aria-describedby="sell-photo-hint"
              />
              <small id="sell-photo-hint">PNG o JPEG, hasta 5 MB.</small>
            </div>
            <button
              className="btn btn-primary"
              type="submit"
              disabled={busy || categories.loading || !!categories.error}
            >
              {busy ? 'Publicando…' : 'Publicar producto'}
            </button>
          </fieldset>
        </form>
      </section>
      <section>
        <h2>Mis publicaciones</h2>
        <MyProducts key={`${revision}-${page}`} page={page} onPage={setPage} onSelect={onSelect} />
      </section>
      <MarketplaceOrders kind="sales" />
    </div>
  );
}
