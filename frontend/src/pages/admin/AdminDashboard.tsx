import React, { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { apiRequest } from '../../services/api';
import { Cpu, Users, ShieldAlert, FileText } from 'lucide-react';

interface AdminDashboardData {
  admin: {
    id: string;
    email: string;
    full_name: string;
    role: string;
    access_level: string;
  };
  system_metrics: {
    total_customers: number;
    total_admins: number;
    ml_engine_status: string;
    auth_guard: string;
  };
  recent_audit_logs: Array<{
    id: string;
    action: string;
    details: string;
    created_at: string;
    user_id: string;
  }>;
}

interface TransactionFeed {
  id: string;
  sender_name: string;
  recipient_name: string;
  amount: number;
  fraud_probability: number | null;
  decision: string | null;
  status: string;
  timestamp: string;
}

export const AdminDashboard: React.FC = () => {
  const { user } = useAuth();
  const [data, setData] = useState<AdminDashboardData | null>(null);
  const [transactions, setTransactions] = useState<TransactionFeed[]>([]);
  const [feedError, setFeedError] = useState('');

  useEffect(() => {
    apiRequest<AdminDashboardData>('/api/admin/dashboard')
      .then(setData)
      .catch((err) => console.error("Error loading admin dashboard:", err));
    apiRequest<{ transactions: TransactionFeed[] }>('/api/admin/transactions')
      .then((feed) => setTransactions(feed.transactions))
      .catch((err) => setFeedError(err instanceof Error ? err.message : 'Unable to load transaction feed.'));
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
      {/* Header Banner */}
      <div style={{
        backgroundColor: 'var(--bg-card)',
        borderRadius: 'var(--radius-sm)',
        padding: '24px 28px',
        border: '1px solid var(--border-color)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--primary)', display: 'inline-block' }} />
            <span style={{ fontSize: '11px', color: 'var(--primary)', letterSpacing: '1px', textTransform: 'uppercase', fontWeight: 700, fontFamily: 'monospace' }}>
              SECURITY COMMAND STATION
            </span>
          </div>
          <h1 style={{ fontSize: '24px', fontWeight: 800, color: 'var(--text-primary)', margin: 0 }}>
            Fraud Monitoring & Access Management
          </h1>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Administrator: {user?.full_name} ({user?.email}) &bull; Role: ADMIN
          </p>
        </div>

        <div style={{
          display: 'flex',
          gap: '12px'
        }}>
          <div style={{
            padding: '10px 16px',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'var(--bg-card-subtle)',
            border: '1px solid var(--border-color)',
            textAlign: 'right'
          }}>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              ACTIVE GUARD
            </div>
            <div style={{ fontSize: '13px', fontWeight: 700, color: '#10B981', fontFamily: 'monospace' }}>
              ENFORCING RBAC
            </div>
          </div>
        </div>
      </div>

      {/* Metric Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
        gap: '20px'
      }}>
        {/* ML Engine Status */}
        <div style={{
          backgroundColor: 'var(--bg-card)',
          borderRadius: 'var(--radius-sm)',
          padding: '22px',
          border: '1px solid var(--border-color)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              LightGBM Inference Engine
            </span>
            <Cpu size={18} color="var(--primary)" />
          </div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '6px' }}>
            Ready & Calibrated
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
            22 Features &bull; Isotonic Probability
          </div>
        </div>

        {/* Customer Accounts */}
        <div style={{
          backgroundColor: 'var(--bg-card)',
          borderRadius: 'var(--radius-sm)',
          padding: '22px',
          border: '1px solid var(--border-color)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Registered Customers
            </span>
            <Users size={18} color="var(--primary)" />
          </div>
          <div style={{ fontSize: '26px', fontWeight: 800, color: 'var(--text-primary)', marginBottom: '6px' }}>
            {data?.system_metrics.total_customers ?? 0}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            Active customer identities
          </div>
        </div>

        {/* Security Operators */}
        <div style={{
          backgroundColor: 'var(--bg-card)',
          borderRadius: 'var(--radius-sm)',
          padding: '22px',
          border: '1px solid var(--border-color)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Admin Operators
            </span>
            <ShieldAlert size={18} color="var(--primary)" />
          </div>
          <div style={{ fontSize: '26px', fontWeight: 800, color: 'var(--text-primary)', marginBottom: '6px' }}>
            {data?.system_metrics.total_admins ?? 1}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            Provisioned via CLI bootstrap
          </div>
        </div>
      </div>

      {/* Audit Log Table */}
      <div style={{
        backgroundColor: 'var(--bg-card)',
        borderRadius: 'var(--radius-sm)',
        border: '1px solid var(--border-color)',
        overflow: 'hidden'
      }}>
        <div style={{
          padding: '18px 22px',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <FileText size={18} color="var(--primary)" />
            <h2 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
              Live Security & Authorization Audit Records
            </h2>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
            REAL-TIME FEED
          </span>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--bg-card-subtle)', borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '12px 20px', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.6px' }}>Action</th>
                <th style={{ padding: '12px 20px', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.6px' }}>Details</th>
                <th style={{ padding: '12px 20px', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.6px' }}>User ID</th>
                <th style={{ padding: '12px 20px', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.6px' }}>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {data?.recent_audit_logs && data.recent_audit_logs.length > 0 ? (
                data.recent_audit_logs.map((log) => (
                  <tr key={log.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '12px 20px', fontWeight: 700, color: 'var(--primary)', fontFamily: 'monospace' }}>
                      {log.action}
                    </td>
                    <td style={{ padding: '12px 20px', color: 'var(--text-primary)' }}>
                      {log.details}
                    </td>
                    <td style={{ padding: '12px 20px', color: 'var(--text-secondary)', fontFamily: 'monospace', fontSize: '12px' }}>
                      {log.user_id || 'System'}
                    </td>
                    <td style={{ padding: '12px 20px', color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: '12px' }}>
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No audit records recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Persisted transaction monitoring feed */}
      <div style={{
        backgroundColor: 'var(--bg-card)',
        borderRadius: 'var(--radius-sm)',
        border: '1px solid var(--border-color)',
        overflow: 'hidden'
      }}>
        <div style={{
          padding: '18px 22px',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <h2 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
            Live Transaction Monitoring
          </h2>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
            PERSISTED DATABASE FEED
          </span>
        </div>
        {feedError && <div style={{ padding: '16px 22px', color: '#FCA5A5', fontSize: '13px' }}>{feedError}</div>}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--bg-card-subtle)', borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '12px 20px', fontSize: '11px', textTransform: 'uppercase' }}>Transaction</th>
                <th style={{ padding: '12px 20px', fontSize: '11px', textTransform: 'uppercase' }}>Sender / Recipient</th>
                <th style={{ padding: '12px 20px', fontSize: '11px', textTransform: 'uppercase' }}>Amount</th>
                <th style={{ padding: '12px 20px', fontSize: '11px', textTransform: 'uppercase' }}>Fraud Probability</th>
                <th style={{ padding: '12px 20px', fontSize: '11px', textTransform: 'uppercase' }}>Decision</th>
                <th style={{ padding: '12px 20px', fontSize: '11px', textTransform: 'uppercase' }}>Status</th>
                <th style={{ padding: '12px 20px', fontSize: '11px', textTransform: 'uppercase' }}>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((transaction) => (
                <tr key={transaction.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '12px 20px', color: 'var(--primary)', fontFamily: 'monospace', fontSize: '12px' }}>{transaction.id}</td>
                  <td style={{ padding: '12px 20px', color: 'var(--text-primary)' }}>
                    {transaction.sender_name} &rarr; {transaction.recipient_name}
                  </td>
                  <td style={{ padding: '12px 20px', color: 'var(--text-primary)', fontWeight: 700 }}>
                    ${transaction.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </td>
                  <td style={{ padding: '12px 20px', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                    {transaction.fraud_probability == null ? 'Unavailable' : `${(transaction.fraud_probability * 100).toFixed(2)}%`}
                  </td>
                  <td style={{ padding: '12px 20px', color: 'var(--text-primary)', fontFamily: 'monospace' }}>
                    {transaction.decision || 'N/A'}
                  </td>
                  <td style={{ padding: '12px 20px', color: 'var(--text-secondary)' }}>
                    {transaction.status.replaceAll('_', ' ')}
                  </td>
                  <td style={{ padding: '12px 20px', color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: '12px' }}>
                    {new Date(transaction.timestamp).toLocaleString()}
                  </td>
                </tr>
              ))}
              {!transactions.length && !feedError && (
                <tr>
                  <td colSpan={7} style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No persisted transactions recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
