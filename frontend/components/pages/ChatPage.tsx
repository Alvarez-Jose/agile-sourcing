import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import Login from './Login';

export function ChatPage() {
  const { userProfile, isAuthenticated, isApproved, isLoading, refreshSession, toggleMockApproval } = useAuth();
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [messages, setMessages] = useState<Array<{ sender: 'user' | 'bot'; text: string }>>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || !isApproved) return;

    const userText = inputMessage.trim();
    setMessages((prev) => [...prev, { sender: 'user', text: userText }]);
    setInputMessage('');

    // Simulated CruzBuy Assistant response
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          sender: 'bot',
          text: `CruzBuy Assistant received: "${userText}". (RAG backend pipeline integration pending)`,
        },
      ]);
    }, 600);
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await refreshSession();
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-gray-200">
        <div>
          <h1 className="text-xl font-bold text-gray-800 flex items-center gap-2">
            <span>CruzBuy Assistant</span>
            {isAuthenticated && (
              <span
                className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                  isApproved
                    ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                    : 'bg-amber-100 text-amber-800 border border-amber-200'
                }`}
              >
                {isApproved ? '● Approved' : '⏳ Pending Approval'}
              </span>
            )}
          </h1>
          <p className="text-xs text-slate-500">
            Intelligent procurement & sourcing assistance
          </p>
        </div>

        {/* Development State Switcher */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => toggleMockApproval()}
            className="text-[11px] px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-600 border border-slate-300 transition-colors cursor-pointer"
            title="Toggle between Approved and Pending Approval states for testing"
          >
            🧪 Dev Toggle: {isApproved ? 'Simulate Pending' : 'Simulate Approved'}
          </button>
        </div>
      </div>

      {/* State 1: Not Authenticated */}
      {!isAuthenticated && (
        <div className="flex-1 flex flex-col items-center justify-center p-8 bg-white border border-gray-200 rounded-xl shadow-xs text-center">
          <div className="w-12 h-12 rounded-full bg-blue-50 flex items-center justify-center text-[#00539b] mb-4">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-gray-800 mb-1">Sign In Required</h2>
          <p className="text-sm text-gray-500 max-w-sm mb-6">
            Please log in with your CruzBuy or UCSC account to access the sourcing assistant.
          </p>
          <button
            onClick={() => setLoginModalOpen(true)}
            className="px-5 py-2.5 rounded-lg bg-[#00539b] text-white text-sm font-medium hover:bg-[#003d6f] transition-all cursor-pointer shadow-xs active:scale-95"
          >
            Sign In to Continue
          </button>
          <Login isOpen={loginModalOpen} onClose={() => setLoginModalOpen(false)} />
        </div>
      )}

      {/* State 2: Authenticated but Pending Approval */}
      {isAuthenticated && !isApproved && (
        <div className="flex flex-col flex-1 gap-3">
          {/* Pending Approval Notice Banner */}
          <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3 shadow-xs">
            <div className="p-2 bg-amber-100 text-amber-700 rounded-lg shrink-0 mt-0.5">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-amber-900">
                Account Pending Approval
              </h3>
              <p className="text-xs text-amber-700 mt-1 leading-relaxed">
                Welcome, <span className="font-semibold">{userProfile?.email}</span>. Your account is currently awaiting administrative approval before CruzBuy assistant chat features can be accessed.
              </p>
              <div className="mt-3 flex items-center gap-3">
                <button
                  onClick={handleRefresh}
                  disabled={isRefreshing}
                  className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-md text-xs font-medium transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                >
                  {isRefreshing ? (
                    <>
                      <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Checking Status...
                    </>
                  ) : (
                    <>
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      Refresh Approval Status
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Greyed-out Chat Box Container */}
          <div className="flex-1 flex flex-col border border-gray-200 rounded-xl bg-gray-50/80 p-4 relative opacity-75 select-none min-h-[260px]">
            <div className="flex-1 flex flex-col items-center justify-center text-center text-gray-400 p-6">
              <svg className="w-10 h-10 mb-2 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
              <p className="text-sm font-medium text-gray-500">Chat is locked</p>
              <p className="text-xs text-gray-400 max-w-xs mt-1">
                Once approved, you will be able to search contracts, query quotes, and interact with the AI assistant.
              </p>
            </div>

            {/* Disabled Input Bar */}
            <div className="mt-auto flex gap-2">
              <input
                type="text"
                disabled
                placeholder="Chat disabled until account approval..."
                className="flex-1 p-2.5 bg-gray-100 border border-gray-300 rounded-lg text-xs text-gray-400 cursor-not-allowed italic"
              />
              <button
                disabled
                className="px-4 py-2 bg-gray-300 text-gray-500 rounded-lg text-xs font-medium cursor-not-allowed"
              >
                Send
              </button>
            </div>
          </div>
        </div>
      )}

      {/* State 3: Authenticated and Approved */}
      {isAuthenticated && isApproved && (
        <div className="flex-1 flex flex-col border border-gray-200 rounded-xl bg-white shadow-xs p-4 min-h-[300px]">
          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto space-y-3 mb-4 pr-1">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-400 text-center py-12">
                <svg className="w-8 h-8 mb-2 text-blue-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
                <p className="text-sm font-medium text-gray-600">How can I help you today?</p>
                <p className="text-xs text-gray-400 mt-1 max-w-xs">
                  Ask questions about purchasing guidelines, approved vendors, or item specifications.
                </p>
              </div>
            ) : (
              messages.map((m, i) => (
                <div
                  key={i}
                  className={`flex ${m.sender === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[80%] rounded-xl px-3.5 py-2.5 text-xs sm:text-sm leading-relaxed ${
                      m.sender === 'user'
                        ? 'bg-[#00539b] text-white rounded-br-none shadow-xs'
                        : 'bg-gray-100 text-gray-800 rounded-bl-none'
                    }`}
                  >
                    {m.text}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Active Input Bar */}
          <form onSubmit={handleSendMessage} className="mt-auto flex gap-2">
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder="Ask CruzBuy Assistant about suppliers, contracts, orders..."
              className="flex-1 p-2.5 border border-gray-300 rounded-lg text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-[#00539b] focus:border-transparent transition-all"
            />
            <button
              type="submit"
              disabled={!inputMessage.trim()}
              className="px-4 py-2 bg-[#00539b] hover:bg-[#003d6f] active:scale-95 text-white rounded-lg text-xs sm:text-sm font-medium transition-all disabled:opacity-50 cursor-pointer shadow-xs"
            >
              Send
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

export default ChatPage;
