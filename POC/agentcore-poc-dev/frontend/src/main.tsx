import React from 'react'
import ReactDOM from 'react-dom/client'
import '@cloudscape-design/global-styles/index.css'
import App from './App'

/**
 * Top-level error boundary.
 *
 * Catches any unhandled React render errors beneath it and replaces the
 * blank/broken screen with a minimal fallback UI that shows the error
 * message and a reload button. This prevents silent white-screens in
 * production while still surfacing enough detail for debugging.
 *
 * Intentionally kept simple — no external logging SDK — because this fires
 * only for catastrophic failures that escape all component-level handling.
 */
// Add error boundary
class ErrorBoundary extends React.Component<{children: React.ReactNode}, {hasError: boolean, error: any}> {
  constructor(props: {children: React.ReactNode}) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: any) {
    return { hasError: true, error };
  }

  componentDidCatch(error: any, errorInfo: any) {
    console.error('React Error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '20px', fontFamily: 'sans-serif' }}>
          <h1>Something went wrong</h1>
          <pre style={{ background: '#f5f5f5', padding: '10px', overflow: 'auto' }}>
            {this.state.error?.toString()}
          </pre>
          <button onClick={() => window.location.reload()}>Reload</button>
        </div>
      );
    }

    return this.props.children;
  }
}

/**
 * Load runtime config (region, Cognito IDs, API URL) from /config.json BEFORE
 * rendering the app. This guarantees window.__CONFIG__ is populated before
 * AuthProvider reads it, avoiding a race where auth falls back to defaults.
 * config.json is generated per-environment by deploy.sh.
 */
async function loadRuntimeConfig(): Promise<void> {
  try {
    const resp = await fetch('/config.json', { cache: 'no-store' });
    if (resp.ok) {
      (window as any).__CONFIG__ = await resp.json();
    }
  } catch {
    // If config.json is unavailable the app will surface an auth error;
    // better than silently using wrong (hardcoded) values.
  }
}

loadRuntimeConfig().then(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </React.StrictMode>,
  )
})
