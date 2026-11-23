import React from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ShieldCheck, LogOut, LayoutDashboard, CreditCard, Lock } from 'lucide-react';

export const CustomerLayout: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="theme-customer" style={{
      minHeight: '100vh',
      display: 'flex',
      backgroundColor: 'var(--bg-page)',
      color: 'var(--text-primary)',
      fontFamily: 'inherit'
    }}>
      {/* Sidebar Navigation */}
      <aside style={{
        width: '260px',
        backgroundColor: 'var(--bg-card)',
        borderRight: '1px solid var(--border-color)',
        display: 'flex',
        flexDirection: 'column',
        padding: '24px 20px',
        boxShadow: 'var(--shadow-sm)'
      }}>
        {/* Brand identity */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '36px' }}>
          <div style={{
            width: '42px',
            height: '42px',
            backgroundColor: 'var(--text-primary)',
            borderRadius: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent)',
            boxShadow: '0 4px 10px rgba(22, 78, 99, 0.2)'
          }}>
            <ShieldCheck size={26} strokeWidth={2.2} />
          </div>
          <div>
            <h1 style={{ fontSize: '18px', fontWeight: 800, letterSpacing: '-0.4px', color: 'var(--text-primary)', margin: 0 }}>
              FraudGuard
            </h1>
            <span style={{ fontSize: '11px', fontWeight: 600, color: '#047857', letterSpacing: '0.6px', textTransform: 'uppercase' }}>
              Premier Banking
            </span>
          </div>
        </div>

        {/* Navigation links */}
        <nav style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <button
            onClick={() => navigate('/customer')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '12px 14px',
              borderRadius: 'var(--radius-sm)',
              border: 'none',
              backgroundColor: location.pathname === '/customer' ? 'var(--bg-card-subtle)' : 'transparent',
              color: location.pathname === '/customer' ? 'var(--text-primary)' : 'var(--text-secondary)',
              fontWeight: location.pathname === '/customer' ? 700 : 500,
              fontSize: '14px',
              textAlign: 'left',
              width: '100%'
            }}
          >
            <LayoutDashboard size={18} />
            Account Overview
          </button>

          <button
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '12px 14px',
              borderRadius: 'var(--radius-sm)',
              border: 'none',
              backgroundColor: 'transparent',
              color: 'var(--text-secondary)',
              fontWeight: 500,
              fontSize: '14px',
              textAlign: 'left',
              width: '100%',
              opacity: 0.8
            }}
            onClick={() => alert("Transfers & Transactions will be integrated in Phase 2.")}
          >
            <CreditCard size={18} />
            Transfers & Activity
          </button>

          <button
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '12px 14px',
              borderRadius: 'var(--radius-sm)',
              border: 'none',
              backgroundColor: 'transparent',
              color: 'var(--text-secondary)',
              fontWeight: 500,
              fontSize: '14px',
              textAlign: 'left',
              width: '100%',
              opacity: 0.8
            }}
            onClick={() => alert("Security preferences are managed automatically by AI Guard.")}
          >
            <Lock size={18} />
            Security & Controls
          </button>
        </nav>

        {/* User Card & Logout */}
        <div style={{
          borderTop: '1px solid var(--border-color)',
          paddingTop: '20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '38px',
              height: '38px',
              borderRadius: '50%',
              backgroundColor: 'var(--accent)',
              color: 'var(--text-primary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
              fontSize: '14px'
            }}>
              {user?.full_name?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div style={{ overflow: 'hidden' }}>
              <div style={{ fontSize: '13px', fontWeight: 700, whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                {user?.full_name}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                {user?.email}
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
              padding: '10px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-card-subtle)',
              color: 'var(--text-primary)',
              fontWeight: 600,
              fontSize: '13px'
            }}
          >
            <LogOut size={16} />
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
        {/* Top Header */}
        <header style={{
          height: '68px',
          backgroundColor: 'var(--bg-card)',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 32px'
        }}>
          <div>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.8px', fontWeight: 600 }}>
              Customer Portal
            </span>
            <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)' }}>
              Protected Financial Environment
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '20px',
              backgroundColor: 'var(--bg-card-subtle)',
              border: '1px solid var(--border-color)',
              fontSize: '12px',
              fontWeight: 600,
              color: '#065F46'
            }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#10B981', display: 'inline-block' }} />
              FraudGuard AI Shield Active
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main style={{ padding: '36px', maxWidth: '1200px', width: '100%', margin: '0 auto' }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};
