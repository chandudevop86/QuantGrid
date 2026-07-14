import { Component, StrictMode, type ErrorInfo, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import App from "./App";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

type AppErrorBoundaryProps = {
  children: ReactNode;
};

type AppErrorBoundaryState = {
  error: Error | null;
};

class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("QuantGrid failed to render", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="fatal-screen" role="alert">
          <section className="fatal-card">
            <span className="brand-mark">QG</span>
            <div>
              <p className="eyebrow">Dashboard startup failed</p>
              <h1>QuantGrid could not finish loading.</h1>
              <p>
                Refresh the page. If this repeats, open the browser console and send the
                error shown there.
              </p>
              <pre>{this.state.error.message}</pre>
              <button type="button" onClick={() => window.location.reload()}>
                Reload dashboard
              </button>
            </div>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}><App /></QueryClientProvider>
    </AppErrorBoundary>
  </StrictMode>
);
