import React from 'react';

export function ChatPage() {
  return (
    <div className="text-left">
      <h1 className="text-2xl font-bold mb-4">Chat</h1>
      <div className="flex flex-col h-[60vh] border border-gray-200 rounded-lg bg-white shadow-sm p-4">
        <div className="flex-1 overflow-y-auto mb-4 text-slate-500 italic">
          No messages yet. Start a conversation!
        </div>
        <div className="mt-auto flex gap-2">
          <input 
            type="text" 
            placeholder="Type your message..." 
            className="flex-1 p-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#00539b]"
          />
          <button className="px-4 py-2 bg-[#00539b] text-white rounded-md hover:bg-[#003d6f]">
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

export default ChatPage;
