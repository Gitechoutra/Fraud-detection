import axios from 'axios';
import client, { API_BASE, data } from './client';

const q = (params) => ({ params });

export const authApi = {
  login: (username, password) => data(client.post('/auth/login', { username, password })),
  me: () => data(client.get('/auth/me')),
  logout: (refresh_token) => data(client.post('/auth/logout', { refresh_token })),
};

export const txnApi = {
  list: (params) => data(client.get('/transactions', q(params))),
  latest: (since_id) => data(client.get('/transactions/latest', q(since_id ? { since_id } : {}))),
  detail: (id) => data(client.get(`/transactions/${id}`)),
};

export const alertApi = {
  list: (params) => data(client.get('/alerts', q(params))),
  update: (id, body) => data(client.patch(`/alerts/${id}`, body)),
};

export const caseApi = {
  get: (id) => data(client.get(`/cases/${id}`)),
  addNote: (id, body) => data(client.post(`/cases/${id}/notes`, { body })),
  close: (id, outcome, notes) => data(client.patch(`/cases/${id}/outcome`, { outcome, notes })),
};

export const ruleApi = {
  list: () => data(client.get('/rules')),
  update: (code, body) => data(client.put(`/rules/${code}`, body)),
  bands: (body) => data(client.put('/rules/bands', body)),
};

export const watchlistApi = {
  list: (params) => data(client.get('/watchlist', q(params))),
  add: (body) => data(client.post('/watchlist', body)),
  remove: (id) => data(client.delete(`/watchlist/${id}`)),
};

export const dashboardApi = {
  summary: (range) => data(client.get('/dashboard/summary', q({ range }))),
  charts: (range) => data(client.get('/dashboard/charts', q({ range }))),
};

export const simulatorApi = {
  run: (code) => data(client.post(`/simulator/scenario/${code}`)),
  start: (rate, fraud_ratio) => data(client.post('/simulator/stream/start', { rate, fraud_ratio })),
  stop: () => data(client.post('/simulator/stream/stop')),
  status: () => data(client.get('/simulator/stream/status')),
};

export const evaluationApi = {
  run: (size, fraud_ratio) => data(client.post('/evaluation/run', { size, fraud_ratio })),
  status: () => data(client.get('/evaluation/status')),
  latest: () => data(client.get('/evaluation/latest')),
  history: () => data(client.get('/evaluation/history')),
};

export const auditApi = { list: (params) => data(client.get('/audit', q(params))) };

export const userApi = {
  list: () => data(client.get('/users')),
  create: (body) => data(client.post('/users', body)),
  update: (id, body) => data(client.patch(`/users/${id}`, body)),
};

export const bankDemoApi = {
  reset: () => data(client.post('/bank-demo/reset')),
};

/**
 * The demo bank app. Each phone on the OTP Shield page has its own bank
 * session token, so these calls take the token explicitly instead of using
 * the staff client.
 */
export function bankPhone() {
  let token = null;
  const http = axios.create({ baseURL: API_BASE, timeout: 20000 });
  http.interceptors.request.use((config) => {
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  });
  return {
    info: () => data(http.get('/bank-demo/info')),
    login: async (body) => {
      const res = await data(http.post('/bank-demo/login', body));
      token = res.token;
      return res;
    },
    logout: () => {
      token = null;
    },
    me: () => data(http.get('/bank-demo/me')),
    addPayee: (body) => data(http.post('/bank-demo/payees', body)),
    send: (beneficiary_id, amount) => data(http.post('/bank-demo/send', { beneficiary_id, amount })),
    verify: (otp_request_id, otp) => data(http.post('/otp/verify', { otp_request_id, otp })),
    status: (id) => data(http.get(`/otp/request/${id}/status`)),
    pending: () => data(http.get('/otp/approval/pending')),
    respond: (id, answer) => data(http.post(`/otp/approval/${id}/respond`, { answer })),
    notifications: () => data(http.get('/notifications')),
  };
}
