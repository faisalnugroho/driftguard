import React, { useEffect, useState } from 'react';
import { useApp } from '../lib/store';
import { shortAddr } from '../lib/types';
import * as chain from '../lib/chain';

export function TopBar() {
  const app = useApp();
  const info = useContractInfoOnce();

  return (
    <header className="topbar">
      <button className="brand" onClick={() => app.go({ page: 'dashboard' })}>
        <span className="brand-mark" aria-hidden>
          ⟁
        </span>
        DriftGuard
      </button>
      <nav className="tabs">
        <button
          className={app.route.page === 'dashboard' ? 'active' : ''}
          onClick={() => app.go({ page: 'dashboard' })}
        >
          Dashboard
        </button>
        <button
          className={app.route.page === 'create' ? 'active' : ''}
          onClick={() => app.go({ page: 'create' })}
        >
          Create Watch
        </button>
        <a href="#about" className="tab-link">
          How it works
        </a>
      </nav>
      <div className="net-switch" role="group" aria-label="Network mode">
        <button
          className={app.net === 'live' ? 'active' : ''}
          onClick={() => app.setNet('live')}
          title="Real GenLayer Studionet consensus via the deployed Intelligent Contract"
        >
          LIVE
        </button>
        <button
          className={app.net === 'demo' ? 'active' : ''}
          onClick={() => app.setNet('demo')}
          title="Deterministic local simulation — no consensus, no chain, for UI testing only"
        >
          DEMO
        </button>
      </div>
      <div className="net-badge">
        {app.net === 'demo' ? (
          <span className="badge tone-warn demo-badge">DEMO MODE — simulated, not consensus</span>
        ) : chain.hasSDK ? (
          <span className="badge tone-ok">Studionet</span>
        ) : (
          <span className="badge tone-bad">SDK missing</span>
        )}
        {app.net === 'live' && info ? (
          <span className="badge tone-muted" title="Protocol version">
            v{info.protocol_version}
          </span>
        ) : null}
      </div>
    </header>
  );
}

function useContractInfoOnce() {
  const app = useApp();
  const [info, setInfo] = useState<any>(null);
  useEffect(() => {
    if (app.net !== 'live' || info) return;
    app
      .contractInfo()
      .then(setInfo)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app.net]);
  return info;
}

export function WalletBar() {
  const app = useApp();
  if (app.net === 'demo') {
    return (
      <div className="walletbar">
        <span className="wallet-note">
          Demo mode uses a simulated wallet — no keys, no chain, no consensus.
        </span>
      </div>
    );
  }
  return (
    <div className="walletbar">
      <div className="wallet-chips">
        {app.wallets.length === 0 ? (
          <span className="wallet-note">
            No signer yet — create a burner wallet (stays in this browser) and
            fund it from the Studionet faucet.
          </span>
        ) : (
          app.wallets.map((w, i) => (
            <button
              key={i}
              className={'chip' + (app.activeWallet === w ? ' active' : '')}
              onClick={() => app.selectWallet(i)}
              title={w.address + ' — click to make active signer'}
            >
              {shortAddr(w.address)}
            </button>
          ))
        )}
      </div>
      <div className="wallet-actions">
        <button
          className="btn small"
          onClick={() => {
            const w = app.newWallet();
            app.notify('Burner wallet created: ' + shortAddr(w.address));
          }}
        >
          New wallet
        </button>
        <button
          className="btn small ghost"
          onClick={() => {
            const pk = window.prompt(
              'Paste private key (0x…). It stays in this browser.'
            );
            if (pk) {
              try {
                app.importWallet(pk);
                app.notify('Wallet imported');
              } catch {
                app.notify('Invalid private key', true);
              }
            }
          }}
        >
          Import
        </button>
        <button
          className="btn small ghost"
          disabled={!app.activeWallet}
          onClick={async () => {
            try {
              await app.faucet();
              app.notify('Faucet: 5 GEN sent to the active wallet');
            } catch (e: any) {
              app.notify('Faucet failed: ' + String(e?.message || e), true);
            }
          }}
        >
          Faucet
        </button>
      </div>
    </div>
  );
}

export function BusyOverlay() {
  const app = useApp();
  if (!app.busy) return null;
  return (
    <div className="busy-overlay" role="status">
      <div className="busy-box">
        <span className="spinner big" aria-hidden />
        <div className="busy-title">GenLayer consensus in progress</div>
        <div className="busy-msg">{app.busy}</div>
      </div>
    </div>
  );
}

export function Toast() {
  const app = useApp();
  if (!app.toast) return null;
  return (
    <div className={'toast show' + (app.toast.err ? ' err' : '')}>
      {app.toast.msg}
    </div>
  );
}

export function About() {
  const app = useApp();
  const [info, setInfo] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    app
      .contractInfo()
      .then((i) => setInfo(i))
      .catch((e) => setErr(String(e?.message || e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app.net]);
  return (
    <section id="about" className="about">
      <h2>How DriftGuard works</h2>
      <ol className="flow">
        <li>
          <b>Register</b> a public URL and say what matters about it (the
          criteria).
        </li>
        <li>
          <b>Baseline:</b> GenLayer's leader retrieves the page, strips markup
          noise, and an LLM extracts a structured semantic state limited to
          your criteria. Validators independently re-derive it and must agree
          on substance — title, topics, values — before anything is stored.
        </li>
        <li>
          <b>Check:</b> the source is re-observed the same way. The LLM
          compares the current semantic state against the accepted baseline
          and proposes NO_CHANGE / MINOR_CHANGE / MATERIAL_CHANGE /
          UNCERTAIN. Retrieval failures become SOURCE_UNAVAILABLE — a
          deterministic gate no LLM can override.
        </li>
        <li>
          <b>Consensus:</b> every validator re-runs the entire pipeline
          itself. The leader's classification is accepted only if it matches
          the validator's own under an explicit equivalence matrix — a material
          change can never be downgraded to "no change", and an unavailable
          source can never masquerade as a calm one.
        </li>
        <li>
          <b>On-chain state:</b> accepted results update the watch, append to
          its immutable history, and the baseline moves only when you
          explicitly promote it.
        </li>
      </ol>
      {info ? (
        <div className="about-info">
          <div>
            <span className="kv-label">Contract</span>
            <span className="kv-value mono">
              {app.net === 'live'
                ? app.contract || 'Not deployed'
                : 'simulated (demo mode)'}
            </span>
          </div>
          <div>
            <span className="kv-label">Equivalence matrix</span>
            <span className="kv-value">
              {Object.entries(info.equivalence_matrix || {})
                .map(([k, v]) => `${k} ↔ ${(v as string[]).join('/')}`)
                .join('  ·  ')}
            </span>
          </div>
          <div>
            <span className="kv-label">Retrieval gate</span>
            <span className="kv-value">
              HTTP 4xx/5xx/network error → SOURCE_UNAVAILABLE · empty page →
              UNCERTAIN (never NO_CHANGE)
            </span>
          </div>
        </div>
      ) : err ? (
        <div className="about-info">
          <span className="kv-value muted">{err}</span>
        </div>
      ) : null}
      <p className="about-note">
        DriftGuard needs GenLayer because byte-diffing can't tell "30 days → 14
        days" from "30 days → thirty (30) days", and a single LLM shouldn't be
        trusted to make that call for a protocol that depends on it. A
        conventional backend can detect byte-level changes; only decentralized
        semantic consensus makes the <b>meaning-level</b> verdict trustless.
      </p>
    </section>
  );
}

export function Footer() {
  const app = useApp();
  return (
    <footer className="footer">
      <span>
        DriftGuard — trustless semantic change detection for the open web.
      </span>
      {app.net === 'live' && app.contract ? (
        <a
          href={chain.EXPLORER_ADDR + app.contract}
          target="_blank"
          rel="noopener noreferrer"
        >
          View contract on explorer ↗
        </a>
      ) : null}
    </footer>
  );
}
