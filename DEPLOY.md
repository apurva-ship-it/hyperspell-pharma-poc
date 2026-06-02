# Deploying to Vercel

The Flask app deploys to Vercel via `@vercel/python` (see `vercel.json` — the `app`
object in `app.py` is the WSGI entrypoint). Hyperspell and Langfuse are external APIs
and work unchanged. The only piece that must move off your laptop is **Keycloak**.

The project is already linked: `hyperspell_pharma_poc` (see `.vercel/project.json`).

## 1. Host Keycloak publicly

Vercel functions can't reach `localhost:8080`, so run Keycloak somewhere with a public
HTTPS URL (Railway, Fly.io, Render, or a small VM). Use the same realm import:

- Mount `keycloak/realm-export.json` as the import file (same as `docker-compose.yml`).
- The realm now already whitelists `https://*.vercel.app/auth/callback` and
  `https://*.vercel.app` web origins, so both production and preview URLs work.
- ⚠️ Change the client secret `flask-app-secret-change-me` to a real value (update it
  in both the realm and the `KEYCLOAK_CLIENT_SECRET` env var below).

Note the public URL, e.g. `https://keycloak-yourapp.up.railway.app`.

## 2. Set environment variables on Vercel

Set these in the Vercel project (Settings → Environment Variables, or
`vercel env add`). The app reads `VERCEL` (auto-set by Vercel) to enable HTTPS-aware
URL generation for the OIDC redirect.

```
HYPERSPELL_API_KEY      = hs2-...                       # same as local .env
FLASK_SECRET_KEY        = <generate a fresh long random string>
KEYCLOAK_URL            = https://<your-public-keycloak-url>
KEYCLOAK_REALM          = pharma-poc
KEYCLOAK_CLIENT_ID      = flask-app
KEYCLOAK_CLIENT_SECRET  = <the real secret you set in step 1>
LANGFUSE_PUBLIC_KEY     = pk-lf-...                      # optional
LANGFUSE_SECRET_KEY     = sk-lf-...                      # optional
LANGFUSE_HOST           = https://cloud.langfuse.com     # optional
```

## 3. Deploy

```
vercel           # preview deploy
vercel --prod    # production deploy
```

## 4. Verify

- Open the deployment URL → it should redirect to your hosted Keycloak login.
- After login the OIDC redirect lands on `https://<domain>/auth/callback` (https, thanks
  to ProxyFix) and matches the realm's allowed redirect URIs.
- Test the global chat, citations, and (as admin) document upload.

## Notes / limits on serverless

- **Ingest of the bundled `.md` files** works — they ship in the deployment bundle and
  are read-only-read at runtime. Uploads go straight to Hyperspell (no disk write), so
  they work fine too.
- Sessions use Flask's default **signed cookies** — no server-side session store needed,
  which is correct for serverless. Just keep `FLASK_SECRET_KEY` stable across deploys.
