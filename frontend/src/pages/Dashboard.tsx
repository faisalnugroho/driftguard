import React, { useEffect, useState } from 'react';
import { useApp } from '../lib/store';
import { Stat, Empty, ClassBadge, SourceBadge, Spinner } from '../components/ui';
import type { Watch, Stats } from '../lib/types';
import { fmtAgo } from '../lib/types';

export default function Dashboard() {
  const app = useApp();
  const [watches, setWatches] = useState<Watch[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    setErr(null);
    try {
      const [w, s] = await Promise.all([app.listWatches(), app.stats()]);
      setWatches(w);
      setStats(s);
    } catch (e: any) {
      setErr(String(e?.message || e));
      setWatches([]);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app.net]);

  return (
    <div className="page">
      <section className="hero">
        <div className="hero-copy">
          <div className="hero-eyebrow">DECENTRALIZED CHANGE DETECTION</div>
          <h1>
            The web changes.
            <br />
            <span className="accent">Meaning</span> shouldn't drift past you.
          </h1>
          <p className="hero-sub">
            DriftGuard is a decentralized web-change monitoring protocol.
            GenLayer validators independently retrieve a registered public source,
            normalize what it says, and reach consensus on whether its{' '}
            <b>meaning</b> materially changed — not its bytes, not its layout.
          </p>
          <div className="hero-actions">
            <button className="btn primary" onClick={() => app.go({ page: 'create' })}>
              Create Watch
            </button>
            {watches && watches.length > 0 ? (
              <span className="hero-note">
                {watches.length} watch{watches.length === 1 ? '' : 'es'} on-chain
              </span>
            ) : null}
          </div>
        </div>
        <div className="hero-panel">
          <div className="demo-strip">
            <span className="pulse" aria-hidden />
            30 days → 14 days = MATERIAL_CHANGE
            <span className="demo-vs">vs</span>
            30 days → thirty (30) days = NO_CHANGE
          </div>
          <p className="hero-panel-note">
            A byte-diff sees both edits. Only semantic consensus under the
            Equivalence Principle can tell a policy change from a rewording —
            and it takes a majority of independent validators to make the call.
          </p>
        </div>
      </section>

      <section className="stats-row" aria-label="Protocol statistics">
        <Stat label="Active watches" value={stats?.active_watches ?? '—'} />
        <Stat label="Total checks" value={stats?.total_checks ?? '—'} />
        <Stat label="Material changes" value={stats?.material_changes ?? '—'} tone="bad" />
        <Stat label="Uncertain checks" value={stats?.uncertain_checks ?? '—'} tone="muted" />
      </section>

      {err ? (
        <div className="notice err">
          {err}
          <button className="btn small" onClick={load}>
            Retry
          </button>
        </div>
      ) : null}

      <section className="watch-list">
        <h2>Your Watches</h2>
        {watches === null ? (
          <Spinner label="Loading watches…" />
        ) : watches.length === 0 ? (
          <Empty
            title="No watches registered"
            hint="Register a public URL, say what matters about it, and create its semantic baseline."
            action={
              <button className="btn primary" onClick={() => app.go({ page: 'create' })}>
                Create Watch
              </button>
            }
          />
        ) : (
          <ul className="watch-cards">
            {watches.map((w) => (
              <li
                key={w.watch_id}
                className="watch-card"
                onClick={() => app.go({ page: 'watch', id: w.watch_id })}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') app.go({ page: 'watch', id: w.watch_id });
                }}
              >
                <div className="wc-top">
                  <span className="wc-name">{w.name}</span>
                  {!w.active ? <span className="badge tone-muted">PAUSED</span> : null}
                </div>
                <div className="wc-url">{w.url}</div>
                {w.latest_status || w.baseline ? (
                  <div className="wc-badges">
                    <ClassBadge cls={(w.latest_status as string) || 'BASELINE_CREATED'} />
                    {w.latest_source_status ? (
                      <SourceBadge status={w.latest_source_status} />
                    ) : null}
                  </div>
                ) : null}
                <div className="wc-meta">
                  <span>{w.total_checks} checks</span>
                  <span>{w.material_changes} material</span>
                  <span>last checked {fmtAgo(w.last_checked_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
