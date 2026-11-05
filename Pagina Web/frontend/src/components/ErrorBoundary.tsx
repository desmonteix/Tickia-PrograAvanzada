import { Component } from 'react';
import type { ReactNode } from 'react';

export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed)
      return (
        <main className="container main-content">
          <h1>No pudimos mostrar esta página</h1>
          <p role="alert">
            Ocurrió un error inesperado. Recarga la página para volver a intentarlo.
          </p>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>
            Recargar página
          </button>
        </main>
      );
    return this.props.children;
  }
}
