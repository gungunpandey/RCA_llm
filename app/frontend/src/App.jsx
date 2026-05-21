import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import BreakdownLogPage from './pages/BreakdownLogPage';
import CAPACreationPage from './pages/CAPACreationPage';
import CAPATrackingBoard from './pages/CAPATrackingBoard';
import CAPADetailPage from './pages/CAPADetailPage';
import EquipmentMasterPage from './pages/EquipmentMasterPage';
import HistoricalAnalyticsPage from './pages/HistoricalAnalyticsPage';
import ProtectedRoute from './components/ProtectedRoute';

function App() {
    return (
        <AuthProvider>
            <BrowserRouter>
                <Routes>
                    <Route path="/login" element={<LoginPage />} />

                    <Route
                        path="/dashboard"
                        element={
                            <ProtectedRoute>
                                <DashboardPage />
                            </ProtectedRoute>
                        }
                    />

                    <Route
                        path="/log-breakdown"
                        element={
                            <ProtectedRoute allowedRoles={['Admin', 'Maintenance Engineer']}>
                                <BreakdownLogPage />
                            </ProtectedRoute>
                        }
                    />

                    <Route
                        path="/capa/create"
                        element={
                            <ProtectedRoute>
                                <CAPACreationPage />
                            </ProtectedRoute>
                        }
                    />

                    <Route
                        path="/capa/board"
                        element={
                            <ProtectedRoute>
                                <CAPATrackingBoard />
                            </ProtectedRoute>
                        }
                    />

                    <Route
                        path="/capa/:id/detail"
                        element={
                            <ProtectedRoute>
                                <CAPADetailPage />
                            </ProtectedRoute>
                        }
                    />

                    <Route
                        path="/equipment"
                        element={
                            <ProtectedRoute>
                                <EquipmentMasterPage />
                            </ProtectedRoute>
                        }
                    />

                    <Route
                        path="/analytics"
                        element={
                            <ProtectedRoute>
                                <HistoricalAnalyticsPage />
                            </ProtectedRoute>
                        }
                    />

                    <Route path="/" element={<Navigate to="/dashboard" replace />} />
                    <Route path="*" element={<div>404 Not Found</div>} />
                </Routes>
            </BrowserRouter>
        </AuthProvider>
    );
}

export default App;

