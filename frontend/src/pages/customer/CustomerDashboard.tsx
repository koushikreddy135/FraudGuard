import React, { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { apiRequest } from '../../services/api';
import { ShieldCheck, ArrowUpRight, ArrowDownLeft, Lock, CheckCircle2, X } from 'lucide-react';

interface CustomerDashboardData {
  status: string;
  user: {
    id: string;
    email: string;
    full_name: string;
    security_status: string;
    last_login: string | null;
    account: {
      id: string;
      balance: number;
      balance_cents: number;
      currency: string;
      simulated: boolean;
    };
  };
  model_status: { available: boolean; model_version: string | null };
  recent_activity: Array<{ id: string; decision: string | null; status: string }>;
}

export const CustomerDashboard: React.FC = () => {
  const { user } = useAuth();
  const [_data, setData] = useState<CustomerDashboardData | null>(null);
  const [showAddFunds, setShowAddFunds] = useState(false);
  const [fundAmount, setFundAmount] = useState('500');
  const [funding, setFunding] = useState(false);
  const [fundError, setFundError] = useState<string | null>(null);
  const [fundSuccess, setFundSuccess] = useState<string | null>(null);

  const fetchDashboardData = () => {
    apiRequest<CustomerDashboardData>('/api/customer/dashboard')
      .then(setData)
      .catch((err) => console.error("Error loading customer overview:", err));
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const handleAddFundsSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFundError(null);
    setFundSuccess(null);
    const parsed = parseFloat(fundAmount);
    if (isNaN(parsed) || parsed <= 0) {
      setFundError('Please enter a valid amount greater than $0.');
      return;
    }
    setFunding(true);
    try {
      const res = await apiRequest<{ success: boolean; new_balance: number; amount: number }>(
        '/api/customer/add-funds',
        {
          method: 'POST',
          body: JSON.stringify({ amount: parsed }),
        }
      );
      setFundSuccess(`Successfully added $${res.amount.toFixed(2)} to your balance!`);
      fetchDashboardData();
      setTimeout(() => {
        setShowAddFunds(false);
        setFundSuccess(null);
      }, 1500);
    } catch (err: any) {
      setFundError(err?.message || 'Failed to add funds.');
    } finally {
      setFunding(false);
    }
  };

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
              Fraud scoring: {_data?.model_status.available ? 'Available' : 'Unavailable'}
            </div>
            <div style={{ fontSize: '11px', color: '#047857', fontWeight: 600 }}>
              {_data?.recent_activity.length ?? 0} recent transactions
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
                fontSize: '13px',
                cursor: 'pointer'
              }}
            >
              <ArrowUpRight size={16} /> Send Money
            </button>
            <button
              onClick={() => {
                setFundError(null);
                setFundSuccess(null);
                setShowAddFunds(true);
              }}
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
                fontSize: '13px',
                cursor: 'pointer'
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
                  Last successful login: {_data?.user.last_login ? new Date(_data.user.last_login).toLocaleString() : 'No login record'}
                </div>
              </div>
            </div>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Account security</span>
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
                  Outbound Transfer Scoring
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  {_data?.model_status.available ? `Model ${_data.model_status.model_version} is ready` : 'Model unavailable; transfers cannot be scored'}
                </div>
              </div>
            </div>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{_data?.model_status.available ? 'Ready' : 'Unavailable'}</span>
          </div>
        </div>
      </div>

      {/* Add Funds Modal */}
      {showAddFunds && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 999
        }}>
          <div style={{
            backgroundColor: '#FFFFFF',
            borderRadius: 'var(--radius-md)',
            padding: '24px',
            width: '100%',
            maxWidth: '420px',
            border: '1px solid var(--border-color)',
            boxShadow: 'var(--shadow-lg, 0 10px 15px -3px rgba(0,0,0,0.1))'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ArrowDownLeft size={20} color="var(--primary)" />
                <h3 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                  Add Funds (Simulated)
                </h3>
              </div>
              <button
                onClick={() => setShowAddFunds(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
              >
                <X size={20} />
              </button>
            </div>

            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px', lineHeight: 1.4 }}>
              Top up your simulated checking account to test transfers and fraud scoring capabilities.
            </p>

            {fundError && (
              <div style={{
                padding: '10px 12px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: '#FEF2F2',
                color: '#B91C1C',
                fontSize: '13px',
                marginBottom: '14px'
              }}>
                {fundError}
              </div>
            )}

            {fundSuccess && (
              <div style={{
                padding: '10px 12px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: '#ECFDF5',
                color: '#065F46',
                fontSize: '13px',
                marginBottom: '14px'
              }}>
                {fundSuccess}
              </div>
            )}

            <form onSubmit={handleAddFundsSubmit}>
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '6px', color: 'var(--text-primary)' }}>
                  Amount ($ USD)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="1"
                  value={fundAmount}
                  onChange={(e) => setFundAmount(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-color)',
                    fontSize: '15px',
                    fontWeight: 600,
                    outline: 'none',
                    boxSizing: 'border-box'
                  }}
                  required
                />
              </div>

              {/* Quick preset buttons */}
              <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
                {['100', '500', '1000', '5000'].map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => setFundAmount(preset)}
                    style={{
                      flex: 1,
                      padding: '6px',
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: fundAmount === preset ? 'var(--accent)' : 'var(--bg-card-subtle)',
                      border: '1px solid var(--border-color)',
                      fontSize: '12px',
                      fontWeight: 600,
                      color: fundAmount === preset ? 'var(--primary)' : 'var(--text-secondary)',
                      cursor: 'pointer'
                    }}
                  >
                    +${preset}
                  </button>
                ))}
              </div>

              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={() => setShowAddFunds(false)}
                  style={{
                    padding: '10px 16px',
                    borderRadius: 'var(--radius-sm)',
                    backgroundColor: 'transparent',
                    border: '1px solid var(--border-color)',
                    color: 'var(--text-secondary)',
                    fontWeight: 600,
                    fontSize: '13px',
                    cursor: 'pointer'
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={funding}
                  style={{
                    padding: '10px 20px',
                    borderRadius: 'var(--radius-sm)',
                    backgroundColor: 'var(--primary)',
                    color: '#FFFFFF',
                    border: 'none',
                    fontWeight: 600,
                    fontSize: '13px',
                    cursor: funding ? 'not-allowed' : 'pointer'
                  }}
                >
                  {funding ? 'Adding...' : 'Confirm Deposit'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
