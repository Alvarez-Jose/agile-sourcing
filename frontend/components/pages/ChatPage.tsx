import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import Login from './Login';
import { askQuestion, citationUrl } from '../../services/agent';
import { SessionError } from '../../services/auth';
import { captureCart } from '../../services/cart';
import { attachCart, recentHistory, ChatContext, FollowUp } from '../../services/chat';
import { ChatCartPanel } from '../ChatCartPanel';
import { clearChatDraft, loadChatDraft, saveChatDraft, ChatMessage } from '../../services/chatCache';
import { ChatAnswerText } from '../ChatAnswerText';

export function ChatPage() {
  const { userProfile, isAuthenticated, isApproved, isLoading, refreshSession } = useAuth();
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [cartContext, setCartContext] = useState<ChatContext | null>(null);
  const [followUp, setFollowUp] = useState<FollowUp | null>(null);
  const [isReadingCart, setIsReadingCart] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [cacheNotice, setCacheNotice] = useState<string | null>(null);
  const sessionKey = `${userProfile?.uid ?? ''}:${isAuthenticated}:${isApproved}:${userProfile?.clearance ?? 'none'}`;
  const currentSession = useRef({ key: sessionKey, generation: 0 });
  const restored = useRef<string | null>(null);
  const sending = useRef(false);
  const input = useRef<HTMLInputElement | null>(null);
  if (currentSession.current.key !== sessionKey) {
    currentSession.current = { key: sessionKey, generation: currentSession.current.generation + 1 };
  }

  useEffect(() => {
    restored.current = null;
    setMessages([]);
    setChatError(null);
    setInputMessage('');
    setIsSending(false);
    sending.current = false;
    setCartContext(null);
    setFollowUp(null);
    setIsReadingCart(false);
    setCacheNotice(null);
    setIsRestoring(false);
    if (!isApproved || !userProfile?.uid) return;
    setIsRestoring(true);
    const generation = currentSession.current.generation;
    loadChatDraft(sessionKey).then(draft => {
      if (currentSession.current.key !== sessionKey || currentSession.current.generation !== generation) return;
      if (draft) {
        setMessages(draft.messages);
        setInputMessage(draft.input || (draft.interrupted ? draft.messages.filter(m => m.sender === 'user').at(-1)?.text ?? '' : ''));
        setCartContext(draft.context);
        setFollowUp(draft.followUp);
        setCacheNotice(draft.interrupted
          ? 'Conversation restored. The previous request may have been interrupted; resend it if needed.'
          : 'Conversation restored. I will refresh the cart when it is needed again.');
      }
      restored.current = sessionKey;
      setIsRestoring(false);
    }).catch(() => {
      if (currentSession.current.key !== sessionKey || currentSession.current.generation !== generation) return;
      restored.current = sessionKey;
      setCacheNotice('Conversation caching is unavailable. Keep this chat open to avoid losing messages.');
      setIsRestoring(false);
    });
  }, [sessionKey]);

  useEffect(() => {
    if (!isApproved || isLoading || restored.current !== sessionKey || isRestoring) return;
    const generation = currentSession.current.generation;
    void saveChatDraft(sessionKey, {messages, input: inputMessage, context: cartContext, followUp, interrupted: isSending}).catch(() => {
      if (currentSession.current.generation === generation) setCacheNotice('Recent messages could not be cached. Keep this chat open to avoid losing them.');
    });
  }, [sessionKey, messages, inputMessage, cartContext, followUp, isSending, isRestoring, isLoading]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || !isApproved || sending.current || isSending || isLoading || isReadingCart || isRestoring) return;
    sending.current = true;

    const userText = text.trim();
    setMessages((prev) => [...prev, { sender: 'user', text: userText }]);
    setInputMessage('');

    setChatError(null);
    setIsSending(true);
    const requestSession = currentSession.current.generation;
    try {
      let result = await askQuestion(userText, cartContext, recentHistory(messages));
      if (currentSession.current.generation !== requestSession) return;
      if (result.tool_request) {
        // The server can request only this allowlisted, read-only browser tool.
        if (result.tool_request.name !== 'read_cart') throw new Error('Unsupported assistant tool.');
        setIsReadingCart(true);
        setCartContext(null);
        setFollowUp(null);
        const snapshot = await captureCart();
        if (currentSession.current.generation !== requestSession) return;
        const next = attachCart(snapshot, result.chat_context ?? cartContext);
        setCartContext(next);
        result = await askQuestion(result.tool_request.question, next, recentHistory(messages));
        if (result.tool_request) throw new Error('Could not finish reading the cart. Open the CruzBuy Simple Cart and retry.');
      }
      if (currentSession.current.generation !== requestSession) return;
      const previous = messages.slice().reverse().find(message => message.sender === 'bot');
      setMessages((prev) => [...prev, {sender: 'bot', text: result.summary ?? result.answer,
        detailText: result.summary ? result.answer : result.original_answer ?? undefined,
        formLinks: result.form_links ?? [],
        sources: result.inherit_sources ? previous?.sources ?? [] : result.sources}]);
      if (result.chat_context) setCartContext(result.chat_context);
      setFollowUp(result.follow_up ?? null);
    } catch (error) {
      if (currentSession.current.generation !== requestSession) return;
      setChatError(error instanceof Error ? error.message : 'Could not send your message.');
      if (error instanceof SessionError && (error.status === 401 || error.status === 403)) {
        await refreshSession();
      }
    } finally {
      if (currentSession.current.generation === requestSession) {sending.current = false; setIsSending(false); setIsReadingCart(false);}
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    await sendMessage(inputMessage);
  };

  const updateCart = (next: ChatContext | null) => {
    const confirmationOnly = next && cartContext &&
      JSON.stringify({...next, cart: {...next.cart, reviewed: false}}) ===
      JSON.stringify({...cartContext, cart: {...cartContext.cart, reviewed: false}});
    currentSession.current.generation++;
    setCartContext(next ? {...next, pending_question: next.pending_question ?? next.last_question} : null);
    if (!confirmationOnly) {
      setMessages([]);
      setFollowUp(null);
    }
    setChatError(null);
    setIsSending(false);
    sending.current = false;
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
                Once approved, you will be able to ask about purchasing policies, required forms, and documentation.
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
          {isRestoring && <p role="status" className="mb-2 text-xs text-blue-800">Restoring your conversation…</p>}
          {isReadingCart && <p role="status" className="mb-2 text-xs text-blue-800">Reading your current CruzBuy cart…</p>}
          {cacheNotice && <p role="status" className="mb-2 text-xs text-slate-600">{cacheNotice}</p>}
          <button type="button" disabled={isRestoring || isSending || isReadingCart} onClick={() => {updateCart(null); setInputMessage(''); setCacheNotice(null); void clearChatDraft().catch(() => setCacheNotice('Could not clear the cached conversation.'));}} className="mb-2 text-right text-xs text-blue-800 underline">Clear conversation</button>
          {!cartContext && <div className="mb-3 text-xs">
            <button type="button" onClick={() => sendMessage('Summarize my cart')} disabled={isReadingCart || isSending || isLoading || isRestoring} className="rounded bg-blue-50 px-3 py-2 font-semibold text-[#00539b] disabled:opacity-50">{isReadingCart ? 'Reading cart…' : 'Use my CruzBuy cart'}</button>
            <p className="mt-1 text-slate-500">Ask about your cart and I will read it automatically. Keep the CruzBuy Simple Cart active while using the extension popup.</p>
          </div>}
          {cartContext && <ChatCartPanel context={cartContext} disabled={isSending || isReadingCart || isLoading || isRestoring} onRefresh={() => sendMessage('Refresh my cart')} onClear={() => updateCart(null)}/>}
          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto space-y-3 mb-4 pr-1">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-400 text-center py-12">
                <svg className="w-8 h-8 mb-2 text-blue-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
                <p className="text-sm font-medium text-gray-600">How can I help you today?</p>
                <p className="text-xs text-gray-400 mt-1 max-w-xs">
                  Ask questions about purchasing policies, required forms, and supporting documentation.
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
                    <p className="whitespace-pre-wrap">{m.sender === 'bot' ? <ChatAnswerText text={m.text} links={m.formLinks}/> : m.text}</p>
                    {m.detailText && m.detailText !== m.text && <details className="mt-2 border-t border-gray-200 pt-2">
                      <summary className="cursor-pointer text-xs text-[#00539b]">Full answer and conditions</summary>
                      <div className="mt-2"><ChatAnswerText text={m.detailText} links={m.formLinks}/></div>
                    </details>}
                    {m.sender === 'bot' && i === messages.length - 1 && !!followUp?.choices.length && (
                      <div role="group" aria-label="Choose a reply" className="mt-3 flex flex-col gap-2">
                        {followUp.choices.map(choice => <button
                          type="button" key={choice.value}
                          disabled={isSending || isLoading || isReadingCart || isRestoring}
                          onClick={() => {setInputMessage(choice.value); input.current?.focus();}}
                          aria-pressed={inputMessage === choice.value}
                          className={`rounded-xl border px-3 py-2 text-left text-xs font-medium text-[#00539b] hover:bg-blue-50 focus-visible:outline-2 focus-visible:outline-blue-700 disabled:cursor-not-allowed disabled:opacity-50 ${inputMessage === choice.value ? 'border-blue-500 bg-blue-50' : 'border-blue-200 bg-white'}`}
                        >{choice.label}</button>)}
                        <span className="text-[11px] text-slate-500">Choose an option to fill your reply, then press Send. You can edit it or type your own answer.</span>
                      </div>
                    )}
                    {!!m.sources?.length && (
                      <ul className="mt-2 border-t border-gray-200 pt-2 text-xs">
                        {m.sources.map((source) => {
                          const url = citationUrl(source);
                          return (
                            <li key={source.citation_id} className="mb-2">
                              [{source.citation_id}] {url ? (
                                <a href={url} target="_blank" rel="noopener noreferrer" className="text-[#00539b] underline">{source.policy}</a>
                              ) : source.policy}
                              {source.section && <span> — {source.section}</span>}
                              {source.page && <span>, p. {source.page}</span>}
                              {!!source.evidence?.length && (
                                <details className="mt-1">
                                  <summary className="cursor-pointer text-slate-600">Supporting text</summary>
                                  {source.evidence.map((evidence, index) => (
                                    <blockquote key={index} className="mt-1 border-l-2 border-gray-300 pl-2 whitespace-pre-wrap">{evidence.quote}</blockquote>
                                  ))}
                                </details>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Active Input Bar */}
          {chatError && <p role="alert" className="mb-2 text-xs text-red-700">{chatError}</p>}
          <form onSubmit={handleSendMessage} className="mt-auto flex gap-2">
            <input
              ref={input}
              type="text"
              inputMode={followUp?.kind === 'charges' ? 'decimal' : 'text'}
              value={inputMessage}
              disabled={isSending || isLoading || isReadingCart || isRestoring}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder={followUp?.kind === 'charges' ? 'Type the estimated amount in USD, e.g. 5.00' : followUp?.choices.length ? 'Choose an option above or type your answer...' : 'Ask about purchasing policies or required forms...'}
              className="flex-1 p-2.5 border border-gray-300 rounded-lg text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-[#00539b] focus:border-transparent transition-all"
            />
            <button
              type="submit"
              disabled={!inputMessage.trim() || isSending || isLoading || isReadingCart || isRestoring}
              className="px-4 py-2 bg-[#00539b] hover:bg-[#003d6f] active:scale-95 text-white rounded-lg text-xs sm:text-sm font-medium transition-all disabled:opacity-50 cursor-pointer shadow-xs"
            >
              {isSending ? 'Thinking…' : 'Send'}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

export default ChatPage;
