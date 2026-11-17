import React, { createContext, useContext, useState, useEffect } from 'react';
import { User } from '../types';
import { api } from '../services/api';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  serverUrl: string;
  login: (u: string, p: string) => Promise<void>;
  logout: () => Promise<void>;
  updateServerUrl: (url: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isLoading: true,
  serverUrl: '',
  login: async () => {},
  logout: async () => {},
  updateServerUrl: async () => {},
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [serverUrl, setServerUrlState] = useState('');

  useEffect(() => {
    (async () => {
      try {
        await api.init();
        setServerUrlState(api.getServerUrl());
        const storedUser = await api.getStoredUser();
        if (storedUser && api.getToken()) {
          setUser(storedUser);
        }
      } catch (e) {
        console.warn('Auth initialization error:', e);
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const login = async (u: string, p: string) => {
    const res = await api.login(u, p);
    setUser(res.user);
  };

  const logout = async () => {
    await api.logout();
    setUser(null);
  };

  const updateServerUrl = async (url: string) => {
    await api.setServerUrl(url);
    setServerUrlState(api.getServerUrl());
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        serverUrl,
        login,
        logout,
        updateServerUrl,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
