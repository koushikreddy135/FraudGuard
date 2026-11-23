import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

interface ProtectedRouteProps {
  allowedRole: 'CUSTOMER' | 'ADMIN';
  redirectTo: string;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ allowedRole, redirectTo }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        background: allowedRole === 'ADMIN' ? '#07090C' : '#F5F7ED',
        color: allowedRole === 'ADMIN' ? '#08BCEB' : '#164E63',
        fontSize: '1.25rem',
        fontWeight: 600
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            width: '40px',
            height: '40px',
            border: `3px solid ${allowedRole === 'ADMIN' ? '#243542' : '#D8E5D3'}`,
            borderTopColor: allowedRole === 'ADMIN' ? '#08BCEB' : '#164E63',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
            margin: '0 auto 16px'
          }} />
          Authenticating secure session...
        </div>
        <style>{`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  if (!user) {
    return <Navigate to={redirectTo} replace />;
  }

  if (user.role !== allowedRole) {
    // Prevent privilege escalation or cross-portal routing
    const fallback = user.role === 'ADMIN' ? '/admin' : '/customer';
    return <Navigate to={fallback} replace />;
  }

  return <Outlet />;
};
