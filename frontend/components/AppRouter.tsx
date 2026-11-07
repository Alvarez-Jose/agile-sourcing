import React from 'react';
import { Routes, Route } from 'react-router-dom';
import HomePage from './pages/HomePage';
import SettingsPage from './pages/SettingsPage';
import ChatPage from './pages/ChatPage';
import CartPage from './pages/CartPage';

export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/settings.html" element={<SettingsPage />} />
      <Route path="/chat.html" element={<ChatPage />} />
      <Route path="/cart.html" element={<CartPage />} />
    </Routes>
  );
}
