import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiRequest, setApiToken, type User } from '../services/api';

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (token: string, user: User) => void;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const login = useCallback((newToken: string, newUser: User) => {
    setToken(newToken);
    setUser(newUser);
    setApiToken(newToken);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiRequest('/api/auth/logout', { method: 'POST' });
    } catch {
      // Ignore network errors during logout
    } finally {
      setToken(null);
      setUser(null);
      setApiToken(null);
    }
  }, []);

  const refreshProfile = useCallback(async () => {
    try {
      // Validates HttpOnly session cookie with backend /api/auth/me
      const data = await apiRequest<User>('/api/auth/me');
      setUser(data);
    } catch {
      // If unauthenticated or session expired, reset state cleanly
      setUser(null);
      setToken(null);
      setApiToken(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshProfile();

    const handleSessionExpired = () => {
      setUser(null);
      setToken(null);
      setApiToken(null);
    };

    window.addEventListener('fraudguard:session-expired', handleSessionExpired);
    return () => {
      window.removeEventListener('fraudguard:session-expired', handleSessionExpired);
    };
  }, [refreshProfile]);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
