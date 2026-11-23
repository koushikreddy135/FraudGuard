import React from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ShieldAlert, LogOut, Terminal, Activity, FileText, Cpu } from 'lucide-react';

export const AdminLayout: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => {
    await logout();
    navigate('/admin/login');
  };

  return (
    <div className="theme-admin" style={{
      minHeight: '100vh',
      display: 'flex',
      backgroundColor: 'var(--bg-page)',
      color: 'var(--text-primary)',
      fontFamily: 'inherit'
    }}>
      {/* Dark Sidebar Navigation */}
      <aside style={{
        width: '270px',
        backgroundColor: 'var(--bg-card)',
        borderRight: '1px solid var(--border-color)',
        display: 'flex',
        flexDirection: 'column',
        padding: '24px 18px',
        boxShadow: 'var(--shadow-md)'
      }}>
        {/* Brand identity */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '36px' }}>
          <div style={{
            width: '42px',
            height: '42px',
            backgroundColor: 'var(--bg-card-subtle)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--primary)',
            boxShadow: '0 0 15px rgba(8, 188, 235, 0.2)'
          }}>
            <ShieldAlert size={24} strokeWidth={2.4} />
          </div>
          <div>
            <h1 style={{ fontSize: '17px', fontWeight: 800, letterSpacing: '-0.3px', color: 'var(--text-primary)', margin: 0 }}>
              FraudGuard
            </h1>
            <span style={{ fontSize: '10px', fontWeight: 700, color: 'var(--primary)', letterSpacing: '1px', textTransform: 'uppercase' }}>
              Security Ops & ML
            </span>
          </div>
        </div>

        {/* Navigation links */}
        <nav style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <button
            onClick={() => navigate('/admin')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '11px 14px',
              borderRadius: 'var(--radius-sm)',
              border: location.pathname === '/admin' ? '1px solid rgba(8, 188, 235, 0.4)' : '1px solid transparent',
              backgroundColor: location.pathname === '/admin' ? 'var(--accent-soft)' : 'transparent',
              color: location.pathname === '/admin' ? 'var(--primary)' : 'var(--text-secondary)',
              fontWeight: 600,
              fontSize: '13px',
              textAlign: 'left',
              width: '100%'
            }}
          >
            <Activity size={17} />
            Security Overview
          </button>

          <button
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '11px 14px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid transparent',
              backgroundColor: 'transparent',
              color: 'var(--text-secondary)',
              fontWeight: 500,
              fontSize: '13px',
              textAlign: 'left',
              width: '100%',
              opacity: 0.7
            }}
            onClick={() => alert("Model Ops & Re-training Gate will be integrated in Phase 2.")}
          >
            <Cpu size={17} />
            Model Ops & Health
          </button>

          <button
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '11px 14px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid transparent',
              backgroundColor: 'transparent',
              color: 'var(--text-secondary)',
              fontWeight: 500,
              fontSize: '13px',
              textAlign: 'left',
              width: '100%',
              opacity: 0.7
            }}
            onClick={() => alert("Fraud Investigation Queue will be integrated in Phase 2.")}
          >
            <Terminal size={17} />
            Investigation Queue
          </button>

          <button
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '11px 14px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid transparent',
              backgroundColor: 'transparent',
              color: 'var(--text-secondary)',
              fontWeight: 500,
              fontSize: '13px',
              textAlign: 'left',
              width: '100%',
              opacity: 0.7
            }}
            onClick={() => alert("Audit Logs table is displayed on the main security overview.")}
          >
            <FileText size={17} />
            Audit Records
          </button>
        </nav>

        {/* Admin User Card & Logout */}
        <div style={{
          borderTop: '1px solid var(--border-color)',
          paddingTop: '18px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '36px',
              height: '36px',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: 'var(--bg-card-subtle)',
              border: '1px solid var(--border-color)',
              color: 'var(--primary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
              fontSize: '13px'
            }}>
              {user?.full_name?.charAt(0).toUpperCase() || 'A'}
            </div>
            <div style={{ overflow: 'hidden' }}>
              <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                {user?.full_name}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--primary)', fontWeight: 600, letterSpacing: '0.4px' }}>
                SECURITY ADMIN
              </div>
            </div>
          </div>

          <button
            onClick={handleLogout}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              padding: '9px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-card-subtle)',
              color: '#EF4444',
              fontWeight: 600,
              fontSize: '12px'
            }}
          >
            <LogOut size={15} />
            Terminate Admin Session
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
        {/* Top Header */}
        <header style={{
          height: '64px',
          backgroundColor: 'var(--bg-card)',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 32px'
        }}>
          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: 700 }}>
              Fraud Operations Command
            </span>
            <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)' }}>
              Restricted Administrative Domain
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '6px 14px',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: 'var(--bg-card-subtle)',
              border: '1px solid var(--border-color)',
              fontSize: '12px',
              fontFamily: 'monospace',
              color: 'var(--primary)'
            }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--primary)', display: 'inline-block', boxShadow: '0 0 8px #08BCEB' }} />
              ML INFERENCE ENGINE: ONLINE
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main style={{ padding: '32px', maxWidth: '1350px', width: '100%', margin: '0 auto' }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};
