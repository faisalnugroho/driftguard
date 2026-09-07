/**
 * DriftGuard DEMO MODE — deterministic local simulation, FRONTEND
 * TESTING ONLY.
 *
 * IMPORTANT: demo mode never contacts GenLayer. Its results are
 * produced by a deterministic local script, NOT by validator
 * consensus, and every screen in demo mode is labeled "DEMO MODE".
 * The real application path always goes through the live Intelligent
 * Contract.
 *
 * The simulation mirrors the contract's own logic shape (fetch gate ->
 * semantic extraction -> classification) so UI behavior can be
 * exercised without consensus cost. It is not a replacement for the
 * contract and makes no pretense of being decentralized.
 */

import type {
  Watch,
  HistoryRecord,
  Stats,
  ContractInfo,
  Topic,
  Change,
  Baseline,
} from './types';

const DEMO_T0 = 1757111400; // fixed epoch for determinism
const DEMO_TICK = 3600; // 1h per simulated event

interface DemoPage {
  status: number;
  text: string;
}

/** A tiny mutable "web" for demo watches: one page per watch id. */
const demoPages = new Map<string, DemoPage>();

export const DEMO_SAMPLE_WATCHES: Array<{
  name: string;
  url: string;
  criteria: string;
  script: 'refund30' | 'apiDocs' | 'unreachable';
}> = [
  {
    name: 'Storefront refund policy',
    url: 'https://demo-store.driftguard.example/refund-policy',
    criteria:
      'Monitor refund window, restocking fee, eligibility rules and request deadlines.',
    script: 'refund30',
  },
  {
    name: 'Payments API documentation',
    url: 'https://demo-api.driftguard.example/terms',
    criteria:
      'Monitor authentication requirements, rate limits, endpoints and breaking changes.',
    script: 'apiDocs',
  },
  {
    name: 'Archived vendor portal',
    url: 'https://demo-down.driftguard.example/portal',
    criteria: 'Monitor availability of the vendor terms page.',
    script: 'unreachable',
  },
];

const REFUND_30 = [
  { topic: 'refund_window', value: '30 days' },
  { topic: 'restocking_fee', value: '$5' },
  { topic: 'eligibility', value: 'unused items in original packaging' },
  { topic: 'request_deadline', value: 'before end of 30-day window' },
];
const REFUND_14 = [
  { topic: 'refund_window', value: '14 days' },
  { topic: 'restocking_fee', value: '$5' },
  { topic: 'eligibility', value: 'unused items in original packaging' },
  { topic: 'request_deadline', value: 'before end of 14-day window' },
];
const API_V1 = [
  { topic: 'authentication', value: 'API key in Authorization header' },
  { topic: 'rate_limit', value: '600 requests per minute' },
  { topic: 'base_endpoint', value: 'https://api.demo.example/v1' },
  { topic: 'pagination', value: 'cursor-based, 100 per page' },
];
const API_V2 = [
  { topic: 'authentication', value: 'OAuth 2.0 client credentials' },
  { topic: 'rate_limit', value: '120 requests per minute' },
  { topic: 'base_endpoint', value: 'https://api.demo.example/v2' },
  { topic: 'deprecation', value: 'v1 sunset on 2027-01-31' },
];

function scriptPage(script: string): { status: number; topics: Topic[]; title: string } {
  if (script === 'refund30') {
    // The refund watch's "site" drifts after its second check.
    const checks = demoChecks.get('1') ?? 0;
    if (checks >= 2) {
      return { status: 200, topics: REFUND_14, title: 'Refund Policy' };
    }
    return { status: 200, topics: REFUND_30, title: 'Refund Policy' };
  }
  if (script === 'apiDocs') {
    const checks = demoChecks.get('2') ?? 0;
    if (checks >= 3) {
      return { status: 200, topics: API_V2, title: 'API Terms' };
    }
    return { status: 200, topics: API_V1, title: 'API Terms' };
  }
  return { status: 0, topics: [], title: '' }; // unreachable
}

const demoChecks = new Map<string, number>();

/* -------------- demo store: same shapes as the contract -------------- */

let demoWatches: Watch[] = [];
let demoHistory: HistoryRecord[] = [];
let demoClock = DEMO_T0;
let demoCheckCounter = 0;

function demoFingerprint(topics: Topic[], title: string): string {
  // A stable, obviously-fake hex fingerprint (deterministic).
  const payload = title + '|' + topics.map((t) => `${t.topic}=${t.value}`).sort().join('|');
  let h = 0x811c9dc5;
  for (let i = 0; i < payload.length; i++) {
    h ^= payload.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  let s = h.toString(16);
  while (s.length < 16) s = '0' + s;
  // mark it visually as demo
  return s;
}

export function demoSeed(): void {
  demoWatches = [];
  demoHistory = [];
  demoClock = DEMO_T0;
  demoCheckCounter = 0;
  demoChecks.clear();
  for (const s of DEMO_SAMPLE_WATCHES) {
    const wid = String(demoWatches.length + 1);
    const w: Watch = {
      watch_id: wid,
      name: s.name,
      url: s.url,
      criteria: s.criteria,
      active: true,
      created_at: String(demoClock),
      owner: '0xDemoWallet000000000000000000000000000demo',
      baseline: null,
      baseline_created_at: '',
      latest_status: '',
      latest_source_status: '',
      latest_fingerprint: '',
      latest_summary: '',
      latest_state: null,
      last_explanation: '',
      last_changed_topics: [],
      last_changes: [],
      last_checked_at: '',
      total_checks: 0,
      material_changes: 0,
    };
    demoWatches.push(w);
    // baseline for the reachable ones
    if (s.script !== 'unreachable') {
      const page = scriptPage(s.script);
      const b: Baseline = {
        source_status: 'AVAILABLE',
        title: page.title,
        topics: page.topics,
        semantic_summary: 'Baseline accepted in demo mode.',
        fingerprint: demoFingerprint(page.topics, page.title),
      };
      w.baseline = b;
      w.baseline_created_at = String(demoClock);
      demoCheckCounter += 1;
      demoHistory.unshift({
        check_id: String(demoCheckCounter),
        watch_id: wid,
        classification: 'BASELINE_CREATED',
        source_status: 'AVAILABLE',
        previous_fingerprint: '',
        current_fingerprint: b.fingerprint,
        changed_topics: [],
        changes: [],
        summary: b.semantic_summary,
        explanation: 'Initial semantic baseline accepted (DEMO simulation).',
        checked_at: String(demoClock),
      });
    }
    demoClock += DEMO_TICK;
  }
  // pre-run a couple of checks on watch 1 for a richer timeline
  demoRunCheck('1');
  demoClock += DEMO_TICK;
  demoRunCheck('1');
  demoClock += DEMO_TICK;
}

export function demoRunCheck(watchId: string): HistoryRecord {
  const w = demoWatches.find((x) => x.watch_id === watchId);
  if (!w) throw new Error('watch_not_found');
  if (!w.active) throw new Error('watch_inactive');
  if (!w.baseline) throw new Error('no_baseline');
  const n = (demoChecks.get(watchId) ?? 0) + 1;
  demoChecks.set(watchId, n);
  demoCheckCounter += 1;
  demoClock += DEMO_TICK;

  const script =
    watchId === '1' ? 'refund30' : watchId === '2' ? 'apiDocs' : 'unreachable';
  const page = scriptPage(script);

  let rec: HistoryRecord;
  if (page.status !== 200) {
    rec = {
      check_id: String(demoCheckCounter),
      watch_id: watchId,
      classification: 'SOURCE_UNAVAILABLE',
      source_status: 'UNAVAILABLE',
      previous_fingerprint: w.baseline.fingerprint,
      current_fingerprint: '',
      changed_topics: [],
      changes: [],
      summary: '',
      explanation: 'The source could not be retrieved (simulated HTTP failure).',
      confidence: 100,
      checked_at: String(demoClock),
    };
    w.latest_status = 'SOURCE_UNAVAILABLE';
    w.latest_source_status = 'UNAVAILABLE';
    w.last_explanation = rec.explanation;
    w.last_checked_at = String(demoClock);
  } else {
    // diff against baseline
    const prev = new Map(w.baseline!.topics.map((t) => [t.topic, t.value]));
    const changes: Change[] = [];
    for (const t of page.topics) {
      const before = prev.get(t.topic);
      if (before !== undefined && before !== t.value) {
        changes.push({ topic: t.topic, previous: before, current: t.value });
      }
    }
    const cls =
      changes.length > 0
        ? 'MATERIAL_CHANGE'
        : n % 4 === 0
          ? 'MINOR_CHANGE'
          : 'NO_CHANGE';
    const fingerprint = demoFingerprint(page.topics, page.title);
    rec = {
      check_id: String(demoCheckCounter),
      watch_id: watchId,
      classification: cls,
      source_status: 'AVAILABLE',
      previous_fingerprint: w.baseline!.fingerprint,
      current_fingerprint: fingerprint,
      changed_topics: changes.map((c) => c.topic),
      changes,
      summary: 'Demo simulation of an accepted semantic observation.',
      explanation:
        changes.length > 0
          ? changes
              .map(
                (c) =>
                  `${c.topic.replace(/_/g, ' ')}: ${c.previous} → ${c.current}`
              )
              .join('; ')
          : cls === 'MINOR_CHANGE'
            ? 'Wording changed without affecting the monitored meaning.'
            : 'No material semantic change detected.',
      confidence: 90,
      checked_at: String(demoClock),
    };
    w.latest_status = cls;
    w.latest_source_status = 'AVAILABLE';
    w.latest_fingerprint = fingerprint;
    w.last_explanation = rec.explanation;
    w.last_changed_topics = rec.changed_topics;
    w.last_changes = changes;
    w.last_checked_at = String(demoClock);
    w.latest_state = {
      source_status: 'AVAILABLE',
      title: page.title,
      topics: page.topics,
      semantic_summary: rec.summary,
      fingerprint,
    };
    if (cls === 'MATERIAL_CHANGE') w.material_changes += 1;
  }
  w.total_checks += 1;
  demoHistory.unshift(rec);
  return rec;
}

export function demoListWatches(): Watch[] {
  return demoWatches.map((w) => ({
    ...w,
    history_ids: demoHistory
      .filter((h) => h.watch_id === w.watch_id)
      .map((h) => Number(h.check_id)),
  }));
}

export function demoGetWatch(id: string): Watch | undefined {
  return demoListWatches().find((w) => w.watch_id === id);
}

export function demoGetHistory(watchId: string): HistoryRecord[] {
  return demoHistory.filter((h) => h.watch_id === watchId);
}

export function demoStats(): Stats {
  return {
    total_watches: demoWatches.length,
    active_watches: demoWatches.filter((w) => w.active).length,
    total_checks: demoHistory.filter((h) =>
      ['NO_CHANGE', 'MINOR_CHANGE', 'MATERIAL_CHANGE', 'SOURCE_UNAVAILABLE', 'UNCERTAIN'].includes(
        h.classification
      )
    ).length,
    material_changes: demoWatches.reduce((a, w) => a + w.material_changes, 0),
    uncertain_checks: demoHistory.filter((h) => h.classification === 'UNCERTAIN').length,
    unavailable_checks: demoHistory.filter(
      (h) => h.classification === 'SOURCE_UNAVAILABLE'
    ).length,
  };
}

export function demoContractInfo(): ContractInfo {
  return {
    name: 'DRIFTGUARD',
    tagline: 'Trustless semantic change detection for the open web.',
    protocol_version: '1.0 (demo simulation)',
    owner: '0xDemoWallet000000000000000000000000000demo',
    classifications: [
      'NO_CHANGE',
      'MINOR_CHANGE',
      'MATERIAL_CHANGE',
      'SOURCE_UNAVAILABLE',
      'UNCERTAIN',
    ],
    equivalence_matrix: {
      NO_CHANGE: ['NO_CHANGE', 'MINOR_CHANGE'],
      MINOR_CHANGE: ['NO_CHANGE', 'MINOR_CHANGE'],
      MATERIAL_CHANGE: ['MATERIAL_CHANGE'],
      SOURCE_UNAVAILABLE: ['SOURCE_UNAVAILABLE'],
      UNCERTAIN: ['UNCERTAIN'],
    },
    policy: {
      check_cooldown_seconds: 180,
      baseline_topic_match_pct: 60,
      comparative_cap: 6,
      max_content_chars: 12000,
      min_text_chars: 40,
    },
    stats: demoStats(),
  };
}

export function demoCreateWatch(name: string, url: string, criteria: string): string {
  const wid = String(demoWatches.length + 1);
  demoClock += 60;
  const w: Watch = {
    watch_id: wid,
    name,
    url,
    criteria,
    active: true,
    created_at: String(demoClock),
    owner: '0xDemoWallet000000000000000000000000000demo',
    baseline: null,
    baseline_created_at: '',
    latest_status: '',
    latest_source_status: '',
    latest_fingerprint: '',
    latest_summary: '',
    latest_state: null,
    last_explanation: '',
    last_changed_topics: [],
    last_changes: [],
    last_checked_at: '',
    total_checks: 0,
    material_changes: 0,
  };
  demoWatches.push(w);
  demoPages.set(wid, { status: 200, text: 'demo page' });
  return wid;
}

export function demoCreateBaseline(watchId: string): Record<string, unknown> {
  const w = demoWatches.find((x) => x.watch_id === watchId);
  if (!w) throw new Error('watch_not_found');
  if (watchId === '3') {
    return {
      watch_id: watchId,
      baseline_created: false,
      source_status: 'UNAVAILABLE',
      reason: 'SOURCE_UNAVAILABLE',
      checked_at: String(demoClock),
    };
  }
  const script =
    watchId === '1' ? 'refund30' : watchId === '2' ? 'apiDocs' : 'unreachable';
  const page = scriptPage(script);
  const b: Baseline = {
    source_status: 'AVAILABLE',
    title: page.title,
    topics: page.topics,
    semantic_summary: 'Baseline accepted in demo mode.',
    fingerprint: demoFingerprint(page.topics, page.title),
  };
  w.baseline = b;
  w.baseline_created_at = String(demoClock);
  demoCheckCounter += 1;
  demoClock += DEMO_TICK;
  demoHistory.unshift({
    check_id: String(demoCheckCounter),
    watch_id: watchId,
    classification: 'BASELINE_CREATED',
    source_status: 'AVAILABLE',
    previous_fingerprint: '',
    current_fingerprint: b.fingerprint,
    changed_topics: [],
    changes: [],
    summary: b.semantic_summary,
    explanation: 'Initial semantic baseline accepted (DEMO simulation).',
    checked_at: String(demoClock),
  });
  return {
    watch_id: watchId,
    baseline_created: true,
    source_status: 'AVAILABLE',
    fingerprint: b.fingerprint,
    title: b.title,
    topics: b.topics,
    semantic_summary: b.semantic_summary,
    checked_at: String(demoClock),
  };
}

export function demoPromoteBaseline(watchId: string): Record<string, unknown> {
  const w = demoWatches.find((x) => x.watch_id === watchId);
  if (!w) throw new Error('watch_not_found');
  if (!w.latest_state) throw new Error('no_accepted_latest_state');
  const prev = w.baseline?.fingerprint ?? '';
  w.baseline = w.latest_state;
  demoCheckCounter += 1;
  demoClock += DEMO_TICK;
  demoHistory.unshift({
    check_id: String(demoCheckCounter),
    watch_id: watchId,
    classification: 'BASELINE_PROMOTED',
    source_status: 'AVAILABLE',
    previous_fingerprint: prev,
    current_fingerprint: w.latest_state.fingerprint,
    changed_topics: [],
    changes: [],
    summary: w.latest_state.semantic_summary,
    explanation: 'Latest accepted semantic state promoted to baseline (DEMO simulation).',
    checked_at: String(demoClock),
  });
  return {
    watch_id: watchId,
    promoted: true,
    fingerprint: w.latest_state.fingerprint,
    checked_at: String(demoClock),
  };
}

export function demoToggleWatch(watchId: string, active: boolean): void {
  const w = demoWatches.find((x) => x.watch_id === watchId);
  if (!w) throw new Error('watch_not_found');
  w.active = active;
}

export function demoUpdateCriteria(watchId: string, criteria: string): void {
  const w = demoWatches.find((x) => x.watch_id === watchId);
  if (!w) throw new Error('watch_not_found');
  w.criteria = criteria;
}
