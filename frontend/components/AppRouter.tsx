import React from 'react';
import { HashRouter, Routes, Route } from 'react-router-dom';
import SettingsPage from '../entrypoints/home/components/SettingsPage';
import ChatPage from '../entrypoints/home/components/ChatPage';

// Simple Home Component to be used in both entrypoints
function HomePage() {
  return (
    <div className="text-center">
      <h1 className="text-2xl font-bold mb-4">CruzBuy Assistant Home Page</h1>
      <p className="text-slate-600">Welcome to your dashboard.</p>
    </div>
  );
}

export function AppRouter() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/settings.html" element={<SettingsPage />} />
        <Route path="/chat.html" element={<ChatPage />} />
      </Routes>
    </HashRouter>
  );
}
