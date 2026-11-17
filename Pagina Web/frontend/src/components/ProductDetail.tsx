import { useEffect, useRef } from 'react';
import { useResource } from '../useResource';
import { money } from '../types';
import type { Product } from './ProductCatalog';

interface Detail extends Product {
  variantes: { id_variante: number; talla: string | null; color: string | null; stock: number }[];
  resenas: {
    id_resena: number;
    estrellas: number;
    comentario: string | null;
    fecha: string;
    autor: string;
  }[];
  preguntas: { id_pregunta: number; texto: string; respuesta: string | null; autor: string }[];
}

export default function ProductDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const { data, loading, error, refresh } = useResource<Detail>(`/dataset/products/${id}`);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="checkout-dialog product-dialog"
      aria-labelledby="product-title"
      onClose={onClose}
    >
      <div className="product-dialog-heading">
        <p className="eyebrow">Detalle del producto</p>
        <button
          className="btn btn-secondary"
          onClick={() => dialog.current?.close()}
          aria-label="Cerrar detalle"
        >
          Cerrar ×
        </button>
      </div>
      <h2 id="product-title">{data?.titulo ?? 'Consultando producto'}</h2>
      {loading && <p role="status">Cargando detalle…</p>}
      {error && (
        <p className="error-message" role="alert">
          {error}{' '}
          <button className="btn btn-secondary" onClick={refresh}>
            Reintentar
          </button>
        </p>
      )}
      {data && (
        <>
          <p>
            {data.categoria} · {data.distrito}, {data.provincia}
          </p>
          <p className="price-tag">{money(data.precio)}</p>
          <p>
            {data.vendedor} · Reputación: {data.reputacion.toFixed(2)} / 5
          </p>
          <p className="notice">
            Catálogo de consulta del proyecto académico. Los productos y el stock corresponden al
            dataset; no se realizan cobros.
          </p>
          <h3>Variantes y disponibilidad</h3>
          <div className="product-table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Talla</th>
                  <th scope="col">Color</th>
                  <th scope="col">Stock</th>
                </tr>
              </thead>
              <tbody>
                {data.variantes.map((variant) => (
                  <tr key={variant.id_variante}>
                    <td>{variant.talla ?? 'No especificada'}</td>
                    <td>{variant.color ?? 'No especificado'}</td>
                    <td>{variant.stock}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.variantes.length === 0 && <p>No hay variantes registradas.</p>}
          <h3>
            Reseñas{' '}
            {data.estrellas !== null &&
              `· ${data.estrellas.toFixed(2)} / 5 (${data.total_resenas})`}
          </h3>
          {data.resenas.length === 0 && <p>Aún no hay reseñas para este producto.</p>}
          {data.total_resenas > 10 && <p className="muted">Las 10 reseñas más recientes.</p>}
          <ul className="product-comments">
            {data.resenas.map((review) => (
              <li key={review.id_resena}>
                <strong>
                  {review.autor} · {review.estrellas} / 5
                </strong>
                <p>{review.comentario ?? 'Sin comentario.'}</p>
                <small>{review.fecha}</small>
              </li>
            ))}
          </ul>
          <h3>Preguntas recientes</h3>
          {data.preguntas.length === 0 && <p>No hay preguntas registradas.</p>}
          <ul className="product-comments">
            {data.preguntas.map((question) => (
              <li key={question.id_pregunta}>
                <strong>{question.autor}</strong>
                <p>{question.texto}</p>
                <p className="muted">{question.respuesta ?? 'Sin respuesta todavía.'}</p>
              </li>
            ))}
          </ul>
        </>
      )}
    </dialog>
  );
}
