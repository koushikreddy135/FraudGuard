import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';

// Layouts
import { CustomerLayout } from './layouts/CustomerLayout';
import { AdminLayout } from './layouts/AdminLayout';

// Customer Pages
import { CustomerLogin } from './pages/customer/CustomerLogin';
import { CustomerRegister } from './pages/customer/CustomerRegister';
import { CustomerForgotPassword } from './pages/customer/CustomerForgotPassword';
import { CustomerDashboard } from './pages/customer/CustomerDashboard';
import { AuthCallback } from './pages/auth/AuthCallback';

// Admin Pages
import { AdminLogin } from './pages/admin/AdminLogin';
import { AdminDashboard } from './pages/admin/AdminDashboard';

const RootRedirect: React.FC = () => {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return user.role === 'ADMIN' ? <Navigate to="/admin" replace /> : <Navigate to="/customer" replace />;
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public / Landing Redirect */}
          <Route path="/" element={<RootRedirect />} />

          {/* Customer Auth Pages */}
          <Route path="/login" element={<CustomerLogin />} />
          <Route path="/register" element={<CustomerRegister />} />
          <Route path="/forgot-password" element={<CustomerForgotPassword />} />
          <Route path="/auth/callback" element={<AuthCallback />} />

          {/* Admin Auth Pages */}
          <Route path="/admin/login" element={<AdminLogin />} />

          {/* Protected Customer Portal */}
          <Route element={<ProtectedRoute allowedRole="CUSTOMER" redirectTo="/login" />}>
            <Route path="/customer" element={<CustomerLayout />}>
              <Route index element={<CustomerDashboard />} />
            </Route>
          </Route>

          {/* Protected Admin Portal */}
          <Route element={<ProtectedRoute allowedRole="ADMIN" redirectTo="/admin/login" />}>
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<AdminDashboard />} />
            </Route>
          </Route>

          {/* Catch-all redirect */}
          <Route path="*" element={<RootRedirect />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
};

export default App;
