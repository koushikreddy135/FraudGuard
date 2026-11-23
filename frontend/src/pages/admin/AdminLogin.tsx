import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { apiRequest, type AuthResponse } from '../../services/api';
import { ShieldAlert, Eye, EyeOff, Lock, Mail, ArrowRight, AlertCircle, Terminal, Key } from 'lucide-react';

export const AdminLogin: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { login } = useAuth();
  const navigate = useNavigate();

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
          portal_type: 'ADMIN'
        })
      });

      login(data.access_token, data.user);
      navigate('/admin');
    } catch (err: any) {
      setError(err.message || 'Administrative authentication failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="theme-admin" style={{
      minHeight: '100vh',
      display: 'flex',
      backgroundColor: 'var(--bg-page)',
      color: 'var(--text-primary)',
      fontFamily: 'inherit'
    }}>
      {/* Visual branding banner for security ops */}
      <div style={{
        flex: 1,
        backgroundColor: '#07090C',
        borderRight: '1px solid var(--border-color)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        padding: '60px',
        position: 'relative',
        overflow: 'hidden'
      }}>
        {/* Dark subtle grid / glow effect */}
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundImage: 'radial-gradient(rgba(8, 188, 235, 0.08) 1px, transparent 1px)',
          backgroundSize: '24px 24px',
          pointerEvents: 'none'
        }} />

        <div style={{
          position: 'absolute',
          top: '20%',
          right: '-5%',
          width: '450px',
          height: '450px',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(8, 188, 235, 0.12) 0%, rgba(7, 9, 12, 0) 70%)',
          pointerEvents: 'none'
        }} />

        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', zIndex: 1 }}>
          <div style={{
            width: '44px',
            height: '44px',
            backgroundColor: '#18232C',
            border: '1px solid #243542',
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#08BCEB',
            boxShadow: '0 0 16px rgba(8, 188, 235, 0.25)'
          }}>
            <ShieldAlert size={26} />
          </div>
          <div>
            <h2 style={{ fontSize: '20px', fontWeight: 800, margin: 0, letterSpacing: '-0.3px', color: '#F5FAFC' }}>FraudGuard</h2>
            <p style={{ margin: 0, fontSize: '11px', color: '#08BCEB', letterSpacing: '1px', textTransform: 'uppercase', fontWeight: 700 }}>
              Security Operations Center
            </p>
          </div>
        </div>

        <div style={{ maxWidth: '500px', zIndex: 1 }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '5px 12px',
            backgroundColor: 'rgba(8, 188, 235, 0.1)',
            border: '1px solid rgba(8, 188, 235, 0.3)',
            color: '#08BCEB',
            borderRadius: '6px',
            fontSize: '11px',
            fontWeight: 700,
            letterSpacing: '0.6px',
            marginBottom: '20px'
          }}>
            <Terminal size={14} />
            RESTRICTED ADMIN PROTOCOL
          </div>
          <h1 style={{ fontSize: '34px', fontWeight: 800, lineHeight: 1.25, marginBottom: '18px', color: '#F5FAFC', letterSpacing: '-0.5px' }}>
            Financial Risk Intelligence & Real-time Defense.
          </h1>
          <p style={{ fontSize: '15px', color: '#94A3B8', lineHeight: 1.6 }}>
            Authorized fraud analysts and platform engineers only. Direct access to decision policy engines, LightGBM model retraining gates, and system audit logs.
          </p>
        </div>

        <div style={{ fontSize: '12px', color: '#64748B', zIndex: 1, fontFamily: 'monospace' }}>
          SESSION_MONITOR: ACTIVE // ENCRYPTION: AES-256-GCM / SHA-256
        </div>
      </div>

      {/* Admin Login Panel */}
      <div style={{
        width: '520px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        padding: '60px 48px',
        backgroundColor: '#18232C'
      }}>
        <div style={{ maxWidth: '380px', width: '100%', margin: '0 auto' }}>
          <div style={{ marginBottom: '32px' }}>
            <h2 style={{ fontSize: '24px', fontWeight: 800, color: 'var(--text-primary)', marginBottom: '8px' }}>
              Admin Sign In
            </h2>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              Enter administrator credentials to authenticate your operational session.
            </p>
          </div>

          {error && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '12px 14px',
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid #EF4444',
              borderRadius: 'var(--radius-sm)',
              color: '#F87171',
              fontSize: '13px',
              marginBottom: '24px'
            }}>
              <AlertCircle size={18} style={{ flexShrink: 0 }} />
              <div>{error}</div>
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '6px', letterSpacing: '0.4px', textTransform: 'uppercase' }}>
                Admin Email
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  type="email"
                  required
                  placeholder="admin@fraudguard.local"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '12px 14px 12px 38px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--bg-card-subtle)',
                    color: 'var(--text-primary)',
                    fontSize: '14px',
                    outline: 'none',
                    fontFamily: 'monospace'
                  }}
                />
                <Mail size={16} style={{ position: 'absolute', left: '12px', top: '14px', color: 'var(--text-muted)' }} />
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <label style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-secondary)', letterSpacing: '0.4px', textTransform: 'uppercase' }}>
                  Master Password
                </label>
                <Link to="/forgot-password" style={{ fontSize: '12px', color: 'var(--primary)', textDecoration: 'none', fontWeight: 600 }}>
                  Reset key?
                </Link>
              </div>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '12px 38px 12px 38px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--bg-card-subtle)',
                    color: 'var(--text-primary)',
                    fontSize: '14px',
                    outline: 'none'
                  }}
                />
                <Lock size={16} style={{ position: 'absolute', left: '12px', top: '14px', color: 'var(--text-muted)' }} />
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
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
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
                padding: '12px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'var(--primary)',
                color: '#07090C',
                border: 'none',
                fontWeight: 800,
                fontSize: '13px',
                letterSpacing: '0.5px',
                marginTop: '10px',
                opacity: loading ? 0.7 : 1,
                boxShadow: '0 0 15px rgba(8, 188, 235, 0.4)'
              }}
            >
              {loading ? 'Validating Privileges...' : 'Authorize Operator Session'}
              {!loading && <ArrowRight size={16} />}
            </button>
          </form>

          <div style={{
            marginTop: '32px',
            padding: '16px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-color)',
            backgroundColor: 'var(--bg-card-subtle)',
            fontSize: '12px',
            color: 'var(--text-muted)',
            lineHeight: 1.5
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--primary)', fontWeight: 700, marginBottom: '6px' }}>
              <Key size={14} /> Provisioning Notice
            </div>
            Public admin registration is strictly disabled. Use the protected CLI bootstrap tool <code>python -m backend.bootstrap_admin</code> to provision authorized security operators.
          </div>

          <div style={{ marginTop: '24px', textAlign: 'center' }}>
            <Link to="/login" style={{ fontSize: '12px', color: 'var(--text-secondary)', textDecoration: 'none' }}>
              &larr; Switch to Customer Portal
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};
