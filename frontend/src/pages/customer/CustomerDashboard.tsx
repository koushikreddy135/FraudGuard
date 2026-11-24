import React, { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { apiRequest } from '../../services/api';
import { ShieldCheck, ArrowUpRight, ArrowDownLeft, Lock, CheckCircle2 } from 'lucide-react';

interface CustomerDashboardData {
  status: string;
  user: {
    id: string;
    email: string;
    full_name: string;
    account_tier: string;
    security_status: string;
    last_login: string;
    account: {
      id: string;
      balance: number;
      balance_cents: number;
      currency: string;
      simulated: boolean;
    };
  };
  notifications: Array<{
    id: string;
    title: string;
    message: string;
    type: string;
  }>;
}

export const CustomerDashboard: React.FC = () => {
  const { user } = useAuth();
  const [_data, setData] = useState<CustomerDashboardData | null>(null);

  useEffect(() => {
    apiRequest<CustomerDashboardData>('/api/customer/dashboard')
      .then(setData)
      .catch((err) => console.error("Error loading customer overview:", err));
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '30px' }}>
      {/* Welcome Banner */}
      <div style={{
        backgroundColor: '#FFFFFF',
        borderRadius: 'var(--radius-md)',
        padding: '30px',
        border: '1px solid var(--border-color)',
        boxShadow: 'var(--shadow-sm)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)' }}>
            Welcome back,
          </span>
          <h1 style={{ fontSize: '28px', fontWeight: 800, color: 'var(--text-primary)', marginTop: '4px' }}>
            {user?.full_name || 'Valued Customer'}
          </h1>
          <p style={{ fontSize: '14px', color: 'var(--text-muted)', marginTop: '4px' }}>
            FraudGuard AI Active Protection &bull; Account #{user?.id?.substring(0, 8)}
          </p>
        </div>

        <div style={{
          padding: '14px 20px',
          borderRadius: 'var(--radius-sm)',
          backgroundColor: 'var(--bg-card-subtle)',
          border: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          gap: '12px'
        }}>
          <div style={{
            width: '40px',
            height: '40px',
            borderRadius: '50%',
            backgroundColor: 'var(--accent)',
            color: 'var(--primary)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <ShieldCheck size={24} />
          </div>
          <div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-primary)' }}>
              Risk Level: Low
            </div>
            <div style={{ fontSize: '11px', color: '#047857', fontWeight: 600 }}>
              Zero suspicious flags
            </div>
          </div>
        </div>
      </div>

      {/* Account Overview Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: '24px'
      }}>
        {/* Balance Card */}
        <div style={{
          backgroundColor: '#FFFFFF',
          borderRadius: 'var(--radius-md)',
          padding: '26px',
          border: '1px solid var(--border-color)',
          boxShadow: 'var(--shadow-sm)'
        }}>
          <div style={{ fontSize: '13px', color: 'var(--text-muted)', fontWeight: 600, marginBottom: '8px' }}>
            Protected Balance
          </div>
          <div style={{ fontSize: '34px', fontWeight: 800, color: 'var(--text-primary)', marginBottom: '16px' }}>
            {_data?.user.account
              ? `$${_data.user.account.balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : 'Loading...'}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '10px' }}>
            Simulated funds
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              onClick={() => window.location.assign('/customer/transfers')}
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                padding: '10px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'var(--primary)',
                color: '#FFFFFF',
                border: 'none',
                fontWeight: 600,
                fontSize: '13px'
              }}
            >
              <ArrowUpRight size={16} /> Send Money
            </button>
            <button
              disabled
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                padding: '10px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'var(--bg-card-subtle)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-color)',
                fontWeight: 600,
                fontSize: '13px'
              }}
            >
              <ArrowDownLeft size={16} /> Add Funds
            </button>
          </div>
        </div>

        {/* Security Status Card */}
        <div style={{
          backgroundColor: '#FFFFFF',
          borderRadius: 'var(--radius-md)',
          padding: '26px',
          border: '1px solid var(--border-color)',
          boxShadow: 'var(--shadow-sm)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', fontWeight: 600 }}>
              Security Protocol
            </div>
            <span style={{
              fontSize: '11px',
              padding: '3px 8px',
              borderRadius: '12px',
              backgroundColor: '#ECFDF5',
              color: '#065F46',
              fontWeight: 700
            }}>
              Active
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '13px' }}>
              <CheckCircle2 size={16} color="#047857" />
              <span>Multi-Factor OTP Challenge Ready</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '13px' }}>
              <CheckCircle2 size={16} color="#047857" />
              <span>LightGBM Behavioral Feature Extraction</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '13px' }}>
              <CheckCircle2 size={16} color="#047857" />
              <span>Isotonic Calibration Policy Active</span>
            </div>
          </div>
        </div>
      </div>

      {/* Security Notices / Activity Feed */}
      <div style={{
        backgroundColor: '#FFFFFF',
        borderRadius: 'var(--radius-md)',
        padding: '26px',
        border: '1px solid var(--border-color)',
        boxShadow: 'var(--shadow-sm)'
      }}>
        <h2 style={{ fontSize: '17px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '16px' }}>
          Recent Security Transmissions
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 16px',
            backgroundColor: 'var(--bg-card-subtle)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-color)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <ShieldCheck size={20} color="#164E63" />
              <div>
                <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Session Authenticated Successfully
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  Authenticated with JWT standard bearer token &bull; Session IP verified
                </div>
              </div>
            </div>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Just now</span>
          </div>

          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 16px',
            backgroundColor: 'var(--bg-card-subtle)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-color)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <Lock size={20} color="#164E63" />
              <div>
                <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Outbound Transfer Guard Engaged
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  Model Version v20261120-100346 monitoring accounts
                </div>
              </div>
            </div>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Today</span>
          </div>
        </div>
      </div>
    </div>
  );
};
