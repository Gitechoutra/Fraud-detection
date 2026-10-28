import axios from 'axios';

/**
 * Axios instance for staff APIs.
 *  - attaches the access token,
 *  - on a 401 "TOKEN_EXPIRED" refreshes once (concurrent requests wait for the
 *    same refresh) and retries,
 *  - if refreshing fails, clears the session and tells the app to log out.
 * Tokens live in localStorage; every access is wrapped in try/catch because
 * storage can be unavailable (private windows, blocked site data).
 */

export const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';
const KEY = 'fs-session';

export const session = {
  get() {
    try {
      return JSON.parse(localStorage.getItem(KEY)) || null;
    } catch {
      return null;
    }
  },
  set(value) {
    try {
      localStorage.setItem(KEY, JSON.stringify(value));
    } catch {
      /* storage unavailable: session lasts for this tab only */
    }
    memory = value;
  },
  clear() {
    try {
      localStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
    memory = null;
  },
};
let memory = session.get();
const current = () => memory || session.get();

const client = axios.create({ baseURL: API_BASE, timeout: 30000 });

client.interceptors.request.use((config) => {
  const s = current();
  if (s?.access_token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${s.access_token}`;
  }
  return config;
});

let refreshing = null;

async function refreshAccess() {
  const s = current();
  if (!s?.refresh_token) throw new Error('no refresh token');
  const res = await axios.post(`${API_BASE}/auth/refresh`, null, {
    headers: { Authorization: `Bearer ${s.refresh_token}` },
  });
  const next = { ...s, access_token: res.data.data.access_token };
  session.set(next);
  return next.access_token;
}

client.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    const code = error.response?.data?.error?.code;
    if (error.response?.status === 401 && code === 'TOKEN_EXPIRED' && original && !original._retried) {
      original._retried = true;
      try {
        refreshing = refreshing || refreshAccess().finally(() => (refreshing = null));
        const token = await refreshing;
        original.headers.Authorization = `Bearer ${token}`;
        return client(original);
      } catch {
        session.clear();
        window.dispatchEvent(new Event('fs:logout'));
      }
    } else if (error.response?.status === 401 && current()) {
      session.clear();
      window.dispatchEvent(new Event('fs:logout'));
    }
    return Promise.reject(error);
  },
);

/** The friendliest message we can get from an API error. */
export function errorMessage(err, fallback = 'Something went wrong. Please try again.') {
  if (!err?.response) return 'Cannot reach the FraudShield server. Is the backend running?';
  const e = err.response.data?.error;
  if (e?.details && typeof e.details === 'object') {
    const first = Object.entries(e.details)[0];
    if (first) return `${e.message} (${first[0]}: ${[].concat(first[1]).join(', ')})`;
  }
  return e?.message || fallback;
}

/** Unwraps `{ ok, data }`. */
export const data = (p) => p.then((r) => r.data.data);

export default client;
