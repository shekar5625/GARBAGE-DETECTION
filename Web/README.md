# Web — Garbage Detection dashboard

React 19 + Vite review dashboard for the Flask API in `../Backend`.

## Run

```
npm install
npm run dev        # http://localhost:5173
```

The Flask API must be running on :5000 (`cd ../Backend && python api.py`).

### Pointing at a different API host

Nothing in `src/` contains a host or port. All requests go to `/api/...`, which
`vite.config.js` proxies to Flask. To target another machine:

```
VITE_API_TARGET=http://192.168.1.50:5000 npm run dev
```

For a production build (`npm run build` -> `dist/`), the dev proxy no longer
applies: serve `dist/` behind a reverse proxy that maps `/api` to Flask.

## Screens

| Route       | `is_verified` | What it does                                    |
|-------------|---------------|-------------------------------------------------|
| `/login`    | —             | `/valid/<user>/<pass>`; username doubles as area |
| `/pending`  | 0             | Review queue — Verify / Dismiss                  |
| `/verified` | 1             | Confirmed — can return to pending                |
| `/deleted`  | 2             | Dismissed — Restore, or delete permanently       |
| `/history`  | all           | Every row, with per-state counts                 |

Sign in as `admin` to see every area; any other username is scoped to the area
of the same name (this is how the backend's `/fetch/<area>` routes work).

## Layout

```
src/
  api/client.js        every API call; the one place the `iamge_path`
                       typo and filename-as-id quirk are handled
  api/useDetections.js load + poll a listing, with reload()
  auth/AuthContext.jsx session state (localStorage), area scoping
  components/          Layout (nav + pending badge), DetectionTable,
                       ImageViewer, RequireAuth
  pages/               one file per route
```

## Notes

- Verify and Dismiss **toggle** server-side (0↔1 and 0↔2), so the same button
  reverses itself — that's the backend's behaviour, mirrored here.
- `/delete_row` and `/delete_all` are the only irreversible calls; both sit
  behind an inline confirmation on `/deleted`.
- `/valid` sends the password in the URL path in plaintext. That's the API's
  design and can't be fixed client-side.
