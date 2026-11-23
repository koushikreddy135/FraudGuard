import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { apiRequest, type User } from '../../services/api';
import { ShieldCheck, AlertCircle, Loader2 } from 'lucide-react';

export const AuthCallback: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const { login } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const token = searchParams.get('token');
    const oauthError = searchParams.get('oauth_error');

    if (oauthError) {
      setError(decodeURIComponent(oauthError));
      return;
    }

    if (!token) {
      setError("No authentication token was received from the identity provider.");
      return;
    }

    const completeOAuth = async () => {
      try {
        // Fetch user profile using the newly issued JWT token
        const user = await apiRequest<User>('/api/auth/me', {
          headers: {
            Authorization: `Bearer ${token}`
          }
        });

        // Update AuthContext session state
        login(token, user);

        // Redirect to customer dashboard
        navigate('/customer', { replace: true });
      } catch (err: any) {
        setError(err.message || "Failed to finalize authentication session.");
      }
    };

    completeOAuth();
  }, [searchParams, login, navigate]);

  return (
    <div className="theme-customer" style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: 'var(--bg-page)',
      fontFamily: 'inherit',
      padding: '24px'
    }}>
      <div style={{
        maxWidth: '440px',
        width: '100%',
        backgroundColor: 'var(--bg-card)',
        borderRadius: 'var(--radius-lg)',
        padding: '40px',
        boxShadow: 'var(--shadow-lg)',
        border: '1px solid var(--border-color)',
        textAlign: 'center'
      }}>
        <div style={{
          width: '56px',
          height: '56px',
          backgroundColor: error ? '#FEF2F2' : 'rgba(22, 78, 99, 0.08)',
          borderRadius: '16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          margin: '0 auto 20px',
          color: error ? '#DC2626' : 'var(--primary)'
        }}>
          {error ? <AlertCircle size={28} /> : <ShieldCheck size={28} />}
        </div>

        {error ? (
          <div>
            <h3 style={{ fontSize: '18px', fontWeight: 800, color: '#B91C1C', marginBottom: '8px' }}>
              Authentication Failed
            </h3>
            <p style={{ fontSize: '14px', color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: '24px' }}>
              {error}
            </p>
            <Link
              to="/login"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '10px 20px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'var(--primary)',
                color: '#FFFFFF',
                textDecoration: 'none',
                fontWeight: 600,
                fontSize: '14px'
              }}
            >
              Return to Login
            </Link>
          </div>
        ) : (
          <div>
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '16px', color: 'var(--primary)' }}>
              <Loader2 size={32} className="spin" style={{ animation: 'spin 1s linear infinite' }} />
            </div>
            <h3 style={{ fontSize: '18px', fontWeight: 800, color: 'var(--text-primary)', marginBottom: '8px' }}>
              Securing Session...
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)', margin: 0 }}>
              Verifying OpenID Connect claims and loading your customer portal.
            </p>
          </div>
        )}
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};
