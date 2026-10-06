import { useState } from 'react';
import { Sidebar } from '../../components/Sidebar';
import { AppRouter } from '../../components/AppRouter';
import { AuthProvider } from '../../context/AuthContext';

function AppContent() {
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <div className="flex min-h-screen bg-[#f8f4fb] text-slate-800 font-sans">
      <Sidebar isCollapsed={isCollapsed} setIsCollapsed={setIsCollapsed} />
      <main className="flex-1 p-8">
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