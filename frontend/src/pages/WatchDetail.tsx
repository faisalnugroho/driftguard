import React, { useCallback, useEffect, useState } from 'react';
import { useApp } from '../lib/store';
import {
  Badge,
  ChangeCard,
  ClassBadge,
  Empty,
  HistoryItem,
  SourceBadge,
  Spinner,
} from '../components/ui';
import type { Watch, HistoryRecord } from '../lib/types';
import { fmtAgo, fmtDate, shortAddr, shortFp } from '../lib/types';

export default function WatchDetail({ id }: { id: string }) {
  const app = useApp();
  const [watch, setWatch] = useState<Watch | null>(null);
  const [history, setHistory] = useState<HistoryRecord[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [actBusy, setActBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [w, h] = await Promise.all([
        app.getWatch(id),
        app.getHistory(id),
      ]);
      setWatch(w);
      setHistory(h);
    } catch (e: any) {
      setErr(String(e?.message || e));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, app.net]);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setActBusy(label);
    setErr(null);
    try {
      await fn();
      app.notify(label + ' — done');
      await load();
    } catch (e: any) {
      const msg = String(e?.message || e);
      setErr(msg);
      app.notify(msg, true);
    } finally {
      setActBusy(null);
    }
  };

  if (err && !watch) {
    return (
      <div className="page narrow">
        <Empty
          title="Could not load watch"
          hint={err}
          action={
            <button className="btn" onClick={() => app.go({ page: 'dashboard' })}>
              Back to dashboard
            </button>
          }
        />
      </div>
    );
  }
  if (!watch) {
    return (
      <div className="page">
        <Spinner label="Loading watch…" />
      </div>
    );
  }

  const b = watch.baseline;
  const cls = watch.latest_status;
  const src = watch.latest_source_status;

  return (
    <div className="page">
      <button className="btn small ghost back" onClick={() => app.go({ page: 'dashboard' })}>
        ← All watches
      </button>

      <header className="wd-head">
        <div>
          <h1>{watch.name}</h1>
          <a className="wd-url" href={watch.url} target="_blank" rel="noopener noreferrer">
            {watch.url}
          </a>
          <div className="wd-meta">
            <span>
              <b>Status</b>{' '}
              {watch.active ? <Badge kind="ok">ACTIVE</Badge> : <Badge kind="muted">PAUSED</Badge>}
            </span>
            <span>
              <b>Owner</b> {shortAddr(watch.owner)}
            </span>
            <span>
              <b>Created</b> {fmtDate(watch.created_at)}
            </span>
            <span className="wd-id">Watch #{watch.watch_id}</span>
          </div>
        </div>
        <div className="wd-criteria">
          <span className="kv-label">Monitoring criteria</span>
          <p>{watch.criteria}</p>
        </div>
      </header>

      {err ? <div className="notice err">{err}</div> : null}

      {/* ---------------- CURRENT STATUS ---------------- */}
      <section className="wd-status">
        <div className={`status-card tone-${clsTone(cls)}`}>
          <div className="status-head">
            <span className="status-eyebrow">CURRENT STATUS</span>
            <SourceBadge status={src} />
          </div>
          {cls ? (
            <>
              <div className="status-word">{cls.replace(/_/g, ' ')}</div>
              <div className="status-expl">{watch.last_explanation || '—'}</div>
            </>
          ) : (
            <div className="status-word muted">NO BASELINE YET</div>
          )}
          <div className="status-facts">
            <div>
              <span className="kv-label">Last checked</span>
              <b>{watch.last_checked_at ? fmtDate(watch.last_checked_at) : 'never'}</b>
              <span className="ago">({fmtAgo(watch.last_checked_at)})</span>
            </div>
            <div>
              <span className="kv-label">Checks performed</span>
              <b>{watch.total_checks}</b>
            </div>
            <div>
              <span className="kv-label">Material changes</span>
              <b>{watch.material_changes}</b>
            </div>
            <div>
              <span className="kv-label">Current fingerprint</span>
              <b className="mono">{shortFp(watch.latest_fingerprint)}</b>
            </div>
            <div>
              <span className="kv-label">Baseline fingerprint</span>
              <b className="mono">{shortFp(b?.fingerprint)}</b>
            </div>
          </div>
          <div className="wd-actions">
            <button
              className="btn primary"
              disabled={!!actBusy || !b || !watch.active}
              onClick={() => act('Check Now', () => app.checkWatch(id))}
            >
              {actBusy === 'Check Now' ? <Spinner label="Consensus running…" /> : 'Check Now'}
            </button>
            <button
              className="btn"
              disabled={!!actBusy || !watch.latest_state}
              onClick={() => act('Promote Current State', () => app.promoteBaseline(id))}
              title={
                watch.latest_state
                  ? 'Make the latest accepted semantic state the new baseline'
                  : 'No accepted latest state to promote yet'
              }
            >
              {actBusy === 'Promote Current State' ? <Spinner /> : 'Promote Current State'}
            </button>
            {watch.active ? (
              <button
                className="btn ghost"
                disabled={!!actBusy}
                onClick={() => act('Pause Watch', () => app.deactivateWatch(id))}
              >
                Pause Watch
              </button>
            ) : (
              <button
                className="btn"
                disabled={!!actBusy}
                onClick={() => act('Resume Watch', () => app.activateWatch(id))}
              >
                Resume Watch
              </button>
            )}
            <button
              className="btn ghost"
              disabled={!!actBusy}
              onClick={() => act('Create Baseline', () => app.createBaseline(id))}
              style={{ display: b ? 'none' : undefined }}
            >
              Create Baseline
            </button>
          </div>
          {!b ? (
            <div className="notice">
              No baseline yet. Run <b>Create Baseline</b> — validators will
              observe the source and agree on its initial semantic state before
              any change detection can run.
            </div>
          ) : null}
        </div>

        {/* change evidence */}
        {cls === 'MATERIAL_CHANGE' && watch.last_changes?.length ? (
          <ChangeCard changes={watch.last_changes} explanation={watch.last_explanation} />
        ) : null}

        {/* baseline state */}
        {b ? (
          <div className="baseline-card">
            <div className="baseline-head">
              <span>ACCEPTED BASELINE</span>
              <span className="mono">{b.fingerprint}</span>
            </div>
            {b.title ? <div className="baseline-title">{b.title}</div> : null}
            <table className="topics">
              <tbody>
                {b.topics?.map((t, i) => (
                  <tr key={i}>
                    <th>{t.topic.replace(/_/g, ' ')}</th>
                    <td>{t.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {b.semantic_summary ? (
              <p className="baseline-summary">{b.semantic_summary}</p>
            ) : null}
          </div>
        ) : null}
      </section>

      {/* ---------------- HISTORY ---------------- */}
      <section className="wd-history">
        <h2>Change history</h2>
        {history === null ? (
          <Spinner label="Loading history…" />
        ) : history.length === 0 ? (
          <Empty title="No history yet" hint="Create a baseline to start the timeline." />
        ) : (
          <ul className="hist-list">
            {history.map((r) => (
              <HistoryItem key={r.check_id} rec={r} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function clsTone(cls?: string): string {
  switch (cls) {
    case 'MATERIAL_CHANGE':
      return 'bad';
    case 'MINOR_CHANGE':
      return 'info';
    case 'NO_CHANGE':
      return 'ok';
    case 'SOURCE_UNAVAILABLE':
      return 'warn';
    case 'UNCERTAIN':
      return 'muted';
    default:
      return 'muted';
  }
}
