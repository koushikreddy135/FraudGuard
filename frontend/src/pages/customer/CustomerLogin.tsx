import React, { useState, useEffect } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { apiRequest, type AuthResponse } from '../../services/api';
import { ShieldCheck, Eye, EyeOff, Lock, Mail, ArrowRight, AlertCircle } from 'lucide-react';

export const CustomerLogin: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [searchParams] = useSearchParams();
  const { login } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const oauthError = searchParams.get('oauth_error');
    if (oauthError) {
      setError(decodeURIComponent(oauthError));
    }
  }, [searchParams]);

  const handleGoogleOAuth = async () => {
    setError(null);
    setGoogleLoading(true);
    try {
      const data = await apiRequest<{ configured: boolean; url: string | null; message: string }>('/api/auth/oauth/google/url');
      if (data.configured && data.url) {
        window.location.href = data.url;
      } else {
        setError(data.message || 'Google OAuth is not configured. Please add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env.');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to initiate Google Sign-In.');
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const data = await apiRequest<AuthResponse>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: email.trim(),
          password,
          portal_type: 'CUSTOMER'
        })
      });

      login(data.access_token, data.user);
      navigate('/customer');
    } catch (err: any) {
      setError(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="theme-customer" style={{
      minHeight: '100vh',
      display: 'flex',
      backgroundColor: 'var(--bg-page)',
      color: 'var(--text-primary)',
      fontFamily: 'inherit'
    }}>
      {/* Visual branding banner on desktop */}
      <div style={{
        flex: 1,
        backgroundColor: '#164E63',
        backgroundImage: 'radial-gradient(circle at 20% 30%, #1e6682 0%, #0d3443 100%)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        padding: '60px',
        color: '#FFFFFF',
        position: 'relative',
        overflow: 'hidden'
      }}>
        <div style={{
          position: 'absolute',
          top: '-10%',
          right: '-10%',
          width: '500px',
          height: '500px',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(183,245,168,0.18) 0%, rgba(22,78,99,0) 70%)',
          pointerEvents: 'none'
        }} />

        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', zIndex: 1 }}>
          <div style={{
            width: '46px',
            height: '46px',
            backgroundColor: 'rgba(255, 255, 255, 0.1)',
            backdropFilter: 'blur(8px)',
            borderRadius: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#B7F5A8',
            border: '1px solid rgba(255,255,255,0.2)'
          }}>
            <ShieldCheck size={28} />
          </div>
          <div>
            <h2 style={{ fontSize: '22px', fontWeight: 800, margin: 0, letterSpacing: '-0.5px' }}>FraudGuard</h2>
            <p style={{ margin: 0, fontSize: '12px', color: '#A8DDEB', letterSpacing: '0.5px', textTransform: 'uppercase' }}>
              Personal Banking Protection
            </p>
          </div>
        </div>

        <div style={{ maxWidth: '480px', zIndex: 1 }}>
          <div style={{
            display: 'inline-block',
            padding: '6px 14px',
            backgroundColor: 'rgba(183, 245, 168, 0.15)',
            border: '1px solid rgba(183, 245, 168, 0.4)',
            color: '#B7F5A8',
            borderRadius: '20px',
            fontSize: '12px',
            fontWeight: 700,
            marginBottom: '20px'
          }}>
            PREMIER CUSTOMER SECURITY
          </div>
          <h1 style={{ fontSize: '38px', fontWeight: 800, lineHeight: 1.2, marginBottom: '18px', letterSpacing: '-0.8px' }}>
            Next-generation fraud defense for peace of mind.
          </h1>
          <p style={{ fontSize: '16px', color: '#D8E5D3', lineHeight: 1.6 }}>
            FraudGuard uses calibrated machine learning to monitor outbound transactions, preventing account takeovers and fraudulent withdrawals before they occur.
          </p>
        </div>

        <div style={{ fontSize: '13px', color: '#A8DDEB', zIndex: 1 }}>
          Protected by FraudGuard Enterprise AI &copy; 2026. All rights reserved.
        </div>
      </div>

      {/* Login Form Panel */}
      <div style={{
        width: '540px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        padding: '60px 50px',
        backgroundColor: 'var(--bg-card)'
      }}>
        <div style={{ maxWidth: '400px', width: '100%', margin: '0 auto' }}>
          <div style={{ marginBottom: '32px' }}>
            <h2 style={{ fontSize: '26px', fontWeight: 800, color: 'var(--text-primary)', marginBottom: '8px' }}>
              Welcome back
            </h2>
            <p style={{ fontSize: '14px', color: 'var(--text-muted)' }}>
              Sign in to your customer portal to manage your protected accounts.
            </p>
          </div>

          {error && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '12px 16px',
              backgroundColor: '#FEF2F2',
              border: '1px solid #FCA5A5',
              borderRadius: 'var(--radius-sm)',
              color: '#B91C1C',
              fontSize: '13px',
              marginBottom: '24px'
            }}>
              <AlertCircle size={18} style={{ flexShrink: 0 }} />
              <div>{error}</div>
            </div>
          )}

          {/* Google OAuth Button */}
          <button
            type="button"
            onClick={handleGoogleOAuth}
            disabled={googleLoading || loading}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '12px',
              width: '100%',
              padding: '12px',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: '#FFFFFF',
              border: '1px solid #D1D5DB',
              color: '#374151',
              fontWeight: 600,
              fontSize: '14px',
              cursor: (googleLoading || loading) ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s ease',
              boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
              opacity: (googleLoading || loading) ? 0.7 : 1
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
            </svg>
            {googleLoading ? 'Connecting to Google...' : 'Continue with Google'}
          </button>

          <div style={{
            display: 'flex',
            alignItems: 'center',
            margin: '20px 0',
            color: 'var(--text-muted)',
            fontSize: '12px'
          }}>
            <div style={{ flex: 1, height: '1px', backgroundColor: 'var(--border-color)' }} />
            <span style={{ padding: '0 12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>or sign in with email</span>
            <div style={{ flex: 1, height: '1px', backgroundColor: 'var(--border-color)' }} />
          </div>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                Email address
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  type="email"
                  required
                  placeholder="name@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '12px 14px 12px 40px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--bg-card-subtle)',
                    color: 'var(--text-primary)',
                    fontSize: '14px',
                    outline: 'none',
                    transition: 'border-color 0.2s'
                  }}
                />
                <Mail size={18} style={{ position: 'absolute', left: '13px', top: '13px', color: 'var(--text-muted)' }} />
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Password
                </label>
                <Link to="/forgot-password" style={{ fontSize: '12px', color: 'var(--text-secondary)', textDecoration: 'none', fontWeight: 600 }}>
                  Forgot password?
                </Link>
              </div>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '12px 40px 12px 40px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--bg-card-subtle)',
                    color: 'var(--text-primary)',
                    fontSize: '14px',
                    outline: 'none'
                  }}
                />
                <Lock size={18} style={{ position: 'absolute', left: '13px', top: '13px', color: 'var(--text-muted)' }} />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  style={{
                    position: 'absolute',
                    right: '12px',
                    top: '12px',
                    background: 'none',
                    border: 'none',
                    color: 'var(--text-muted)',
                    padding: 0
                  }}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                padding: '13px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'var(--primary)',
                color: '#FFFFFF',
                border: 'none',
                fontWeight: 700,
                fontSize: '14px',
                marginTop: '10px',
                opacity: loading ? 0.7 : 1,
                boxShadow: 'var(--shadow-md)'
              }}
            >
              {loading ? 'Authenticating...' : 'Sign in to Portal'}
              {!loading && <ArrowRight size={17} />}
            </button>
          </form>

          <div style={{ marginTop: '28px', textAlign: 'center', fontSize: '13px', color: 'var(--text-muted)' }}>
            New to FraudGuard?{' '}
            <Link to="/register" style={{ color: 'var(--text-primary)', fontWeight: 700, textDecoration: 'none' }}>
              Create an account
            </Link>
          </div>

          <div style={{ marginTop: '36px', paddingTop: '20px', borderTop: '1px solid var(--border-color)', textAlign: 'center' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Are you a security analyst or administrator?{' '}
              <Link to="/admin/login" style={{ color: 'var(--text-secondary)', fontWeight: 600, textDecoration: 'none' }}>
                Admin Portal &rarr;
              </Link>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
