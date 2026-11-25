import React, { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { apiRequest } from '../../services/api';
import { Cpu, FileText, CheckCircle2, RotateCcw, AlertTriangle, UserCheck, UserX } from 'lucide-react';

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
    total_transactions?: number;
    total_volume?: number;
    approved_count?: number;
    review_count?: number;
    stepup_count?: number;
    declined_count?: number;
    pending_review_count?: number;
    scored_transaction_count?: number;
    avg_fraud_prob?: number;
    avg_latency_ms?: number;
    ml_engine_status: string;
    model_status: { available: boolean; model_version: string | null; feature_count: number; error: string | null };
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
  raw_fraud_probability?: number | null;
  decision: string | null;
  status: string;
  timestamp: string;
  risk_reasons?: string[];
  review_reason?: string | null;
}

interface UserItem {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
  balance: number;
  currency: string;
}

interface ModelOpsData {
  live_version: string;
  model_status: { available: boolean; model_version: string | null; feature_count: number; error: string | null };
  metrics: {
    trees?: number;
    pos_weight?: number;
    train_rows?: number;
    calib_rows?: number;
    test_rows?: number;
    pr_auc?: number;
    brier?: number;
    recall_at_1pct_fpr?: number;
    worst_decile_gap_pp?: number;
    cost?: {
      total?: number;
      per_txn?: number;
    };
  };
  history: Array<{
    timestamp: string;
    candidate_version: string;
    live_version: string;
    promoted: boolean;
    reason: string;
  }>;
}

const formatFraudProbability = (probability: number, rawProbability?: number | null) => {
  const percent = probability * 100;
  if (percent === 0 && rawProbability != null && rawProbability > 0) {
    const rawPercent = rawProbability * 100;
    const rawText = rawPercent < 0.01 ? rawPercent.toPrecision(2) : rawPercent.toFixed(2);
    return `0.00% (raw ${rawText}%)`;
  }
  return `${percent > 0 && percent < 0.01 ? percent.toPrecision(2) : percent.toFixed(2)}%`;
};

export const AdminDashboard: React.FC = () => {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<'overview' | 'investigation' | 'modelops' | 'users'>('overview');
  const [data, setData] = useState<AdminDashboardData | null>(null);
  const [transactions, setTransactions] = useState<TransactionFeed[]>([]);
  const [usersList, setUsersList] = useState<UserItem[]>([]);
  const [modelOps, setModelOps] = useState<ModelOpsData | null>(null);
  const [feedError, setFeedError] = useState('');
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);
  const [rollingBack, setRollingBack] = useState(false);

  const loadData = () => {
    apiRequest<AdminDashboardData>('/api/admin/dashboard')
      .then(setData)
      .catch((err) => console.error("Error loading admin dashboard:", err));
    apiRequest<{ transactions: TransactionFeed[] }>('/api/admin/transactions')
      .then((feed) => setTransactions(feed.transactions))
      .catch((err) => setFeedError(err instanceof Error ? err.message : 'Unable to load transaction feed.'));
    apiRequest<{ users: UserItem[] }>('/api/admin/users')
      .then((res) => setUsersList(res.users))
      .catch(() => {});
    apiRequest<ModelOpsData>('/api/admin/model-ops')
      .then(setModelOps)
      .catch(() => {});
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleReviewAction = async (transactionId: string, action: 'APPROVE' | 'REJECT') => {
    const notes = window.prompt(`Reason for ${action === 'APPROVE' ? 'approval' : 'decline'}:`);
    if (!notes?.trim()) return;
    setProcessingId(transactionId);
    setReviewMessage(null);
    try {
      const res = await apiRequest<{ success: boolean; message: string }>('/api/admin/transactions/review', {
        method: 'POST',
        body: JSON.stringify({ transaction_id: transactionId, action, notes: notes.trim() }),
      });
      setReviewMessage(res.message);
      loadData();
    } catch (err: any) {
      alert(err.message || 'Action failed');
    } finally {
      setProcessingId(null);
    }
  };

  const handleToggleUser = async (userId: string) => {
    try {
      await apiRequest(`/api/admin/users/${userId}/toggle-status`, { method: 'POST' });
      loadData();
    } catch (err: any) {
      alert(err.message || 'Failed to toggle user status');
    }
  };

  const handleRollbackModel = async () => {
    if (!window.confirm("Roll back the live LightGBM model to the previous archived candidate version?")) return;
    setRollingBack(true);
    try {
      const res = await apiRequest<{ success: boolean; message: string }>('/api/admin/model-ops/rollback', { method: 'POST' });
      alert(res.message);
      loadData();
    } catch (err: any) {
      alert(err.message || 'Rollback failed.');
    } finally {
      setRollingBack(false);
    }
  };

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

      {/* Navigation Tabs */}
      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px' }}>
        {[
          { key: 'overview', label: 'Live Monitoring' },
          { key: 'investigation', label: 'Suspicious / Investigation Queue' },
          { key: 'modelops', label: 'Model Ops & Retrain Registry' },
          { key: 'users', label: 'Customer Accounts' },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key as any)}
            style={{
              padding: '8px 16px',
              borderRadius: 'var(--radius-sm)',
              border: activeTab === tab.key ? '1px solid var(--primary)' : '1px solid transparent',
              backgroundColor: activeTab === tab.key ? 'var(--accent-soft)' : 'transparent',
              color: activeTab === tab.key ? 'var(--primary)' : 'var(--text-secondary)',
              fontWeight: 700,
              fontSize: '13px',
              cursor: 'pointer'
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Metric Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '16px'
      }}>
        <div style={{ backgroundColor: 'var(--bg-card)', borderRadius: 'var(--radius-sm)', padding: '20px', border: '1px solid var(--border-color)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase' }}>Total Volume</span>
            <span style={{ fontSize: '12px', color: '#10B981', fontWeight: 700 }}>${(data?.system_metrics.total_volume ?? 0).toLocaleString()}</span>
          </div>
          <div style={{ fontSize: '24px', fontWeight: 800, color: 'var(--text-primary)' }}>
            {data ? data.system_metrics.total_transactions ?? transactions.length : '—'} txns
          </div>
        </div>

        <div style={{ backgroundColor: 'var(--bg-card)', borderRadius: 'var(--radius-sm)', padding: '20px', border: '1px solid var(--border-color)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase' }}>Pending analyst reviews</span>
            <AlertTriangle size={16} color="#F59E0B" />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 800, color: '#F59E0B' }}>
            {data?.system_metrics.pending_review_count ?? '—'}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Awaiting an analyst decision
          </div>
        </div>

        <div style={{ backgroundColor: 'var(--bg-card)', borderRadius: 'var(--radius-sm)', padding: '20px', border: '1px solid var(--border-color)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase' }}>Avg Latency</span>
            <Cpu size={16} color="var(--primary)" />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 800, color: 'var(--primary)' }}>
            {data?.system_metrics.avg_latency_ms ?? '—'} ms
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Real-time inference speed
          </div>
        </div>

        <div style={{ backgroundColor: 'var(--bg-card)', borderRadius: 'var(--radius-sm)', padding: '20px', border: '1px solid var(--border-color)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase' }}>Model Version</span>
            <CheckCircle2 size={16} color="#10B981" />
          </div>
          <div style={{ fontSize: '16px', fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'monospace' }}>
            {data?.system_metrics.model_status.model_version || 'Unavailable'}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Active LightGBM tree booster
          </div>
        </div>
      </div>

      {/* Tab: Users Management */}
      {activeTab === 'users' && (
        <div style={{ backgroundColor: 'var(--bg-card)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', overflow: 'hidden' }}>
          <div style={{ padding: '18px 22px', borderBottom: '1px solid var(--border-color)' }}>
            <h2 style={{ fontSize: '15px', fontWeight: 700, margin: 0 }}>Registered Customer Directory & Access Control</h2>
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--bg-card-subtle)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '12px 20px', textAlign: 'left' }}>User</th>
                <th style={{ padding: '12px 20px', textAlign: 'left' }}>Email</th>
                <th style={{ padding: '12px 20px', textAlign: 'left' }}>Role</th>
                <th style={{ padding: '12px 20px', textAlign: 'left' }}>Simulated Balance</th>
                <th style={{ padding: '12px 20px', textAlign: 'left' }}>Status</th>
                <th style={{ padding: '12px 20px', textAlign: 'left' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {usersList.map((u) => (
                <tr key={u.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '12px 20px', fontWeight: 700 }}>{u.full_name}</td>
                  <td style={{ padding: '12px 20px', color: 'var(--text-secondary)' }}>{u.email}</td>
                  <td style={{ padding: '12px 20px', fontFamily: 'monospace' }}>{u.role}</td>
                  <td style={{ padding: '12px 20px', fontWeight: 700 }}>${u.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                  <td style={{ padding: '12px 20px' }}>
                    <span style={{
                      padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 700,
                      backgroundColor: u.is_active ? '#ECFDF5' : '#FEF2F2',
                      color: u.is_active ? '#065F46' : '#B91C1C'
                    }}>
                      {u.is_active ? 'ACTIVE' : 'LOCKED'}
                    </span>
                  </td>
                  <td style={{ padding: '12px 20px' }}>
                    {u.role === 'CUSTOMER' && (
                      <button
                        onClick={() => handleToggleUser(u.id)}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 12px',
                          borderRadius: 'var(--radius-sm)', border: 'none',
                          backgroundColor: u.is_active ? '#EF4444' : '#10B981', color: '#fff',
                          fontSize: '11px', fontWeight: 700, cursor: 'pointer'
                        }}
                      >
                        {u.is_active ? <UserX size={13} /> : <UserCheck size={13} />}
                        {u.is_active ? 'Lock Account' : 'Activate Account'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab: Model Ops & Registry */}
      {activeTab === 'modelops' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div style={{ backgroundColor: 'var(--bg-card)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <h2 style={{ fontSize: '17px', fontWeight: 800, margin: 0 }}>LightGBM Production Governance</h2>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Model {modelOps?.model_status.available ? 'available' : 'unavailable'}: <strong>{modelOps?.model_status.model_version || 'No loaded model'}</strong> &bull; Features: {modelOps?.model_status.feature_count ?? 0}
                  {!modelOps?.model_status.available && modelOps?.model_status.error ? ` • ${modelOps.model_status.error}` : ''}
                </p>
              </div>
              <button
                disabled={rollingBack}
                onClick={handleRollbackModel}
                style={{
                  display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 18px',
                  backgroundColor: '#F59E0B', color: '#000', border: 'none', borderRadius: 'var(--radius-sm)',
                  fontWeight: 700, fontSize: '13px', cursor: rollingBack ? 'not-allowed' : 'pointer'
                }}
              >
                <RotateCcw size={16} />
                {rollingBack ? 'Rolling back...' : 'Rollback Model Version'}
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px', marginTop: '16px' }}>
              <div style={{ padding: '14px', backgroundColor: 'var(--bg-card-subtle)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Precision-Recall AUC</div>
                <div style={{ fontSize: '20px', fontWeight: 800, color: 'var(--text-primary)', marginTop: '4px' }}>
                  {modelOps?.metrics.pr_auc?.toFixed(4) ?? '—'}
                </div>
              </div>
              <div style={{ padding: '14px', backgroundColor: 'var(--bg-card-subtle)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Recall @ 1% FPR</div>
                <div style={{ fontSize: '20px', fontWeight: 800, color: '#10B981', marginTop: '4px' }}>
                  {modelOps?.metrics.recall_at_1pct_fpr != null ? `${(modelOps.metrics.recall_at_1pct_fpr * 100).toFixed(1)}%` : '—'}
                </div>
              </div>
              <div style={{ padding: '14px', backgroundColor: 'var(--bg-card-subtle)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Worst Decile Gap</div>
                <div style={{ fontSize: '20px', fontWeight: 800, color: 'var(--text-primary)', marginTop: '4px' }}>
                  {modelOps?.metrics.worst_decile_gap_pp != null ? `${modelOps.metrics.worst_decile_gap_pp.toFixed(2)} pp` : '—'}
                </div>
              </div>
              <div style={{ padding: '14px', backgroundColor: 'var(--bg-card-subtle)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Brier Score Loss</div>
                <div style={{ fontSize: '20px', fontWeight: 800, color: 'var(--text-primary)', marginTop: '4px' }}>
                  {modelOps?.metrics.brier?.toFixed(6) ?? '—'}
                </div>
              </div>
            </div>
          </div>

          <div style={{ backgroundColor: 'var(--bg-card)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', overflow: 'hidden' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-color)' }}>
              <h3 style={{ fontSize: '14px', fontWeight: 700, margin: 0 }}>Model Registry Retraining & Promotion Log</h3>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ backgroundColor: 'var(--bg-card-subtle)', color: 'var(--text-muted)' }}>
                  <th style={{ padding: '12px 20px', textAlign: 'left' }}>Candidate Version</th>
                  <th style={{ padding: '12px 20px', textAlign: 'left' }}>Incumbent Live</th>
                  <th style={{ padding: '12px 20px', textAlign: 'left' }}>Gate Outcome</th>
                  <th style={{ padding: '12px 20px', textAlign: 'left' }}>Reason & Cost Delta</th>
                  <th style={{ padding: '12px 20px', textAlign: 'left' }}>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {modelOps?.history && modelOps.history.length > 0 ? (
                  modelOps.history.map((h, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '12px 20px', fontFamily: 'monospace', fontWeight: 700 }}>{h.candidate_version}</td>
                      <td style={{ padding: '12px 20px', fontFamily: 'monospace', color: 'var(--text-secondary)' }}>{h.live_version}</td>
                      <td style={{ padding: '12px 20px' }}>
                        <span style={{
                          padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 700,
                          backgroundColor: h.promoted ? '#ECFDF5' : '#FEF2F2',
                          color: h.promoted ? '#065F46' : '#B91C1C'
                        }}>
                          {h.promoted ? 'PROMOTED TO PROD' : 'REJECTED AT GATE'}
                        </span>
                      </td>
                      <td style={{ padding: '12px 20px', color: 'var(--text-secondary)' }}>{h.reason}</td>
                      <td style={{ padding: '12px 20px', color: 'var(--text-muted)' }}>{h.timestamp}</td>
                    </tr>
                  ))
                ) : (
                  <tr><td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>No historical promotions recorded yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab: Overview & Investigation Live Transactions */}
      {(activeTab === 'overview' || activeTab === 'investigation') && (
        <>
          {activeTab === 'overview' && (
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
          )}

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
        {reviewMessage && (
          <div style={{ padding: '12px 22px', backgroundColor: '#ECFDF5', color: '#065F46', fontSize: '13px', fontWeight: 600 }}>
            {reviewMessage}
          </div>
        )}
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
                <th style={{ padding: '12px 20px', fontSize: '11px', textTransform: 'uppercase' }}>Risk Analysis / Why</th>
                <th style={{ padding: '12px 20px', fontSize: '11px', textTransform: 'uppercase' }}>Status</th>
                <th style={{ padding: '12px 20px', fontSize: '11px', textTransform: 'uppercase' }}>Timestamp</th>
                <th style={{ padding: '12px 20px', fontSize: '11px', textTransform: 'uppercase' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {transactions
                .filter((tx) => activeTab === 'overview' || tx.status === 'PENDING_REVIEW')
                .map((transaction) => {
                const isUnderReview = transaction.status === 'PENDING_REVIEW';
                return (
                  <tr key={transaction.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '12px 20px', color: 'var(--primary)', fontFamily: 'monospace', fontSize: '12px' }}>{transaction.id}</td>
                    <td style={{ padding: '12px 20px', color: 'var(--text-primary)' }}>
                      {transaction.sender_name} &rarr; {transaction.recipient_name}
                    </td>
                    <td style={{ padding: '12px 20px', color: 'var(--text-primary)', fontWeight: 700 }}>
                      ${transaction.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td style={{ padding: '12px 20px', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ fontWeight: 700, color: (transaction.fraud_probability ?? 0) > 0.04 ? '#F59E0B' : '#10B981' }}>
                          {transaction.fraud_probability == null ? 'Unavailable' : formatFraudProbability(transaction.fraud_probability, transaction.raw_fraud_probability)}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '12px 20px', color: 'var(--text-primary)', fontFamily: 'monospace' }}>
                      <span style={{
                        padding: '3px 8px',
                        borderRadius: '4px',
                        fontSize: '11px',
                        fontWeight: 700,
                        backgroundColor: transaction.decision === 'APPROVE' ? '#ECFDF5' : transaction.decision === 'REVIEW' ? '#FEF3C7' : '#FEF2F2',
                        color: transaction.decision === 'APPROVE' ? '#065F46' : transaction.decision === 'REVIEW' ? '#92400E' : '#B91C1C'
                      }}>
                        {transaction.decision || 'N/A'}
                      </span>
                    </td>
                    <td style={{ padding: '12px 20px', maxWidth: '280px' }}>
                      {transaction.risk_reasons && transaction.risk_reasons.length > 0 ? (
                        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '3px' }}>
                          {transaction.risk_reasons.map((r, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '4px' }}>
                              <span style={{ color: 'var(--primary)' }}>&bull;</span>
                              <span>{r}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                          {transaction.decision === 'APPROVE' || transaction.decision === 'MANUALLY_APPROVED' || transaction.decision === 'VERIFIED_STEP_UP'
                            ? 'Normal transaction profile — low fraud risk (approved).'
                            : 'No elevated-risk reason returned by the scoring service.'}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '12px 20px', color: 'var(--text-secondary)' }}>
                      {transaction.status.replaceAll('_', ' ')}
                    </td>
                    <td style={{ padding: '12px 20px', color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: '12px' }}>
                      {new Date(transaction.timestamp).toLocaleString()}
                    </td>
                    <td style={{ padding: '12px 20px' }}>
                      {isUnderReview ? (
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button
                            disabled={processingId === transaction.id}
                            onClick={() => handleReviewAction(transaction.id, 'APPROVE')}
                            style={{
                              padding: '5px 10px',
                              backgroundColor: '#10B981',
                              color: '#FFFFFF',
                              border: 'none',
                              borderRadius: '4px',
                              fontSize: '11px',
                              fontWeight: 700,
                              cursor: processingId === transaction.id ? 'not-allowed' : 'pointer'
                            }}
                          >
                            Approve
                          </button>
                          <button
                            disabled={processingId === transaction.id}
                            onClick={() => handleReviewAction(transaction.id, 'REJECT')}
                            style={{
                              padding: '5px 10px',
                              backgroundColor: '#EF4444',
                              color: '#FFFFFF',
                              border: 'none',
                              borderRadius: '4px',
                              fontSize: '11px',
                              fontWeight: 700,
                              cursor: processingId === transaction.id ? 'not-allowed' : 'pointer'
                            }}
                          >
                            Reject
                          </button>
                        </div>
                      ) : (
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Settled</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {!transactions.length && !feedError && (
                <tr>
                  <td colSpan={8} style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No persisted transactions recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      </>
      )}
    </div>
  );
};
