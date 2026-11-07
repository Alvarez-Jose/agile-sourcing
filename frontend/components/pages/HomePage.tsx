import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Link } from 'react-router-dom';
import Login from './Login';

export function HomePage() {
  const { userProfile, isAuthenticated, isApproved } = useAuth();
  const [loginModalOpen, setLoginModalOpen] = useState(false);

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      {/* Hero Header */}
      <div className="bg-gradient-to-r from-[#00539b] to-[#1f4e8c] text-white p-6 rounded-2xl shadow-md">
        <h1 className="text-2xl font-bold tracking-tight">CruzBuy AI Assistant</h1>
        <p className="text-sm text-blue-100 mt-1 max-w-lg">
          Automated purchasing guidance, vendor discovery, and policy compliance for UCSC procurement.
        </p>
      </div>

      {/* Account & Approval Status Card */}
      <div className="bg-white border border-gray-200 rounded-2xl p-5 shadow-xs">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-800 flex items-center gap-2">
            <span>Account Status</span>
          </h2>
          {isAuthenticated && (
            <span
              className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                isApproved
                  ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                  : 'bg-amber-100 text-amber-800 border border-amber-200'
              }`}
            >
              {isApproved ? '● Active & Approved' : '⏳ Pending Approval'}
            </span>
          )}
        </div>

        {isAuthenticated ? (
          <div className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs bg-slate-50 p-3 rounded-xl border border-slate-200">
              <div>
                <span className="text-gray-500 block">User Email:</span>
                <span className="font-medium text-gray-800">{userProfile?.email}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Account UID:</span>
                <span className="font-mono text-gray-700 truncate block">{userProfile?.uid}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Access Level:</span>
                <span className="font-medium text-gray-800">{userProfile?.role || 'Standard Buyer'}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Status:</span>
                <span className={`font-semibold ${isApproved ? 'text-emerald-700' : 'text-amber-700'}`}>
                  {isApproved ? 'Approved for CruzBuy Chat' : 'Waiting for Admin Review'}
                </span>
              </div>
            </div>

            {!isApproved && (
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800">
                <p className="font-medium">Why is my account pending?</p>
                <p className="mt-0.5 text-amber-700 leading-relaxed">
                  New users are granted access after administrative verification. You can review your profile and approval status in extension settings.
                </p>
              </div>
            )}

            <div className="flex items-center justify-between pt-2">
              <Link
                to="/chat.html"
                className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold text-white transition-all shadow-xs ${
                  isApproved
                    ? 'bg-[#00539b] hover:bg-[#003d6f]'
                    : 'bg-slate-400 hover:bg-slate-500'
                }`}
              >
                <span>Go to Assistant Chat</span>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </Link>

            </div>
          </div>
        ) : (
          <div className="text-center py-4 space-y-3">
            <p className="text-xs text-gray-500">
              You are currently browsing as a guest. Please sign in to verify your CruzBuy permissions.
            </p>
            <button
              onClick={() => setLoginModalOpen(true)}
              className="px-5 py-2.5 bg-[#00539b] hover:bg-[#003d6f] text-white text-xs font-semibold rounded-lg shadow-xs transition-all cursor-pointer"
            >
              Sign in with Google
            </button>
            <Login isOpen={loginModalOpen} onClose={() => setLoginModalOpen(false)} />
          </div>
        )}
      </div>

      {/* Quick Feature Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="p-4 bg-white border border-gray-200 rounded-xl shadow-xs">
          <h3 className="text-xs font-bold text-gray-800 mb-1">Contract Compliance</h3>
          <p className="text-xs text-gray-500">
            Automatically cross-reference CruzBuy items against pre-negotiated university supplier discounts.
          </p>
        </div>
        <div className="p-4 bg-white border border-gray-200 rounded-xl shadow-xs">
          <h3 className="text-xs font-bold text-gray-800 mb-1">Instant Quotes & Sourcing</h3>
          <p className="text-xs text-gray-500">
            Query catalog items, commodity codes, and purchase limits directly from your browser.
          </p>
        </div>
      </div>
    </div>
  );
}

export default HomePage;
