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

    // Determine if the user is a plant head or admin
    const isPlantHeadOrAdmin = user.role === 'Admin' || [
        'BNFC', 'Pellet 1', 'Pellet 2', 'SMS 1', 'SMS 2',
        'DRI 1', 'DRI 2', 'CPP', 'CPP 2', 'PGP', 'FIRE SERVICE'
    ].includes(user.role);

    return (
        <nav className="db-nav fade-in">
            {/* Brand / Logo */}
            <div className="db-nav-brand">
                <img src={logo} alt="ProdAI" style={{ height: 48, width: 'auto', display: 'block' }} />
            </div>

            {/* Pill container */}
            <div className="db-nav-pill glass-card">
                <div className="db-nav-right">
                    {/* 1. Dashboard */}
                    <button
                        className={`btn ${activePage === 'dashboard' ? 'btn-primary' : 'btn-ghost'}`}
                        style={navBtnStyle}
                        onClick={() => navigate('/dashboard')}
                    >
                        Dashboard
                    </button>

                    {/* 2. Log Issue */}
                    <button
                        className={`btn ${activePage === 'log-issue' ? 'btn-primary' : 'btn-ghost'}`}
                        style={navBtnStyle}
                        onClick={() => navigate('/log-breakdown')}
                    >
                        Log Issue
                    </button>

                    {/* 3. CAPA Board */}
                    <button
                        className={`btn ${activePage === 'capa-board' ? 'btn-primary' : 'btn-ghost'}`}
                        style={{ ...navBtnStyle, minWidth: 120 }}
                        onClick={() => navigate('/capa/board')}
                    >
                        CAPA Board
                    </button>

                    {/* 4. ProdAI */}
                    <button
                        className={`btn ${activePage === 'prodai' ? 'btn-primary' : 'btn-ghost'}`}
                        style={navBtnStyle}
                        onClick={() => navigate('/prodai')}
                    >
                        ProdAI
                    </button>

                    {/* 4.2. AI Assistant */}
                    <button
                        className={`btn ${activePage === 'chat' ? 'btn-primary' : 'btn-ghost'}`}
                        style={{ ...navBtnStyle, minWidth: 120 }}
                        onClick={() => navigate('/chat')}
                    >
                        AI Assistant
                    </button>

                    {/* 4.5. Plant PFD */}
                    <button
                        className={`btn ${activePage === 'plant-pfd' ? 'btn-primary' : 'btn-ghost'}`}
                        style={{ ...navBtnStyle, minWidth: 120 }}
                        onClick={() => navigate('/beneficiation-pfd')}
                    >
                        Plant PFD
                    </button>


                    {/* 5. Hello Admin dropdown */}
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
                                minWidth: 190,
                                zIndex: 1000,
                                overflow: 'hidden',
                            }}>
                                {isPlantHeadOrAdmin && (
                                    <button
                                        onClick={() => {
                                            setDropdownOpen(false);
                                            navigate('/equipment');
                                        }}
                                        style={{
                                            width: '100%',
                                            textAlign: 'left',
                                            padding: '10px 16px',
                                            background: 'none',
                                            border: 'none',
                                            cursor: 'pointer',
                                            fontSize: '0.875rem',
                                            color: '#3C3D3F',
                                            borderBottom: '1px solid rgba(0,0,0,0.06)',
                                            whiteSpace: 'nowrap',
                                        }}
                                        onMouseEnter={e => e.currentTarget.style.background = 'rgba(51,177,176,0.08)'}
                                        onMouseLeave={e => e.currentTarget.style.background = 'none'}
                                    >
                                        📋 Equipment Master
                                    </button>
                                )}
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
                                        whiteSpace: 'nowrap',
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
            </div>
        </nav>
    );
};

export default NavBar;
