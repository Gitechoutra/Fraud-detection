import { createContext, useCallback, useEffect, useMemo, useState } from 'react';
import { session } from '../api/client';
import { authApi } from '../api/endpoints';

export const AuthContext = createContext(null);

const RANK = { ANALYST: 1, RISK_MANAGER: 2, ADMIN: 3 };

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => session.get()?.user || null);
  const [checking, setChecking] = useState(!!session.get());

  // Confirm a stored session is still valid when the app opens.
  useEffect(() => {
    if (!session.get()) return;
    authApi
      .me()
      .then((me) => {
        setUser(me);
        session.set({ ...session.get(), user: me });
      })
      .catch(() => {
        session.clear();
        setUser(null);
      })
      .finally(() => setChecking(false));
  }, []);

  useEffect(() => {
    const onLogout = () => setUser(null);
    window.addEventListener('fs:logout', onLogout);
    return () => window.removeEventListener('fs:logout', onLogout);
  }, []);

  const login = useCallback(async (username, password) => {
    const res = await authApi.login(username, password);
    session.set({ access_token: res.access_token, refresh_token: res.refresh_token, user: res.user });
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(async () => {
    const s = session.get();
    try {
      if (s?.access_token) await authApi.logout(s.refresh_token);
    } catch {
      /* the session ends locally either way */
    }
    session.clear();
    setUser(null);
  }, []);

  /** hasRole('RISK_MANAGER') is true for risk managers and admins. */
  const hasRole = useCallback((min) => !!user && (RANK[user.role] || 0) >= RANK[min], [user]);

  const value = useMemo(() => ({ user, checking, login, logout, hasRole }), [user, checking, login, logout, hasRole]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
