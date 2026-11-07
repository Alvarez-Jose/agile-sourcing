import { useState } from 'react';
import { Sidebar } from '../../components/Sidebar';
import { AppRouter } from '../../components/AppRouter';
import { AuthProvider } from '../../context/AuthContext';
import { SessionNotice } from '../../components/SessionNotice';

function AppContent() {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const handleOpenNewTab = () => {
    browser.tabs.create({ 
      url: browser.runtime.getURL('/home.html') 
    });
  };

  return (
    <div className="flex h-[600px] w-[500px] overflow-hidden bg-[#f8f4fb] text-slate-800 font-sans">
      <Sidebar isCollapsed={isCollapsed} setIsCollapsed={setIsCollapsed} onOpenNewTab={handleOpenNewTab} />
      <main className="flex-1 p-4 overflow-y-auto">
        <SessionNotice />
        <AppRouter />
      </main>
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;
