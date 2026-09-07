import React, { useState } from 'react';
import { useApp } from '../lib/store';
import { Spinner } from '../components/ui';

const EXAMPLES = [
  {
    label: 'Ethereum docs',
    name: 'Ethereum Documentation',
    url: 'https://ethereum.org/en/developers/docs/',
    criteria: 'Monitor major protocol documentation changes.',
  },
  {
    label: 'API docs',
    name: 'Payments API documentation',
    url: 'https://docs.tavily.com/documentation/api-reference/endpoint/search.md',
    criteria:
      'Monitor authentication, rate limits, endpoints and breaking changes.',
  },
  {
    label: 'Store terms',
    name: 'Storefront refund policy',
    url: 'https://store.example.com/refund-policy',
    criteria: 'Monitor fees, eligibility, refund rules and deadlines.',
  },
];

export default function CreateWatch() {
  const app = useApp();
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [criteria, setCriteria] = useState(
    'Monitor pricing, fees, eligibility requirements and important deadlines.'
  );
  const [busy, setLocalBusy] = useState(false);

  const submit = async () => {
    if (!name.trim() || !url.trim() || !criteria.trim()) {
      app.notify('All three fields are required', true);
      return;
    }
    setLocalBusy(true);
    try {
      const wid = await app.createWatch(name.trim(), url.trim(), criteria.trim());
      app.notify(`Watch #${wid} registered`);
      app.go({ page: 'watch', id: String(wid) });
    } catch (e: any) {
      app.notify(String(e?.message || e), true);
    } finally {
      setLocalBusy(false);
    }
  };

  return (
    <div className="page narrow">
      <h1>Create Watch</h1>
      <p className="sub">
        A Watch is a public web source whose meaning DriftGuard monitors. You
        define <b>what matters</b> about the source; validators use exactly that
        as their extraction criteria during consensus.
      </p>

      <div className="form">
        <label>
          <span>Watch name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Storefront refund policy"
            maxLength={80}
          />
        </label>
        <label>
          <span>Source URL (public http/https)</span>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/refund-policy"
            maxLength={300}
          />
          <span className="hint">
            Must be reachable by validators. Private, loopback and link-local
            addresses are rejected.
          </span>
        </label>
        <label>
          <span>What should be monitored?</span>
          <textarea
            value={criteria}
            onChange={(e) => setCriteria(e.target.value)}
            rows={3}
            maxLength={400}
            placeholder="Monitor pricing, fees, eligibility requirements and important deadlines."
          />
          <span className="hint">
            This text is injected into every validator's extraction prompt and
            cannot be redefined by the monitored page.
          </span>
        </label>
        <button className="btn primary" disabled={busy} onClick={submit}>
          {busy ? <Spinner label="Registering watch…" /> : 'Create Watch'}
        </button>
      </div>

      <div className="examples">
        <h3>Example configurations</h3>
        <p className="sub">
          These are starting points — only URLs you explicitly register are
          monitored. A watch makes no claim about a source until its baseline
          exists.
        </p>
        <ul>
          {EXAMPLES.map((ex, i) => (
            <li key={i}>
              <button
                className="btn small ghost"
                onClick={() => {
                  setName(ex.name);
                  setUrl(ex.url);
                  setCriteria(ex.criteria);
                }}
              >
                Use
              </button>
              <div>
                <b>{ex.name}</b>
                <div className="ex-url">{ex.url}</div>
                <div className="ex-crit">{ex.criteria}</div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
