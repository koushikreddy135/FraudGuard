import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Search, WalletCards } from 'lucide-react';
import { apiRequest } from '../../services/api';

interface Recipient {
  id: string;
  full_name: string;
  email: string;
  account_id: string;
}

interface Account {
  id: string;
  balance: number;
  balance_cents: number;
  currency: string;
  simulated: boolean;
  updated_at: string;
}

interface Transaction {
  id: string;
  recipient_id: string;
  recipient_name?: string;
  sender_name?: string;
  amount: number;
  description?: string;
  fraud_probability?: number;
  decision?: string;
  status: string;
  risk_reasons: string[];
  created_at: string;
}

export const CustomerTransfers: React.FC = () => {
  const [account, setAccount] = useState<Account | null>(null);
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [recipient, setRecipient] = useState('');
  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [decisionFilter, setDecisionFilter] = useState('');
  const idempotencyKeyRef = useRef<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError('');
    try {
      const [accountData, recipientData, transferData] = await Promise.all([
        apiRequest<Account>('/api/customer/account'),
        apiRequest<{ recipients: Recipient[] }>('/api/customer/recipients'),
        apiRequest<{ transactions: Transaction[] }>('/api/customer/transfers'),
      ]);
      setAccount(accountData);
      setRecipients(recipientData.recipients);
      setTransactions(transferData.transactions);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load account data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const selectedRecipient = recipients.find((item) => item.id === recipient);
  const parsedAmount = Number(amount);

  const validate = () => {
    if (!recipient) return 'Select a recipient.';
    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) return 'Enter a valid transfer amount.';
    if (parsedAmount > 1000000) return 'Amount cannot exceed $1,000,000.';
    if (account && parsedAmount * 100 > account.balance_cents) return 'Insufficient simulated funds.';
    return '';
  };

  const filteredTransactions = useMemo(() => {
    return transactions.filter((item) => {
      if (decisionFilter && (item.decision || '').toUpperCase() !== decisionFilter) return false;
      const haystack = `${item.id} ${item.recipient_name || ''} ${item.sender_name || ''} ${item.description || ''}`.toLowerCase();
      return !search || haystack.includes(search.toLowerCase());
    });
  }, [transactions, search, decisionFilter]);

  const submitTransfer = async () => {
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setSubmitting(true);
    setError('');
    setMessage('');
    try {
      const result = await apiRequest<Transaction>('/api/customer/transfers', {
        method: 'POST',
        body: JSON.stringify({
          recipient,
          amount: parsedAmount,
          description: description.trim() || null,
          idempotency_key: idempotencyKeyRef.current || (idempotencyKeyRef.current = crypto.randomUUID()),
        }),
      });
      idempotencyKeyRef.current = null;
      setMessage(
        result.status === 'COMPLETED'
          ? `Transfer approved and completed. Transaction ${result.id}.`
          : `Transfer recorded with status ${result.status.replaceAll('_', ' ').toLowerCase()} (${result.decision}).`
      );
      setReviewing(false);
      setRecipient('');
      setAmount('');
      setDescription('');
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Transfer could not be submitted.');
      setReviewing(false);
    } finally {
      setSubmitting(false);
    }
  };

  const statusStyle = (status: string) => {
    if (status === 'COMPLETED') return { background: '#ECFDF5', color: '#065F46' };
    if (status === 'DECLINED') return { background: '#FEF2F2', color: '#991B1B' };
    if (status === 'PENDING_REVIEW') return { background: '#FEF3C7', color: '#92400E' };
    return { background: '#EFF6FF', color: '#1E3A8A' };
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div>
        <h1 style={{ fontSize: '26px', fontWeight: 800, color: 'var(--text-primary)' }}>Transfers & Activity</h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginTop: '4px' }}>Simulated funds protected by the FraudGuard AI decision engine</p>
      </div>

      {error && <div role="alert" style={{ padding: '12px 14px', borderRadius: 'var(--radius-sm)', border: '1px solid #FCA5A5', background: '#FEF2F2', color: '#991B1B', fontSize: '13px' }}>{error}</div>}
      {message && <div role="status" style={{ padding: '12px 14px', borderRadius: 'var(--radius-sm)', border: '1px solid #A7F3D0', background: '#ECFDF5', color: '#065F46', fontSize: '13px' }}>{message}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px' }}>
        <section style={{ background: '#fff', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '18px' }}>
            <WalletCards size={20} color="var(--primary)" />
            <h2 style={{ fontSize: '16px', color: 'var(--text-primary)' }}>Simulated account balance</h2>
          </div>
          <div style={{ fontSize: '32px', fontWeight: 800, color: 'var(--text-primary)' }}>
            {account ? `$${account.balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : 'Loading...'}
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: '12px', marginTop: '6px' }}>USD simulated funds</div>
        </section>

        <section style={{ background: '#fff', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '24px' }}>
          <h2 style={{ fontSize: '16px', color: 'var(--text-primary)', marginBottom: '16px' }}>Send money</h2>
          {!reviewing ? (
            <div style={{ display: 'grid', gap: '12px' }}>
              <label style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 700 }}>Recipient
                <select value={recipient} onChange={(e) => { idempotencyKeyRef.current = null; setRecipient(e.target.value); }} style={{ width: '100%', marginTop: '6px', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', background: '#fff' }}>
                  <option value="">Select customer or account</option>
                  {recipients.map((item) => <option key={item.id} value={item.id}>{item.full_name} — {item.email}</option>)}
                </select>
              </label>
              <label style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 700 }}>Amount (USD)
                <input type="number" min="0.01" step="0.01" value={amount} onChange={(e) => { idempotencyKeyRef.current = null; setAmount(e.target.value); }} placeholder="0.00" style={{ width: '100%', marginTop: '6px', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }} />
              </label>
              <label style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 700 }}>Description (optional)
                <input value={description} maxLength={240} onChange={(e) => { idempotencyKeyRef.current = null; setDescription(e.target.value); }} placeholder="What is this transfer for?" style={{ width: '100%', marginTop: '6px', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }} />
              </label>
              <button disabled={loading || !recipients.length} onClick={() => { setError(validate()); if (!validate()) setReviewing(true); }} style={{ padding: '11px', borderRadius: 'var(--radius-sm)', border: 'none', background: 'var(--primary)', color: '#fff', fontWeight: 700 }}>
                Review transfer
              </button>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: '12px' }}>
              <div style={{ padding: '14px', borderRadius: 'var(--radius-sm)', background: 'var(--bg-card-subtle)', border: '1px solid var(--border-color)' }}>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Recipient</div>
                <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{selectedRecipient?.full_name}</div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{selectedRecipient?.email}</div>
                <div style={{ marginTop: '10px', fontSize: '24px', fontWeight: 800 }}>${parsedAmount.toFixed(2)}</div>
                {description && <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '6px' }}>{description}</div>}
              </div>
              <button disabled={submitting} onClick={submitTransfer} style={{ padding: '11px', borderRadius: 'var(--radius-sm)', border: 'none', background: 'var(--primary)', color: '#fff', fontWeight: 700 }}>
                {submitting ? 'Analyzing transfer...' : 'Confirm & submit'}
              </button>
              <button disabled={submitting} onClick={() => { idempotencyKeyRef.current = null; setReviewing(false); }} style={{ padding: '9px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', background: '#fff', color: 'var(--text-primary)' }}>Edit details</button>
            </div>
          )}
        </section>
      </div>

      <section style={{ background: '#fff', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
        <div style={{ padding: '18px 20px', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <h2 style={{ fontSize: '16px', color: 'var(--text-primary)' }}>Transaction history</h2>
          <div style={{ display: 'flex', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', padding: '6px 8px' }}>
              <Search size={14} />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search" style={{ border: 'none', outline: 'none', width: '140px' }} />
            </div>
            <select value={decisionFilter} onChange={(e) => setDecisionFilter(e.target.value)} style={{ border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', padding: '6px 8px', background: '#fff' }}>
              <option value="">All decisions</option>
              <option value="APPROVE">APPROVE</option>
              <option value="STEP_UP">STEP_UP</option>
              <option value="REVIEW">REVIEW</option>
              <option value="DECLINE">DECLINE</option>
            </select>
          </div>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead><tr style={{ background: 'var(--bg-card-subtle)', color: 'var(--text-muted)' }}>
              <th style={{ textAlign: 'left', padding: '12px 16px' }}>Recipient / sender</th><th style={{ textAlign: 'left', padding: '12px 16px' }}>Amount</th><th style={{ textAlign: 'left', padding: '12px 16px' }}>Decision</th><th style={{ textAlign: 'left', padding: '12px 16px' }}>Status</th><th style={{ textAlign: 'left', padding: '12px 16px' }}>Date</th><th style={{ textAlign: 'left', padding: '12px 16px' }}>Transaction ID</th>
            </tr></thead>
            <tbody>
              {filteredTransactions.map((item) => (
                <tr key={item.id} style={{ borderTop: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '12px 16px' }}>{item.recipient_name || item.sender_name || item.recipient_id}</td>
                  <td style={{ padding: '12px 16px', fontWeight: 700 }}>${item.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                  <td style={{ padding: '12px 16px', fontFamily: 'monospace' }}>{item.decision || 'N/A'}</td>
                  <td style={{ padding: '12px 16px' }}><span style={{ ...statusStyle(item.status), borderRadius: '12px', padding: '4px 8px', fontSize: '11px', fontWeight: 700 }}>{item.status.replaceAll('_', ' ')}</span></td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>{new Date(item.created_at).toLocaleString()}</td>
                  <td style={{ padding: '12px 16px', fontFamily: 'monospace', fontSize: '11px' }}>{item.id}</td>
                </tr>
              ))}
              {!filteredTransactions.length && <tr><td colSpan={6} style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>{loading ? 'Loading transactions...' : 'No persisted transactions found.'}</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};
