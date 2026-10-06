import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { api } from './api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => api.tokens.user);

  const login = useCallback(async (username, password) => {
    const profile = await api.login(username, password);
    setUser(profile);
    return profile;
  }, []);

  const logout = useCallback(() => {
    api.logout();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      login,
      logout,
      /** Mirrors the backend's rank order; the API remains the real gate. */
      atLeast: (role) => {
        const rank = { VIEWER: 0, DEVELOPER: 1, MANAGER: 2, ADMIN: 3 };
        return Boolean(user) && rank[user.role] >= rank[role];
      },
    }),
    [user, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>');
  return context;
}
