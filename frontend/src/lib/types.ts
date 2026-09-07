/**
 * DriftGuard frontend shared types + classification display model.
 */

export type Classification =
  | 'NO_CHANGE'
  | 'MINOR_CHANGE'
  | 'MATERIAL_CHANGE'
  | 'SOURCE_UNAVAILABLE'
  | 'UNCERTAIN';

export type SourceStatus = 'AVAILABLE' | 'UNAVAILABLE' | 'UNCERTAIN';

export type HistoryType =
  | Classification
  | 'BASELINE_CREATED'
  | 'BASELINE_PROMOTED';

export interface Topic {
  topic: string;
  value: string;
}

export interface Change {
  topic: string;
  previous: string;
  current: string;
}

export interface Baseline {
  source_status: string;
  title: string;
  topics: Topic[];
  semantic_summary: string;
  fingerprint: string;
}

export interface Watch {
  watch_id: string;
  name: string;
  url: string;
  criteria: string;
  active: boolean;
  created_at: string;
  owner: string;
  baseline: Baseline | null;
  baseline_created_at: string;
  latest_status: string;
  latest_source_status: string;
  latest_fingerprint: string;
  latest_summary: string;
  latest_state: Baseline | null;
  last_explanation: string;
  last_changed_topics: string[];
  last_changes: Change[];
  last_checked_at: string;
  total_checks: number;
  material_changes: number;
  history_ids?: number[];
  error?: string;
}

export interface HistoryRecord {
  check_id: string;
  watch_id: string;
  classification: HistoryType;
  source_status: string;
  previous_fingerprint: string;
  current_fingerprint: string;
  changed_topics: string[];
  changes: Change[];
  summary: string;
  explanation: string;
  confidence?: number;
  checked_at: string;
}

export interface Stats {
  total_watches: number;
  active_watches: number;
  total_checks: number;
  material_changes: number;
  uncertain_checks: number;
  unavailable_checks: number;
}

export interface ContractInfo {
  name: string;
  tagline: string;
  protocol_version: string;
  owner: string;
  classifications: string[];
  equivalence_matrix: Record<string, string[]>;
  policy: {
    check_cooldown_seconds: number;
    baseline_topic_match_pct: number;
    comparative_cap: number;
    max_content_chars: number;
    min_text_chars: number;
  };
  stats: Stats;
}

export interface WalletInfo {
  name: string;
  pk: string;
  address: string;
  account: unknown;
}

/* ---------------- display model ---------------- */

export const CLASS_META: Record<
  string,
  { label: string; tone: 'ok' | 'info' | 'warn' | 'bad' | 'muted'; blurb: string }
> = {
  NO_CHANGE: {
    label: 'No change',
    tone: 'ok',
    blurb: 'No meaningful semantic change since the accepted baseline.',
  },
  MINOR_CHANGE: {
    label: 'Minor change',
    tone: 'info',
    blurb: 'The source changed, but not in a way that affects the monitored meaning.',
  },
  MATERIAL_CHANGE: {
    label: 'Material change',
    tone: 'bad',
    blurb: 'A meaningful change that could affect anyone relying on this source.',
  },
  SOURCE_UNAVAILABLE: {
    label: 'Source unavailable',
    tone: 'warn',
    blurb: 'The source could not be retrieved. This is never reported as "no change".',
  },
  UNCERTAIN: {
    label: 'Uncertain',
    tone: 'muted',
    blurb: 'Validators could not reliably determine whether the source changed.',
  },
  BASELINE_CREATED: {
    label: 'Baseline created',
    tone: 'info',
    blurb: 'Initial semantic baseline accepted by consensus.',
  },
  BASELINE_PROMOTED: {
    label: 'Baseline promoted',
    tone: 'info',
    blurb: 'The latest accepted state became the new baseline by owner decision.',
  },
};

export const SOURCE_META: Record<string, { label: string; tone: 'ok' | 'warn' | 'muted' }> = {
  AVAILABLE: { label: 'Available', tone: 'ok' },
  UNAVAILABLE: { label: 'Unavailable', tone: 'warn' },
  UNCERTAIN: { label: 'Uncertain', tone: 'muted' },
};

export function fmtDate(epochSeconds: string | number | undefined): string {
  const n = typeof epochSeconds === 'string' ? Number(epochSeconds) : epochSeconds;
  if (!n || !isFinite(n as number)) return '—';
  const d = new Date((n as number) * 1000);
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function fmtAgo(epochSeconds: string | number | undefined): string {
  const n = typeof epochSeconds === 'string' ? Number(epochSeconds) : epochSeconds;
  if (!n || !isFinite(n as number)) return 'never';
  const secs = Math.max(0, Math.floor(Date.now() / 1000 - (n as number)));
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

export function shortAddr(a?: string): string {
  return a && a.length > 12 ? `${a.slice(0, 7)}…${a.slice(-4)}` : a || '—';
}

export function shortFp(fp?: string): string {
  return fp && fp.length > 12 ? `${fp.slice(0, 8)}…${fp.slice(-4)}` : fp || '—';
}
