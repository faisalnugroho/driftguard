import React from 'react';
import { AppProvider, useApp } from './lib/store';
import { TopBar, WalletBar, BusyOverlay, Toast, About, Footer } from './components/shell';
import Dashboard from './pages/Dashboard';
import CreateWatch from './pages/CreateWatch';
import WatchDetail from './pages/WatchDetail';

function Router() {
  const app = useApp();
  switch (app.route.page) {
    case 'dashboard':
      return <Dashboard />;
    case 'create':
      return <CreateWatch />;
    case 'watch':
      return <WatchDetail id={app.route.id} />;
    default:
      return <Dashboard />;
  }
}

export default function App() {
  return (
    <AppProvider>
      <TopBar />
      <WalletBar />
      <main>
        <Router />
        <About />
      </main>
      <Footer />
      <BusyOverlay />
      <Toast />
    </AppProvider>
  );
}
