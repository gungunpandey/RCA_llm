import React, { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    // On mount, check if we have a valid session by calling /api/auth/me
    useEffect(() => {
        fetch('/api/auth/me', { credentials: 'include' })
            .then(async (res) => {
                if (res.ok) {
                    const data = await res.json();
                    setUser(data);
                }
            })
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    // Called after a successful login — cookie is already set by the server
    const login = (userData) => {
        setUser(userData);
    };

    const logout = () => {
        // Call server to clear the cookie
        fetch('/api/auth/logout', { credentials: 'include' })
            .finally(() => setUser(null));
    };

    if (loading) {
        return (
            <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                height: '100vh', background: '#ffffff',
                color: '#3C3D3F', fontSize: '1.1rem',
            }}>
                Loading...
            </div>
        );
    }

    return (
        <AuthContext.Provider value={{ user, login, logout }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
