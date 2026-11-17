import { useEffect, useState } from 'react';
import { useResource } from '../useResource';
import { money } from '../types';
import type { User } from '../types';
import ProductDetail from './ProductDetail';
import './ProductCatalog.css';

export interface Product {
  owner_id: string | null;
  descripcion: string;
  imagen: string | null;
  id_producto: number;
  titulo: string;
  precio: number;
  categoria: string;
  vendedor: string;
  reputacion: number;
  distrito: string;
  provincia: string;
  stock: number;
  estrellas: number | null;
  total_resenas: number;
}
interface Page {
  items: Product[];
  total: number;
  page: number;
  pages: number;
}
interface Category {
  id_categoria: number;
  id_padre: number | null;
  nombre: string;
  productos: number;
}
interface Summary {
  tables: { table: string; file: string; rows: number }[];
  total_records: number;
}
const number = (value: number) => value.toLocaleString('es-PE');

function ProductResults({
  path,
  onSelect,
  onPage,
}: {
  path: string;
  onSelect: (id: number) => void;
  onPage: (page: number) => void;
}) {
  const { data, loading, error, refresh } = useResource<Page>(path);
  if (loading) return <p role="status">Cargando productos…</p>;
  if (error)
    return (
      <div className="error-message" role="alert">
        {error}{' '}
        <button className="btn btn-secondary" onClick={refresh}>
          Reintentar
        </button>
      </div>
    );
  if (!data) return null;
  return (
    <>
      <p role="status" className="muted">
        {number(data.total)} productos encontrados
      </p>
      <div className="ticket-grid">
        {data.items.length === 0 && (
          <div className="empty-state">
            <h3>No encontramos productos</h3>
            <p>Prueba otra búsqueda o cambia los filtros.</p>
          </div>
        )}
        {data.items.map((product) => (
          <article key={product.id_producto} className="ticket-card">
            {product.imagen ? (
              <img
                className="product-photo"
                src={`/api/marketplace/images/${product.imagen}`}
                alt={product.titulo}
                loading="lazy"
              />
            ) : (
              <div className="ticket-art" aria-hidden="true">
                <span>{product.categoria}</span>
                <img src="/brand/tickia-symbol.png" alt="" />
              </div>
            )}
            <div className="ticket-info">
              <p className="eyebrow">{product.categoria}</p>
              <h3>{product.titulo}</h3>
              <p>{product.vendedor}</p>
              <p className="seller-rating">Vendedor: {product.reputacion.toFixed(2)} / 5</p>
              <p className="ticket-type">
                {product.stock > 0
                  ? `${number(product.stock)} ${product.stock === 1 ? 'unidad disponible' : 'unidades disponibles'}`
                  : 'Sin stock'}
              </p>
              <div className="ticket-footer">
                <strong className="price-tag">{money(product.precio)}</strong>
                <button
                  className="btn btn-primary"
                  onClick={() => onSelect(product.id_producto)}
                  aria-label={`Comprar ${product.titulo}`}
                >
                  {product.stock > 0 ? 'Comprar' : 'Ver detalle'}
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
      {data.pages > 1 && (
        <nav className="catalog-pagination" aria-label="Páginas del catálogo">
          <button
            className="btn btn-secondary"
            disabled={data.page <= 1}
            onClick={() => onPage(data.page - 1)}
          >
            Anterior
          </button>
          <span>
            Página {number(data.page)} de {number(data.pages)}
          </span>
          <button
            className="btn btn-secondary"
            disabled={data.page >= data.pages}
            onClick={() => onPage(data.page + 1)}
          >
            Siguiente
          </button>
        </nav>
      )}
    </>
  );
}

export default function ProductCatalog({
  searchQuery,
  user,
  onRequireLogin,
  initialProduct = null,
  onSelectionClosed,
}: {
  searchQuery: string;
  user: User | null;
  onRequireLogin: (id: number) => void;
  initialProduct?: number | null;
  onSelectionClosed: () => void;
}) {
  const categories = useResource<Category[]>('/dataset/categories');
  const summary = useResource<Summary>('/dataset/summary');
  const [filters, setFilters] = useState({
    q: '',
    category: '',
    sort: 'id',
    inStock: false,
    page: 1,
  });
  const [selected, setSelected] = useState<number | null>(initialProduct);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const timer = window.setTimeout(
      () => setFilters((value) => ({ ...value, q: searchQuery, page: 1 })),
      250,
    );
    return () => window.clearTimeout(timer);
  }, [searchQuery]);
  const params = new URLSearchParams({
    q: filters.q,
    sort: filters.sort,
    in_stock: String(filters.inStock),
    page: String(filters.page),
  });
  if (filters.category) params.set('category', filters.category);
  const path = `/marketplace/products?${params}`;
  return (
    <div className="product-catalog">
      <div className="catalog-filters">
        <label>
          Categoría
          <select
            aria-label="Categoría"
            className="input-field"
            value={filters.category}
            onChange={(event) => setFilters({ ...filters, category: event.target.value, page: 1 })}
          >
            <option value="">Todas las categorías</option>
            {categories.data?.map((category) => (
              <option key={category.id_categoria} value={category.id_categoria}>
                {category.nombre}
              </option>
            ))}
          </select>
        </label>
        <label>
          Ordenar por
          <select
            aria-label="Ordenar por"
            className="input-field"
            value={filters.sort}
            onChange={(event) => setFilters({ ...filters, sort: event.target.value, page: 1 })}
          >
            <option value="id">Orden del catálogo</option>
            <option value="newest">Publicaciones más recientes</option>
            <option value="price_asc">Menor precio</option>
            <option value="price_desc">Mayor precio</option>
            <option value="rating">Mejor vendedor</option>
            <option value="stock">Mayor stock</option>
          </select>
        </label>
        <label className="stock-filter">
          <input
            type="checkbox"
            checked={filters.inStock}
            onChange={(event) => setFilters({ ...filters, inStock: event.target.checked, page: 1 })}
          />{' '}
          Solo con stock
        </label>
      </div>
      {categories.error && (
        <p className="error-message" role="alert">
          {categories.error}
          <button className="btn btn-secondary" onClick={categories.refresh}>
            Reintentar categorías
          </button>
        </p>
      )}
      <ProductResults
        key={`${path}-${revision}`}
        path={path}
        onSelect={setSelected}
        onPage={(page) => {
          setFilters({ ...filters, page });
          document.getElementById('events')?.scrollIntoView({ block: 'start' });
        }}
      />
      {summary.data && (
        <details className="dataset-summary">
          <summary>
            {summary.data.tables.length} tablas · {number(summary.data.total_records)} registros del
            dataset
          </summary>
          <dl>
            {summary.data.tables.map((table) => (
              <div key={table.table}>
                <dt>{table.file}</dt>
                <dd>{number(table.rows)} registros</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
      {selected !== null && (
        <ProductDetail
          id={selected}
          user={user}
          onRequireLogin={() => onRequireLogin(selected)}
          onPurchased={() => setRevision((value) => value + 1)}
          onClose={() => {
            setSelected(null);
            onSelectionClosed();
          }}
        />
      )}
    </div>
  );
}
