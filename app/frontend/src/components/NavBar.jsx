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
        // After cookie is cleared, redirect to login
        setTimeout(() => navigate('/login'), 100);
    };

    if (!user) return null;

    // Display name: use role if available, fallback to email prefix
    const displayName = user.role || user.email.split('@')[0];

    return (
        <nav className="db-nav fade-in">
            {/* Brand / Logo */}
            <div className="db-nav-brand">
                <img src={logo} alt="ProdAI" style={{ height: 48, width: 'auto', display: 'block' }} />
            </div>

            {/* Pill container — wraps only the 4 buttons */}
            <div className="db-nav-pill glass-card">

            {/* Right-side nav buttons */}
            <div className="db-nav-right">
                {/* Dashboard button */}
                <button
                    className={`btn ${activePage === 'dashboard' ? 'btn-primary' : 'btn-ghost'}`}
                    style={navBtnStyle}
                    onClick={() => navigate('/dashboard')}
                >
                    Dashboard
                </button>

                {/* Log Issue button */}
                <button
                    className={`btn ${activePage === 'log-issue' ? 'btn-primary' : 'btn-ghost'}`}
                    style={navBtnStyle}
                    onClick={() => navigate('/log-breakdown')}
                >
                    Log Issue
                </button>

                {/* CAPA Board button */}
                <button
                    className={`btn ${activePage === 'capa-board' ? 'btn-primary' : 'btn-ghost'}`}
                    style={navBtnStyle}
                    onClick={() => navigate('/capa/board')}
                >
                    CAPA Board
                </button>

                {/* Hello, [Role] dropdown */}
                <div ref={dropdownRef} style={{ position: 'relative' }}>
                    <button
                        className="btn btn-ghost"
                        style={navBtnStyle}
                        onClick={() => setDropdownOpen(prev => !prev)}
                    >
                        Hello, {displayName} ▾
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
