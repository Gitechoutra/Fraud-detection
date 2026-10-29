import axios from 'axios';
import { getCity, getDeviceId } from '../utils/device';
import { API_BASE } from './client';

/**
 * Separate API clients for the customer banking app and the fraudster
 * console. Each has its own token (its own storage key), so the split-screen
 * demo can be logged in as a victim and a fraudster at once, and neither
 * ever sends the staff token. Every request carries this browser's device id
 * and chosen demo city for that role. A 401 tells the screen to log out
 * (e.g. the bank ended the fraudster's session after a "Not me").
 */
function createClient(role, defaultCity) {
  const key = `fs-${role}-token`;
  const store = {
    get() {
      try {
        return localStorage.getItem(key);
      } catch {
        return store.mem || null;
      }
    },
    set(token) {
      store.mem = token;
      try {
        if (token) localStorage.setItem(key, token);
        else localStorage.removeItem(key);
      } catch {
        /* storage unavailable: this tab only */
      }
    },
  };

  const http = axios.create({ baseURL: API_BASE, timeout: 30000 });
  http.interceptors.request.use((config) => {
    const token = store.get();
    if (token) config.headers.Authorization = `Bearer ${token}`;
    config.headers['X-Device-Id'] = getDeviceId(role);
    config.headers['X-Demo-City'] = getCity(role, defaultCity());
    return config;
  });
  http.interceptors.response.use(
    (res) => res,
    (error) => {
      if (error.response?.status === 401 && store.get() && !error.config.url.endsWith('/login')) {
        store.set(null);
        window.dispatchEvent(new CustomEvent(`fs:${role}-logout`, { detail: error.response.data?.error }));
      }
      return Promise.reject(error);
    },
  );
  const data = (p) => p.then((r) => r.data.data);
  return { http, data, token: store };
}

let customerHome = 'Hyderabad';
const customer = createClient('customer', () => customerHome);
const attacker = createClient('attacker', () => 'Delhi');

export const customerApi = {
  hasSession: () => Boolean(customer.token.get()),
  setHomeCity: (city) => {
    customerHome = city;
  },
  async login(username, password) {
    const res = await customer.data(customer.http.post('/customer/login', { username, password }));
    customer.token.set(res.token);
    return res;
  },
  async logout() {
    try {
      await customer.http.post('/customer/logout');
    } finally {
      customer.token.set(null);
    }
  },
  me: () => customer.data(customer.http.get('/customer/me')),
  payees: () => customer.data(customer.http.get('/customer/payees')),
  pay: (body) => customer.data(customer.http.post('/customer/payments', body)),
  history: (page = 1) => customer.data(customer.http.get('/customer/transactions', { params: { page } })),
  alerts: () => customer.data(customer.http.get('/customer/alerts')),
  markRead: () => customer.data(customer.http.post('/customer/alerts/read')),
  confirm: (id, password) => customer.data(customer.http.post(`/customer/alerts/${id}/confirm`, { password })),
  report: (id) => customer.data(customer.http.post(`/customer/alerts/${id}/report`)),
};

export const attackerApi = {
  hasSession: () => Boolean(attacker.token.get()),
  async login(username, password) {
    const res = await attacker.data(attacker.http.post('/attacker/login', { username, password }));
    attacker.token.set(res.token);
    return res;
  },
  async logout() {
    try {
      await attacker.http.post('/attacker/logout');
    } finally {
      attacker.token.set(null);
    }
  },
  me: () => attacker.data(attacker.http.get('/attacker/me')),
  run: (code) => attacker.data(attacker.http.post(`/attacker/attack/${code}`)),
  events: () => attacker.data(attacker.http.get('/attacker/events')),
  resetDemo: () => attacker.data(attacker.http.post('/demo/reset')),
};
