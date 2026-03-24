import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import logo from '../assets/favicon.svg';

const LoginPage = () => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const { login } = useAuth();
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password }),
            });

            const data = await response.json();

            if (response.ok) {
                // Server sets HttpOnly cookie; we just store user info in state
                login(data.user);
                navigate('/dashboard');
            } else {
                setError(data.message || 'Login failed. Please try again.');
            }
        } catch {
            setError('Network error — is the server running?');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={styles.page}>
            {/* Background blobs */}
            <div style={{ ...styles.blob, top: '10%', left: '15%', background: 'rgba(51,177,176,0.15)' }} />
            <div style={{ ...styles.blob, bottom: '15%', right: '10%', background: 'rgba(51,177,176,0.10)', width: 300, height: 300 }} />

            <div className="glass-card fade-in" style={styles.card}>
                {/* Header */}
                <div style={styles.header}>
                    <div style={styles.logoCircle}>
                        <img src={logo} alt="ProdAI" style={{ height: 40, width: 'auto', display: 'block' }} />
                    </div>
                    <h1 style={styles.title}>Welcome Back</h1>
                    <p style={styles.subtitle}>Sign in to your account to continue</p>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} style={styles.form}>
                    {error && (
                        <div className="alert-error fade-in">{error}</div>
                    )}

                    <div className="form-group">
                        <label className="form-label" htmlFor="email">Email Address</label>
                        <input
                            id="email"
                            type="email"
                            className="form-input"
                            placeholder="you@example.com"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            autoComplete="email"
                        />
                    </div>

                    <div className="form-group">
                        <label className="form-label" htmlFor="password">Password</label>
                        <input
                            id="password"
                            type="password"
                            className="form-input"
                            placeholder="••••••••"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            autoComplete="current-password"
                        />
                    </div>

                    <button type="submit" className="btn btn-primary" disabled={loading} style={{ marginTop: 8 }}>
                        {loading ? (
                            <>
                                <span className="spinner" />
                                Signing in…
                            </>
                        ) : 'Sign In'}
                    </button>
                </form>

                {/* Hint */}
                <p style={styles.hint}>
                    Demo credentials: <code style={styles.code}>admin@plant.com</code> /
                    <code style={styles.code}> admin123</code>
                </p>
            </div>
        </div>
    );
};

const styles = {
    page: {
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
        position: 'relative',
        overflow: 'hidden',
    },
    blob: {
        position: 'absolute',
        width: 400,
        height: 400,
        borderRadius: '50%',
        filter: 'blur(80px)',
        pointerEvents: 'none',
    },
    card: {
        width: '100%',
        maxWidth: 420,
        padding: '40px 36px',
        display: 'flex',
        flexDirection: 'column',
        gap: 24,
        position: 'relative',
        zIndex: 1,
    },
    header: {
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 12,
    },
    logoCircle: {
        width: 60,
        height: 60,
        background: 'linear-gradient(135deg, #33B1B0, #2a9a99)',
        borderRadius: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: '0 8px 24px rgba(51,177,176,0.35)',
    },
    title: {
        fontSize: '1.75rem',
        fontWeight: 700,
        color: '#1a1a1a',
        margin: 0,
    },
    subtitle: {
        fontSize: '0.9rem',
        color: 'rgba(60,61,63,0.6)',
        margin: 0,
    },
    form: {
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
    },
    hint: {
        fontSize: '0.78rem',
        color: 'rgba(60,61,63,0.5)',
        textAlign: 'center',
        borderTop: '1px solid rgba(60,61,63,0.12)',
        paddingTop: 16,
    },
    code: {
        background: 'rgba(51,177,176,0.08)',
        borderRadius: 4,
        padding: '1px 5px',
        fontFamily: 'monospace',
        fontSize: '0.78rem',
        color: '#33B1B0',
    },
};

export default LoginPage;
