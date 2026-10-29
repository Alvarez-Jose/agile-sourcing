# Firebase authentication with FastAPI

The extension signs in with Google and exchanges the Google token for a **Firebase ID
token**. FastAPI verifies that token with Firebase Admin (including revocation and
disabled-account checks), then reads `users/{uid}` from Firestore.

## Configure the backend

Enable Google sign-in in the Firebase Authentication project and create a Firestore
database in the same project. In Firebase Console → Project settings → Service
accounts, obtain credentials for a backend service account that can access Firebase
Authentication and the user collection. Put the JSON file outside the frontend, for
example in the ignored `secret/` directory.

Apply the included [`firestore.rules`](../firestore.rules) in Firebase Console →
Firestore Database → Rules for this profile-only database. These rules deny direct
client access; the server Admin SDK continues to work through IAM. If the project
already has other collections, merge the `users` rule into its existing rules and
ensure no broader matching rule grants clients write access to user profiles.

Backend and frontend share **`secret/.env`**. Create `secret/` and use the local
`secret/.env.example` if available, or start with this template:

```dotenv
FIREBASE_PROJECT_ID=agile-sourcing
GOOGLE_APPLICATION_CREDENTIALS=agile-sourcing-firebase-adminsdk-fbsvc-9ba8071ec8.json
VITE_API_BASE_URL=http://localhost:8000
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=agile-sourcing.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=agile-sourcing
VITE_FIREBASE_STORAGE_BUCKET=
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_APP_ID=
VITE_GOOGLE_CLIENT_ID=
```

Place the JSON file named in `GOOGLE_APPLICATION_CREDENTIALS` inside `secret/`.
Relative credential paths are resolved from `secret/`, and absolute paths are also
supported. Both application environment variables and external server settings work;
settings already exported in the server environment take precedence over `.env`.
The entire directory, including the environment files and JSON, is ignored by Git.
Give each teammate the required configuration separately from the repository.

Existing Google Application Default Credentials can also be used; in a hosted Google
environment use the server's service identity. When using existing ADC, leave
`GOOGLE_APPLICATION_CREDENTIALS` unset rather than pointing it at an empty path.
Admin credentials belong only on the server. The frontend's Firebase API key and
OAuth client ID do not authenticate the Admin SDK.

Install backend dependencies and start FastAPI from the repository root:

```sh
python -m pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

The auth routes initialize Firebase on demand. Login and `/api/health` do not load
the RAG models or need Ollama. Approved chat requests require the reviewed SQLite
policy index, local retrieval models, and Ollama.

### Run chat locally

The new document/section index and policy graph have their own
[preparation and review workflow](policy-index.md). `--prepare-only` builds them
without loading models; `--preview-index` embeds local review sources without
activating them. Normal `--ingest` publication requires reviewed public sources.

The extension already calls `POST /api/ask`. A working login does not initialize
the policy index or the language model service. To run the assistant locally:

1. Install the backend dependencies, including the Python `ollama` package.
2. Start `ollama serve` in a separate terminal (or start the Ollama application).
   Run `ollama list` to confirm `qwen3:8b` is available; download it with
   `ollama pull qwen3:8b` if it is missing.
3. Restore the two verified public starter PDFs and build the source/graph index
   from the repository root if it has not already been prepared:

   ```sh
   ./venv/bin/python -m scripts.download_starter_policies
   ./venv/bin/python -m scripts.build_policy_graph build
   ```

   Current chat reads the reviewed SQLite index directly; publishing a Chroma
   collection is optional. Additional sources require the review procedure in
   [the policy index guide](policy-index.md).
4. Start FastAPI from the repository root:

   ```sh
   ./venv/bin/python -m uvicorn backend.main:app --reload --port 8000
   ```

5. In another terminal, run `cd frontend` and `pnpm dev`. Open the extension,
   sign in, sync the approved account, and send a question. See
   [the policy chat guide](policy-chat.md) for demo questions and tests.

The embedding model (`all-MiniLM-L6-v2`) and reranker
(`cross-encoder/ms-marco-MiniLM-L-6-v2`) download on first use if they are not cached.
The policy documents/index are local artifacts and are not included in this checkout.
Pipeline failures return a JSON `503` response; the FastAPI terminal contains the
underlying exception, while the extension displays an availability message.

## Configure the extension

Populate `VITE_FIREBASE_*` in `secret/.env` and the **Web application** OAuth
client ID in `VITE_GOOGLE_CLIENT_ID`. WXT and FastAPI both read `secret/.env`.
Keep the backend and frontend Firebase
project IDs consistent. Register each browser's actual
`browser.identity.getRedirectURL()` in that OAuth client's authorized redirect
URIs. Restart WXT and reload the extension after changing environment variables.

```sh
cd frontend
pnpm install
pnpm dev
```

## Profile contract

Both endpoints require `Authorization: Bearer <firebase_id_token>`:

- `POST /auth/session`: create the profile on first sign-in, otherwise load it.
- `GET /auth/me`: retrieve the current user's profile (also creates a missing profile).

Example response:

```json
{
  "uid": "firebase-uid",
  "email": "buyer@ucsc.edu",
  "name": "Test Buyer",
  "photoURL": null,
  "department": null,
  "clearance": "none",
  "is_approved": false,
  "role": "buyer",
  "created_at": "2026-10-08T00:00:00Z"
}
```

Name, email, and photo initially come from the verified Firebase identity.
Google sign-in does not supply a department or procurement clearance. An authorized
administrator assigns `department`, `clearance`, `role`, and `is_approved` in the
Firestore document (or a future admin/directory integration). Existing administrative
values are preserved on subsequent logins. Clients cannot set permissions through
the session endpoints. Restrict client writes to this collection with Firestore
Security Rules; the backend uses the Admin SDK and its IAM permissions.

`is_approved` gates assistant chat. Exact clearance `internal` permits public/internal
documents; `restricted` permits all three classifications. `none`, `public`, missing
and unknown values permit public documents only. Every document must also be active.
Role and department do not implicitly grant clearance, and clearance does not establish
purchasing authority. See [policy chat](policy-chat.md) for retrieval and access tests.
New users can log in and see their profile while awaiting approval.

To approve a test user, edit `users/{uid}` in Firestore, set `is_approved` to a
**boolean** `true`, and assign the department/clearance as appropriate. Click
**Sync Session with Backend** in extension settings. Local mock approval controls
have been removed.

## Use the profile inside FastAPI

Routes can access a verified user without trusting request-body profile fields:

```python
from typing import Annotated
from fastapi import Depends
from backend.auth.dependencies import get_current_user, require_approved_user
from backend.auth.models import UserProfile

def endpoint(user: Annotated[UserProfile, Depends(get_current_user)]):
    return {"name": user.name, "department": user.department, "clearance": user.clearance}
```

Use `Depends(require_approved_user)` for approved-only routes. `/api/ask` now uses
this dependency and reloads approval from Firestore on each request before invoking
the pipeline. It returns `401` for missing/invalid tokens, `403` for pending users,
and `503` when identity verification or profile storage is unavailable. The extension
uses fresh Firebase tokens and shows retryable errors instead of inventing profiles.

## Verification

```sh
python -m pytest tests/integration/test_auth.py rules/test_engine.py -q
cd frontend
pnpm compile
pnpm test
pnpm build
pnpm build:firefox
```

The backend tests stub Firebase and Firestore to verify invalid/expired/revoked tokens,
profile creation, permission ownership, concurrent creation, live approval changes,
and service failures. To confirm live setup, sign in with a new account, check the
Firestore document, assign test permissions as an admin, refresh the extension
profile, and verify an approved `/api/ask` request.

References: [Firebase Admin setup](https://firebase.google.com/docs/admin/setup),
[Firebase token verification](https://firebase.google.com/docs/auth/admin/verify-id-tokens).
