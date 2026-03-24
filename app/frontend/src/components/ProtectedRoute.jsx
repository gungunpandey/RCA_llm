import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const ProtectedRoute = ({ children, allowedRoles }) => {
    const { user } = useAuth();

    if (!user) {
        return <Navigate to="/login" replace />;
    }

    if (allowedRoles && !allowedRoles.includes(user.role)) {
        return (
            <div style={{
                minHeight: '100vh',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: 24,
            }}>
                <div className="glass-card fade-in" style={{
                    padding: '40px 36px',
                    textAlign: 'center',
                    maxWidth: 380,
                }}>
                    <div style={{ fontSize: '3rem', marginBottom: 16 }}>🚫</div>
                    <h2 style={{ margin: '0 0 10px', color: '#f0f0f0', fontSize: '1.4rem' }}>Access Denied</h2>
                    <p style={{ margin: 0, color: 'rgba(240,240,240,0.6)', fontSize: '0.9rem' }}>
                        Your role (<strong style={{ color: '#f0f0f0' }}>{user.role}</strong>) does not have permission to view this page.
                    </p>
                </div>
            </div>
        );
    }

    return children;
};

export default ProtectedRoute;
