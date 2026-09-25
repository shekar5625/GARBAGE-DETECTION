// Thin wrapper over Backend/api.py.
//
// Two quirks of that API are load-bearing and deliberately preserved here:
//   1. A detection's identity is its IMAGE FILENAME, not a numeric id.
//      /verify/<id>, /temp_delete/<id> and /delete_row/<id> all run
//      `WHERE image = "<id>"`. `id` below is always that filename.
//   2. The listing payload misspells the image key as `iamge_path`.
//      normalise() is the single place that typo is tolerated.
//
// Area scoping: the literal area 'admin' means "all areas" server-side.

const BASE = '/api'

async function request(path, options) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) throw new Error(`${options?.method || 'GET'} ${path} -> ${res.status}`)
  return res
}

async function getJSON(path) {
  return (await request(path)).json()
}

// One detection row, with the API's shape translated to something sane.
function normalise(row) {
  return {
    id: row.iamge_path, // sic - the API's own spelling, and the row's identity
    image: row.iamge_path,
    date: row.date,
    time: row.time,
    area: row.location,
    mac: row.mac_address,
    status: row.approved, // 0 pending | 1 verified | 2 soft-deleted
  }
}

// Full URL for a detection image, for use as an <img src>.
export const mediaUrl = (image) => `${BASE}/media/${encodeURIComponent(image)}`

export const api = {
  // --- auth -------------------------------------------------------------
  // NOTE: /valid puts the password in the URL path in plaintext. That is the
  // backend's design; it is not something this client can fix.
  async login(username, password) {
    const data = await getJSON(
      `/valid/${encodeURIComponent(username)}/${encodeURIComponent(password)}`
    )
    return data.status === 'Yes' ? { username: data.Username } : null
  },

  // --- listings ---------------------------------------------------------
  async pending(area) {
    const d = await getJSON(`/fetch/${encodeURIComponent(area)}`)
    return (d.data || []).map(normalise)
  },

  async verified(area) {
    const d = await getJSON(`/fetchv/${encodeURIComponent(area)}`)
    return (d.data || []).map(normalise)
  },

  async deleted(area) {
    const d = await getJSON(`/fetch_delete/${encodeURIComponent(area)}`)
    return (d.data || []).map(normalise)
  },

  // History has no area-scoped route; /fetch_all returns every row, so a
  // non-admin user is filtered client-side to keep the scoping consistent.
  async history(area) {
    const d = await getJSON('/fetch_all')
    const rows = (d.data || []).map(normalise)
    return area === 'admin' ? rows : rows.filter((r) => r.area === area)
  },

  async pendingCount(area) {
    const d = await getJSON(`/count/${encodeURIComponent(area)}`)
    return d.count ?? 0
  },

  // --- state transitions ------------------------------------------------
  // Both of these TOGGLE server-side: verify flips 0<->1, remove flips 0<->2.
  verify: (id, area) =>
    request(`/verify/${encodeURIComponent(id)}/${encodeURIComponent(area)}`, { method: 'POST' }),

  remove: (id) => request(`/temp_delete/${encodeURIComponent(id)}`, { method: 'POST' }),

  // Permanent. Only ever call on a row already at status 2.
  purge: (id) => request(`/delete_row/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  purgeAll: () => request('/delete_all', { method: 'DELETE' }),
}
