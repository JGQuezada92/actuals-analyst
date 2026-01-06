import { Outlet } from 'react-router-dom';
import { Sidebar } from './sidebar';
import { Header } from './header';

export function AppLayout() {
  return (
    <div className="flex h-screen overflow-hidden" style={{ backgroundColor: '#f9fafb', minHeight: '100vh' }}>
      <style>{`
        /* Test CSS - if you see red background, CSS is working */
        body { background-color: #fee2e2 !important; }
        /* If Tailwind works, you'll see styled sidebar */
      `}</style>
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

