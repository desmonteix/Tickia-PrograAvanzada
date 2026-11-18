import { useState } from 'react';
import { useResource } from '../useResource';
import { money } from '../types';

const REPORTS = [
  ['diagnostico', 'Ventas altas, mala reputación y retrasos'],
  ['rfm', 'Segmentación RFM'],
  ['cohortes', 'Cohortes y retención'],
  ['cocompras', 'Productos comprados juntos'],
  ['entregas', 'Entregas por courier y departamento'],
  ['vendedores', 'Reputación y ventas por vendedor'],
  ['ventas_distrito', 'Ventas por vendedor y distrito'],
  ['stock', 'Stock crítico'],
  ['categorias', 'Categorías jerárquicas'],
];
type Cell = string | number | null;
type ChartPoint =
  | { label: string; value: number }
  | {
      razon_social: string;
      ventas_brutas: number;
      estrellas_promedio: number;
      retraso_pct: number;
    };
interface Report {
  columns: string[];
  items: Record<string, Cell>[];
  total: number;
  page: number;
  pages: number;
  notes: string;
  chart: ChartPoint[];
  generated_at: string;
  criteria: { ventas_altas_desde: number; correlacion_estrellas_retrasos: number | null } | null;
}
interface Summary {
  summary: Record<string, number>;
  reference_date: string;
  generated_at: string;
}

function Chart({ points }: { points: ChartPoint[] }) {
  const bars = points.filter(
    (point): point is { label: string; value: number } => 'label' in point,
  );
  const scatter = points.filter(
    (
      point,
    ): point is {
      razon_social: string;
      ventas_brutas: number;
      estrellas_promedio: number;
      retraso_pct: number;
    } => 'razon_social' in point,
  );
  if (bars.length) {
    const max = Math.max(...bars.map((point) => point.value), 1);
    return (
      <div className="analysis-bars" aria-label="Gráfico de resultados">
        {bars.map((point) => (
          <div key={point.label}>
            <span>{point.label}</span>
            <div>
              <i style={{ width: `${(100 * point.value) / max}%` }} />
            </div>
            <strong>{point.value.toLocaleString('es-PE')}</strong>
          </div>
        ))}
      </div>
    );
  }
  if (scatter.length) {
    const max = Math.max(...scatter.map((point) => Math.log10(point.ventas_brutas + 1)), 1);
    return (
      <figure className="analysis-scatter">
        <svg
          viewBox="0 0 640 280"
          role="img"
          aria-label="Cada punto representa un vendedor: ventas en escala logarítmica y estrellas promedio"
        >
          <title>Ventas brutas y calificación promedio por vendedor</title>
          <line x1="45" y1="235" x2="620" y2="235" />
          <line x1="45" y1="25" x2="45" y2="235" />
          {[1, 2, 3, 4, 5].map((value) => (
            <text key={value} x="20" y={240 - value * 40}>
              {value}
            </text>
          ))}
          {scatter.map((point) => (
            <circle
              key={point.razon_social}
              cx={45 + (Math.log10(point.ventas_brutas + 1) / max) * 565}
              cy={235 - point.estrellas_promedio * 40}
              r="3.5"
            >
              <title>
                {point.razon_social}: {money(point.ventas_brutas)}, {point.estrellas_promedio}{' '}
                estrellas; {point.retraso_pct}% de retrasos
              </title>
            </circle>
          ))}
          <text x="200" y="270">
            Ventas brutas (escala logarítmica)
          </text>
        </svg>
        <figcaption>
          Pasa por un punto para ver sus datos. Eje vertical: estrellas de 1 a 5.
        </figcaption>
      </figure>
    );
  }
  return null;
}

function ReportView({
  name,
  page,
  onPage,
}: {
  name: string;
  page: number;
  onPage: (page: number) => void;
}) {
  const { data, loading, error, refresh } = useResource<Report>(
    `/analytics/reports/${name}?page=${page}`,
    120000,
  );
  if (loading) return <p role="status">Calculando el análisis con Pandas…</p>;
  if (error)
    return (
      <p className="error-message" role="alert">
        {error}{' '}
        <button className="btn btn-secondary" onClick={refresh}>
          Reintentar
        </button>
      </p>
    );
  if (!data) return null;
  return (
    <>
      <p className="notice">{data.notes}</p>
      {data.criteria && (
        <p>
          {data.total} vendedores cumplen los criterios. Ventas altas desde{' '}
          <strong>{money(data.criteria.ventas_altas_desde)}</strong>.
          {data.criteria.correlacion_estrellas_retrasos !== null && (
            <>
              {' '}
              Correlación entre estrellas y retrasos:{' '}
              <strong>{data.criteria.correlacion_estrellas_retrasos.toFixed(3)}</strong>.
            </>
          )}
        </p>
      )}
      <Chart points={data.chart} />
      <div className="analysis-table-scroll">
        <table>
          <caption>
            {data.total.toLocaleString('es-PE')} resultados · Página {page} de{' '}
            {Math.max(1, data.pages)}
          </caption>
          <thead>
            <tr>
              {data.columns.map((column) => (
                <th scope="col" key={column}>
                  {column.replaceAll('_', ' ')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.items.map((item, index) => (
              <tr key={index}>
                {data.columns.map((column) => (
                  <td key={column}>
                    {item[column] === null
                      ? '—'
                      : typeof item[column] === 'number'
                        ? item[column].toLocaleString('es-PE', { maximumFractionDigits: 4 })
                        : item[column]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.items.length === 0 && <p>No hay resultados con estos criterios.</p>}
      <nav className="catalog-pagination" aria-label="Páginas del análisis">
        <button className="btn btn-secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Anterior
        </button>
        <button
          className="btn btn-secondary"
          disabled={page >= data.pages}
          onClick={() => onPage(page + 1)}
        >
          Siguiente
        </button>
        <a className="btn btn-primary" href={`/api/analytics/exports/${name}.csv`}>
          Descargar CSV completo
        </a>
      </nav>
    </>
  );
}

export default function MarketplaceAnalytics() {
  const [report, setReport] = useState('diagnostico');
  const [page, setPage] = useState(1);
  const summary = useResource<Summary>('/analytics/summary', 120000);
  return (
    <section className="marketplace-analysis">
      <p className="eyebrow">Decisiones a partir de los datos</p>
      <h1>Análisis del marketplace</h1>
      <p>Consultas SQL y análisis con Pandas sobre el histórico del dataset original.</p>
      {summary.data && (
        <>
          <div className="analysis-metrics">
            {Object.entries(summary.data.summary).map(([label, value]) => (
              <div key={label}>
                <strong>{value.toLocaleString('es-PE')}</strong>
                <span>{label.replaceAll('_', ' ')}</span>
              </div>
            ))}
          </div>
          <p className="muted">
            Fecha de referencia RFM: {summary.data.reference_date}. Los resultados se actualizan
            cada 60 segundos.
          </p>
        </>
      )}
      <label htmlFor="analysis-kind">Análisis a consultar</label>
      <select
        id="analysis-kind"
        className="input-field"
        value={report}
        onChange={(event) => {
          setReport(event.target.value);
          setPage(1);
        }}
      >
        {REPORTS.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      <ReportView key={`${report}-${page}`} name={report} page={page} onPage={setPage} />
    </section>
  );
}
