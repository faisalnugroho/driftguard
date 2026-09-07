import React from 'react';
import { CLASS_META, SOURCE_META, type HistoryType } from '../lib/types';

export function Badge({
  kind,
  children,
}: {
  kind: 'ok' | 'info' | 'warn' | 'bad' | 'muted';
  children: React.ReactNode;
}) {
  return <span className={`badge tone-${kind}`}>{children}</span>;
}

export function ClassBadge({ cls }: { cls: string }) {
  const meta = CLASS_META[cls];
  if (!meta) return <span className="badge tone-muted">{cls || '—'}</span>;
  return (
    <span className={`badge tone-${meta.tone}`} title={meta.blurb}>
      {meta.label.toUpperCase().replace(/ /g, '_')}
    </span>
  );
}

export function SourceBadge({ status }: { status: string }) {
  const meta = SOURCE_META[status] ?? {
    label: status || '—',
    tone: 'muted' as const,
  };
  return <span className={`badge tone-${meta.tone}`}>{meta.label}</span>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="spinner-wrap">
      <span className="spinner" aria-hidden />
      {label ? <span className="spinner-label">{label}</span> : null}
    </span>
  );
}

export function Empty({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-title">{title}</div>
      {hint ? <div className="empty-hint">{hint}</div> : null}
      {action}
    </div>
  );
}

export function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  tone?: string;
}) {
  return (
    <div className={`stat ${tone ? 'stat-' + tone : ''}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

/** The CHANGE DETECTED evidence card — the spec's key UX piece. */
export function ChangeCard({
  changes,
  explanation,
}: {
  changes: Array<{ topic: string; previous: string; current: string }>;
  explanation: string;
}) {
  if (!changes || changes.length === 0) return null;
  return (
    <div className="change-card">
      <div className="change-head">CHANGE DETECTED</div>
      {changes.map((c, i) => (
        <div className="change-row" key={i}>
          <div className="change-topic">
            Topic: <b>{c.topic.replace(/_/g, ' ')}</b>
          </div>
          <div className="change-vals">
            <div className="change-val prev">
              <span>Previous</span>
              <b>{c.previous || '—'}</b>
            </div>
            <div className="change-val curr">
              <span>Current</span>
              <b>{c.current || '—'}</b>
            </div>
          </div>
        </div>
      ))}
      <div className="change-expl">
        <span className="change-expl-label">Impact explanation</span>
        <p>{explanation}</p>
      </div>
    </div>
  );
}

export function HistoryItem({ rec }: { rec: any }) {
  const [open, setOpen] = React.useState(false);
  const isEvent = rec.classification === 'BASELINE_CREATED' || rec.classification === 'BASELINE_PROMOTED';
  const meta = CLASS_META[rec.classification as HistoryType];
  return (
    <li className={`hist-item ${open ? 'open' : ''}`}>
      <button
        className="hist-head"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="hist-date">
          {new Date(Number(rec.checked_at) * 1000).toLocaleString(undefined, {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
          })}
        </span>
        <ClassBadge cls={rec.classification} />
        <span className="hist-line">
          {isEvent
            ? meta?.blurb ?? ''
            : rec.classification === 'MATERIAL_CHANGE'
              ? firstChangeText(rec)
              : rec.classification === 'SOURCE_UNAVAILABLE'
                ? 'The source could not be retrieved'
                : rec.classification === 'UNCERTAIN'
                  ? 'Consensus could not reliably classify the change'
                  : rec.explanation || meta?.blurb || ''}
        </span>
        <span className="hist-caret" aria-hidden>
          {open ? '−' : '+'}
        </span>
      </button>
      {open ? (
        <div className="hist-body">
          <div className="hist-grid">
            <div>
              <span className="kv-label">Check ID</span>
              <span className="kv-value">#{rec.check_id}</span>
            </div>
            <div>
              <span className="kv-label">Source</span>
              <span className="kv-value">
                <SourceBadge status={rec.source_status} />
              </span>
            </div>
            <div>
              <span className="kv-label">Previous fingerprint</span>
              <span className="kv-value mono">
                {rec.previous_fingerprint || '—'}
              </span>
            </div>
            <div>
              <span className="kv-label">Current fingerprint</span>
              <span className="kv-value mono">
                {rec.current_fingerprint || '—'}
              </span>
            </div>
          </div>
          {rec.classification === 'MATERIAL_CHANGE' &&
          rec.changes &&
          rec.changes.length > 0 ? (
            <ChangeCard changes={rec.changes} explanation={rec.explanation} />
          ) : rec.explanation ? (
            <p className="hist-expl">{rec.explanation}</p>
          ) : null}
          {typeof rec.confidence === 'number' ? (
            <p className="hist-conf">Validator confidence: {rec.confidence}/100</p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

function firstChangeText(rec: any): string {
  const c = rec.changes?.[0];
  if (!c) return rec.explanation || 'Material change detected';
  return `${c.topic.replace(/_/g, ' ')} changed from ${c.previous} to ${c.current}`;
}
