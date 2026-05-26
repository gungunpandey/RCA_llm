import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import logo from '../assets/favicon.svg';

const navBtnStyle = {
    padding: '8px 18px',
    fontSize: '0.875rem',
    minWidth: '110px',
    textAlign: 'center',
    borderRadius: '8px',
    height: '38px',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxSizing: 'border-box',
    whiteSpace: 'nowrap',
};

const NavBar = ({ activePage }) => {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const [dropdownOpen, setDropdownOpen] = useState(false);
    const dropdownRef = useRef(null);

    // Close dropdown when clicking outside
    useEffect(() => {
        const handleClickOutside = (e) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
                setDropdownOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const handleLogout = () => {
        setDropdownOpen(false);
        logout();
        setTimeout(() => navigate('/login'), 100);
    };

    if (!user) return null;

    const displayName = user.role || user.email.split('@')[0];

    return (
        <nav className="db-nav fade-in">
            {/* Brand / Logo */}
            <div className="db-nav-brand">
                <img src={logo} alt="ProdAI" style={{ height: 48, width: 'auto', display: 'block' }} />
            </div>

            {/* Pill container */}
            <div className="db-nav-pill glass-card">
            <div className="db-nav-right">

                {/* 1. Equipment */}
                <button
                    className={`btn ${activePage === 'equipment' ? 'btn-primary' : 'btn-ghost'}`}
                    style={navBtnStyle}
                    onClick={() => navigate('/equipment')}
                >
                    Equipment
                </button>

                {/* 2. Log Issue */}
                <button
                    className={`btn ${activePage === 'log-issue' ? 'btn-primary' : 'btn-ghost'}`}
                    style={navBtnStyle}
                    onClick={() => navigate('/log-breakdown')}
                >
                    Log Issue
                </button>

                {/* 3. Dashboard */}
                <button
                    className={`btn ${activePage === 'dashboard' ? 'btn-primary' : 'btn-ghost'}`}
                    style={navBtnStyle}
                    onClick={() => navigate('/dashboard')}
                >
                    Dashboard
                </button>

                {/* 4. CAPA Board (single line) */}
                <button
                    className={`btn ${activePage === 'capa-board' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ ...navBtnStyle, minWidth: 120 }}
                    onClick={() => navigate('/capa/board')}
                >
                    CAPA Board
                </button>

                {/* 5. Analytics */}
                <button
                    className={`btn ${activePage === 'analytics' ? 'btn-primary' : 'btn-ghost'}`}
                    style={navBtnStyle}
                    onClick={() => navigate('/analytics')}
                >
                    Analytics
                </button>

                {/* 6. Hello Admin dropdown */}
                <div ref={dropdownRef} style={{ position: 'relative' }}>
                    <button
                        className="btn btn-ghost"
                        style={navBtnStyle}
                        onClick={() => setDropdownOpen(prev => !prev)}
                    >
                        Hello {displayName} ▾
                    </button>

                    {dropdownOpen && (
                        <div style={{
                            position: 'absolute',
                            top: 'calc(100% + 8px)',
                            right: 0,
                            background: '#fff',
                            border: '1px solid rgba(51,177,176,0.25)',
                            borderRadius: 8,
                            boxShadow: '0 8px 24px rgba(0,0,0,0.10)',
                            minWidth: 140,
                            zIndex: 1000,
                            overflow: 'hidden',
                        }}>
                            <button
                                onClick={handleLogout}
                                style={{
                                    width: '100%',
                                    textAlign: 'left',
                                    padding: '10px 16px',
                                    background: 'none',
                                    border: 'none',
                                    cursor: 'pointer',
                                    fontSize: '0.875rem',
                                    color: '#3C3D3F',
                                }}
                                onMouseEnter={e => e.currentTarget.style.background = 'rgba(51,177,176,0.08)'}
                                onMouseLeave={e => e.currentTarget.style.background = 'none'}
                            >
                                🚪 Logout
                            </button>
                        </div>
                    )}
                </div>
            </div>
            </div>{/* end db-nav-pill */}
        </nav>
    );
};

export default NavBar;
