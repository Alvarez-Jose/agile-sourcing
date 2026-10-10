import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import Login from './Login';

export function SettingsPage() {
  const {
    userProfile,
    idToken,
    isAuthenticated,
    isApproved,
    isLoading,
    refreshSession,
    logout,
  } = useAuth();

  const [loginOpen, setLoginOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const handleCopyToken = () => {
    if (idToken) {
      navigator.clipboard.writeText(idToken);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await refreshSession();
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      {/* Page Title */}
      <div className="pb-2 border-b border-gray-200">
        <h1 className="text-xl font-bold text-gray-800">Extension Settings</h1>
        <p className="text-xs text-slate-500">
          Manage your CruzBuy assistant preferences and session details.
        </p>
      </div>

      {/* Profile & Auth Section */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-xs space-y-3">
        <h2 className="text-sm font-bold text-gray-800 flex items-center justify-between">
          <span>Authentication Profile</span>
          {isAuthenticated && (
            <span
              className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                isApproved
                  ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                  : 'bg-amber-100 text-amber-800 border border-amber-200'
              }`}
            >
              {isApproved ? 'Approved' : 'Pending Approval'}
            </span>
          )}
        </h2>

        {isAuthenticated ? (
          <div className="space-y-3 text-xs">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 bg-slate-50 p-3 rounded-lg border border-slate-200">
              <div>
                <span className="text-gray-500 block">Name:</span>
                <span className="font-medium text-gray-800">{userProfile?.name || 'Not set'}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Department:</span>
                <span className="font-medium text-gray-800">{userProfile?.department || 'Not assigned'}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Clearance:</span>
                <span className="font-medium text-gray-800">{userProfile?.clearance || 'none'}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Email:</span>
                <span className="font-medium text-gray-800">{userProfile?.email}</span>
              </div>
              <div>
                <span className="text-gray-500 block">UID:</span>
                <span className="font-mono text-gray-700 truncate block">{userProfile?.uid}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Approval Flag:</span>
                <span className={`font-semibold ${isApproved ? 'text-emerald-600' : 'text-amber-600'}`}>
                  is_approved = {String(userProfile?.is_approved)}
                </span>
              </div>
              <div>
                <span className="text-gray-500 block">Role:</span>
                <span className="text-gray-800">{userProfile?.role || 'buyer'}</span>
              </div>
            </div>

            {/* Token details */}
            <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
              <div className="flex items-center justify-between mb-1">
                <span className="text-gray-500 font-medium">Stored ID Token (JWT):</span>
                {idToken && (
                  <button
                    onClick={handleCopyToken}
                    className="text-[11px] text-[#00539b] hover:underline cursor-pointer"
                  >
                    {copied ? '✓ Copied!' : 'Copy Token'}
                  </button>
                )}
              </div>
              <p className="font-mono text-[11px] text-gray-600 truncate bg-white p-1.5 rounded border border-gray-200">
                {idToken ? `${idToken.substring(0, 32)}...${idToken.substring(idToken.length - 16)}` : 'No token stored'}
              </p>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 pt-1">
              <button
                onClick={handleRefresh}
                disabled={refreshing || isLoading}
                className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-md text-xs font-medium transition-colors cursor-pointer disabled:opacity-50"
              >
                {refreshing ? 'Syncing...' : 'Sync Session with Backend'}
              </button>
              <button
                onClick={() => logout()}
                className="px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-600 rounded-md text-xs font-medium transition-colors cursor-pointer"
              >
                Sign Out
              </button>
            </div>
          </div>
        ) : (
          <div className="py-2 text-center space-y-2">
            <p className="text-xs text-gray-500">Not currently signed in.</p>
            <button
              onClick={() => setLoginOpen(true)}
              className="px-4 py-2 bg-[#00539b] hover:bg-[#003d6f] text-white text-xs font-medium rounded-lg shadow-xs cursor-pointer"
            >
              Sign In
            </button>
            <Login isOpen={loginOpen} onClose={() => setLoginOpen(false)} />
          </div>
        )}
      </div>

    </div>
  );
}

export default SettingsPage;
