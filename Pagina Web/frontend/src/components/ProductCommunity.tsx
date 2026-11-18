import { useState } from 'react';
import api, { errorMessage } from '../api';
import type { User } from '../types';

interface Question {
  id_pregunta: number;
  texto: string;
  respuesta: string | null;
}
export default function ProductCommunity({
  id,
  user,
  owner,
  favorite,
  canReview,
  reviewed,
  questions,
  onLogin,
  onUpdated,
}: {
  id: number;
  user: User | null;
  owner: string | null;
  favorite: boolean;
  canReview: boolean;
  reviewed: boolean;
  questions: Question[];
  onLogin: () => void;
  onUpdated: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [question, setQuestion] = useState('');
  const [review, setReview] = useState('');
  const [stars, setStars] = useState(5);
  const [answer, setAnswer] = useState('');
  const [questionId, setQuestionId] = useState<number | null>(null);
  const unanswered = questions.filter((item) => !item.respuesta);
  const selected = unanswered.find((item) => item.id_pregunta === questionId) ?? unanswered[0];
  async function submit(action: 'favorite' | 'question' | 'review' | 'answer') {
    if (!user) {
      onLogin();
      return;
    }
    if (busy) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      if (action === 'favorite')
        await api.put(`/marketplace/products/${id}/favorite`, { enabled: !favorite });
      if (action === 'question') {
        await api.post(`/marketplace/products/${id}/questions`, { texto: question });
        setQuestion('');
      }
      if (action === 'review') {
        await api.post(`/marketplace/products/${id}/reviews`, {
          estrellas: stars,
          comentario: review,
        });
        setReview('');
      }
      if (action === 'answer' && selected) {
        await api.put(`/marketplace/questions/${selected.id_pregunta}/answer`, { texto: answer });
        setAnswer('');
        setQuestionId(null);
      }
      setNotice(
        {
          favorite: favorite ? 'Producto quitado de favoritos.' : 'Producto guardado en favoritos.',
          question: 'Pregunta publicada.',
          review: 'Reseña publicada.',
          answer: 'Respuesta publicada.',
        }[action],
      );
      onUpdated();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="product-community" aria-label="Participar en este producto">
      <h3>Tu opinión cuenta</h3>
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      <button
        className="btn btn-secondary"
        disabled={busy}
        aria-pressed={favorite}
        onClick={() => void submit('favorite')}
      >
        {favorite ? 'Quitar de favoritos' : 'Guardar en favoritos'}
      </button>
      {user ? (
        <>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void submit('question');
            }}
          >
            <label htmlFor="product-question">Haz una pregunta al vendedor</label>
            <textarea
              id="product-question"
              className="input-field"
              minLength={3}
              maxLength={2000}
              required
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              disabled={busy}
            />
            <button className="btn btn-secondary" disabled={busy} type="submit">
              Publicar pregunta
            </button>
          </form>
          {owner === user.id && selected && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void submit('answer');
              }}
            >
              <label htmlFor="product-unanswered">Pregunta por responder</label>
              <select
                id="product-unanswered"
                className="input-field"
                value={selected.id_pregunta}
                onChange={(event) => setQuestionId(Number(event.target.value))}
                disabled={busy}
              >
                {unanswered.map((item) => (
                  <option key={item.id_pregunta} value={item.id_pregunta}>
                    {item.texto}
                  </option>
                ))}
              </select>
              <label htmlFor="product-answer">Tu respuesta</label>
              <textarea
                id="product-answer"
                className="input-field"
                minLength={3}
                maxLength={2000}
                required
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                disabled={busy}
              />
              <button className="btn btn-secondary" type="submit" disabled={busy}>
                Publicar respuesta
              </button>
            </form>
          )}
          {canReview ? (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void submit('review');
              }}
            >
              <h3>Dejar una reseña</h3>
              <label htmlFor="product-stars">Calificación</label>
              <select
                id="product-stars"
                className="input-field"
                value={stars}
                onChange={(event) => setStars(Number(event.target.value))}
                disabled={busy}
              >
                {[5, 4, 3, 2, 1].map((value) => (
                  <option key={value} value={value}>
                    {value} de 5
                  </option>
                ))}
              </select>
              <label htmlFor="product-review">Cuéntanos tu experiencia</label>
              <textarea
                id="product-review"
                className="input-field"
                minLength={3}
                maxLength={2000}
                required
                value={review}
                onChange={(event) => setReview(event.target.value)}
                disabled={busy}
              />
              <button className="btn btn-primary" disabled={busy} type="submit">
                Publicar reseña
              </button>
            </form>
          ) : (
            <p className="muted">
              {reviewed
                ? 'Ya dejaste tu reseña para este producto.'
                : 'Podrás reseñar este producto después de recibirlo.'}
            </p>
          )}
        </>
      ) : (
        <p>
          <button className="btn btn-ghost" onClick={onLogin}>
            Ingresa para preguntar o dejar una reseña
          </button>
        </p>
      )}
    </section>
  );
}
