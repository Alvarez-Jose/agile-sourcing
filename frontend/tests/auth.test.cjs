// Run the actual service code with fake browser/Firebase/network boundaries.
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const source = readFileSync(join(__dirname, '../services/auth.ts'), 'utf8')
  .replaceAll('import.meta.env', '__testEnv');
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function fixture() {
  const state = { stored: [], removed: [], requests: [], forceRefresh: [], ready: 0 };
  const profile = { uid: 'verified-user', email: 'buyer@ucsc.edu', name: 'Buyer',
    department: 'Chemistry', clearance: 'department_buyer', is_approved: false };
  const firebase = {
    currentUser: { uid: profile.uid, getIdToken: async (force) => {
      state.forceRefresh.push(force);
      return 'fresh-firebase-token';
    } },
    authStateReady: async () => { state.ready++; },
  };
  const browser = {
    identity: {
      getRedirectURL: () => 'https://test-extension.chromiumapp.org/',
      launchWebAuthFlow: async () => 'https://test-extension.chromiumapp.org/#id_token=google-token',
    },
    storage: { local: {
      set: async (data) => state.stored.push(JSON.parse(JSON.stringify(data))),
      remove: async (keys) => state.removed.push(Array.from(keys)),
    } },
  };
  const sdk = {
    GoogleAuthProvider: { credential: (token) => { state.googleToken = token; return 'credential'; } },
    signInWithCredential: async () => ({ user: firebase.currentUser }),
    signOut: async () => { firebase.currentUser = null; },
  };
  const network = { fetch: async () => new Response(JSON.stringify(profile), { status: 200 }) };
  const module = { exports: {} };
  const context = {
    module, exports: module.exports,
    URL, URLSearchParams, AbortSignal, crypto: globalThis.crypto,
    __testEnv: { VITE_GOOGLE_CLIENT_ID: 'test-client', VITE_API_BASE_URL: 'http://localhost:8000' },
    fetch: async (...args) => { state.requests.push(args); return network.fetch(...args); },
    require: (name) => {
      if (name === 'firebase/auth') return sdk;
      if (name === '../firebase/firebaseConfig') return { auth: firebase };
      if (name === 'wxt/browser') return { browser };
      throw new Error(`Unexpected import: ${name}`);
    },
  };
  vm.runInNewContext(code, context);
  return { api: module.exports, state, profile, firebase, browser, sdk, network };
}

test('Google sign-in exchanges the token and persists only the verified backend profile', async () => {
  const f = fixture();
  const result = await f.api.signInWithGoogle();
  assert.equal(f.state.googleToken, 'google-token');
  assert.equal(result.profile.department, 'Chemistry');
  assert.equal(result.profile.clearance, 'department_buyer');
  assert.deepEqual(f.state.stored, [{ idToken: 'fresh-firebase-token', userProfile: f.profile }]);
  assert.equal(f.state.requests[0][0], 'http://localhost:8000/auth/session');
  assert.equal(f.state.requests[0][1].headers.Authorization, 'Bearer fresh-firebase-token');
});

for (const status of [401, 403, 503]) {
  test(`HTTP ${status} cannot produce a local mock session`, async () => {
    const f = fixture();
    f.network.fetch = async () => new Response(JSON.stringify({ detail: 'Server rejected session' }), { status });
    await assert.rejects(f.api.signInWithGoogle(), (error) =>
      error.status === status && error.message === 'Server rejected session');
    assert.deepEqual(f.state.stored, []);
  });
}

test('network failures report a retryable error without storing a profile', async () => {
  const f = fixture();
  f.network.fetch = async () => { throw new Error('Connection refused'); };
  await assert.rejects(f.api.establishSession('token'), /Cannot reach the sign-in server/);
  assert.deepEqual(f.state.stored, []);
});

test('a response for a different user cannot establish a session', async () => {
  const f = fixture();
  f.network.fetch = async () => new Response(JSON.stringify({ ...f.profile, uid: 'someone-else' }));
  await assert.rejects(f.api.establishSession('token'), /invalid user profile/);
  assert.deepEqual(f.state.stored, []);
});

test('non-boolean approval is rejected', async () => {
  const f = fixture();
  f.network.fetch = async () => new Response(JSON.stringify({ ...f.profile, is_approved: 'true' }));
  await assert.rejects(f.api.establishSession('token'), /invalid user profile/);
  assert.deepEqual(f.state.stored, []);
});

test('sign-out during an in-flight session request cannot restore the profile', async () => {
  const f = fixture();
  f.network.fetch = async () => {
    f.firebase.currentUser = null;
    return new Response(JSON.stringify(f.profile));
  };
  await assert.rejects(f.api.establishSession('token'), /invalid user profile/);
  assert.deepEqual(f.state.stored, []);
});

test('token refresh waits for restored Firebase identity and requests a fresh token', async () => {
  const f = fixture();
  assert.equal(await f.api.getFreshIdToken(true), 'fresh-firebase-token');
  assert.equal(f.state.ready, 1);
  assert.deepEqual(f.state.forceRefresh, [true]);
});

test('no restored identity means authenticated requests must sign in again', async () => {
  const f = fixture();
  f.firebase.currentUser = null;
  await assert.rejects(f.api.getFreshIdToken(), /Please sign in/);
});

test('extension storage is cleared even when Firebase sign-out fails', async () => {
  const f = fixture();
  f.sdk.signOut = async () => { throw new Error('Sign-out failed'); };
  await assert.rejects(f.api.signOutUser(), /Sign-out failed/);
  assert.deepEqual(f.state.removed, [['idToken', 'userProfile']]);
});
