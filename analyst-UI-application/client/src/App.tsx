import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from '@/components/theme-provider';
import { AppLayout } from '@/components/layout/app-layout';
import { ChatPage } from '@/pages/chat';
import { TracesPage } from '@/pages/traces';
import { AdminPage } from '@/pages/admin';
import { SettingsPage } from '@/pages/settings';

function App() {
  return (
    <ThemeProvider defaultTheme="system" storageKey="financial-analyst-theme">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            <Route index element={<ChatPage />} />
            <Route path="traces" element={<TracesPage />} />
            <Route path="admin" element={<AdminPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;

