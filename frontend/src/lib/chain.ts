/* eslint-disable @typescript-eslint/no-explicit-any */

export interface WriteResult {
  txHash: string;
  receipt: any;
}

/**
 * GenLayer SDK client bridge (window.GenLayerSDK) + the full
 * transaction lifecycle with FINALIZED + execution-result checking,
 * ported from the battle-tested AgentProof/TrustReconciler pattern
 * (Sep 2026). All chain access goes through this module; the UI never
 * talks to the RPC directly.
 *
 * Busy-state contract (finalization fix, Sep 2026):
 * onStatus may be called with a string (status message) — the caller
 * keeps a busy overlay visible while sendWrite is awaited. sendWrite
 * NEVER leaves the caller hanging: every terminal path (success,
 * user-facing error, guard revert) returns or throws, and the CALLER
 * clears busy in its own finally. Because a live consensus round can
 * exceed 12+ minutes under load (observed: create_watch finalized 13
 * minutes after send), the wait budgets here are generous and the
 * fallback poll keeps running rather than giving up early.
 */

const SDK = (window as any).GenLayerSDK;

export const CHAIN = SDK?.studionet ?? null;
export const EXPLORER_ADDR = 'https://explorer-studio.genlayer.com/address/';
export const EXPLORER_TX = 'https://explorer-studio.genlayer.com/tx/';

export const hasSDK = typeof SDK !== 'undefined' && !!SDK.createClient;

let client: any = null;

export function getClient(): any {
  if (!hasSDK) throw new Error('GenLayer SDK bundle not loaded');
  if (!client) client = SDK.createClient({ chain: SDK.studionet });
  return client;
}

export function createAccount(pk: string): any {
  return SDK.createAccount(pk);
}

export function generatePrivateKey(): string {
  return SDK.generatePrivateKey();
}

export async function fundAccount(address: string): Promise<void> {
  await getClient().request({
    method: 'sim_fundAccount',
    params: [address, 5e18],
  });
}

/* ---------------- retry ---------------- */

export async function withRetry<T>(
  fn: () => Promise<T>,
  attempts: number,
  label: string,
  onRetry?: (msg: string) => void
): Promise<T> {
  let lastErr: unknown;
  for (let i = 1; i <= attempts; i++) {
    try {
      return await fn();
    } catch (e: any) {
      lastErr = e;
      const msg = String(e?.message || e);
      const transient =
        /failed to fetch|network|timeout|rate|429|503|econn|socket|502/i.test(
          msg
        );
      if (!transient || i === attempts) throw e;
      const wait = 3000 * i;
      onRetry?.(`Retrying ${label} (${i}/${attempts}) after ${wait / 1000}s — ${msg.slice(0, 80)}`);
      await new Promise((res) => setTimeout(res, wait));
    }
  }
  throw lastErr;
}

export async function readContract(
  address: string,
  fn: string,
  args: any[] = [],
  account?: unknown
): Promise<any> {
  return withRetry(
    () =>
      getClient().readContract({
        address,
        functionName: fn,
        args,
        ...(account ? { account } : {}),
      }),
    4,
      'read ' + fn
  );
}

/* ---------------- receipt helpers ---------------- */

function txStatusName(r: any): string {
  if (!r) return '';
  return String(
    r.status?.status ?? r.status ?? r.result_name ?? ''
  );
}

async function fetchReceipt(txHash: string): Promise<any> {
  const c = getClient();
  if (typeof c.getTransactionReceipt === 'function') {
    try {
      return await c.getTransactionReceipt({ hash: txHash });
    } catch (e: any) {
      if (!/not ?found/i.test(String(e?.message || e))) throw e;
      return null;
    }
  }
  try {
    return await c.request({
      method: 'eth_getTransactionReceipt',
      params: [txHash],
    });
  } catch {
    return null;
  }
}

function receiptExecutionError(receipt: any, label: string): Error | null {
  const leader = receipt?.consensus_data?.leader_receipt;
  const lead = Array.isArray(leader) && leader.length ? leader[0] : null;
  if (!lead) return null;
  if (lead.execution_result === 'FAILURE' || lead.execution_result === 'ERROR') {
    const stderr = String(lead.genvm_result?.stderr || '');
    const contractErr = (stderr.match(/AssertionError: (.+)/) || [])[1];
    return new Error(
      contractErr
        ? `${label} rejected: ${contractErr}`
        : `${label} reached consensus but reverted on chain`
    );
  }
  return null;
}

/* ---------------- full tx lifecycle ---------------- */

// Observed live (Sep 2026): consensus rounds can take 13+ minutes under
// validator-set churn. The SDK poll gets 10 minutes; the raw-receipt
// fallback poll then runs up to ANOTHER 20 minutes before giving up.
const TX_FINAL_WAIT_MS = 10 * 60 * 1000;
const TX_FALLBACK_WAIT_MS = 20 * 60 * 1000;
const TERMINAL_NOT_FINAL = [
  'UNDETERMINED',
  'CANCELED',
  'LEADER_TIMEOUT',
  'VALIDATORS_TIMEOUT',
];

export async function sendWrite(
  address: string,
  fn: string,
  args: any[],
  account: unknown,
  label: string,
  onStatus?: (msg: string) => void
): Promise<WriteResult> {
  const c = getClient();
  const txHash: string = await withRetry(
    () =>
      c.writeContract({
        address,
        functionName: fn,
        args,
        account,
      }),
    5,
    'send ' + fn,
    onStatus
  );
  onStatus?.(
    `Transaction sent (${txHash.slice(0, 18)}…) — waiting for validator consensus (typically 1–3 min, up to 15 under load). Validators are independently retrieving the source right now. Explorer: ${EXPLORER_TX}${txHash}`
  );
  let receipt: any = null;
  try {
    receipt = await Promise.race([
      c.waitForTransactionReceipt({
        hash: txHash,
        status: SDK.TransactionStatus.FINALIZED,
        interval: 5000,
        retries: 120,
      }),
      new Promise((_, rej) =>
        setTimeout(() => rej(new Error('TX_FINAL_WAIT_TIMEOUT')), TX_FINAL_WAIT_MS)
      ),
    ]);
  } catch (e: any) {
    const msg = String(e?.message || e);
    if (!/TX_FINAL_WAIT_TIMEOUT/.test(msg)) throw e;
    onStatus?.('Receipt wait timed out — polling the transaction until FINALIZED…');
    const deadline = Date.now() + TX_FALLBACK_WAIT_MS;
    while (Date.now() < deadline) {
      let r: any = null;
      try {
        r = await fetchReceipt(txHash);
      } catch {}
      const st = txStatusName(r);
      if (st === 'FINALIZED') {
        receipt = r;
        break;
      }
      if (TERMINAL_NOT_FINAL.includes(st)) {
        throw new Error(
          `${label} ended in consensus status ${st} — nothing was committed (tx ${txHash.slice(0, 18)}…). The previous accepted state is untouched; you can retry.`
        );
      }
      await new Promise((res) => setTimeout(res, 10000));
    }
    if (!receipt)
      throw new Error(
        `Could not confirm FINALIZED for ${label} within 30 min (tx ${txHash.slice(0, 18)}…) — check it on the explorer: ${EXPLORER_TX}${txHash}`
      );
  }
  const execErr = receiptExecutionError(receipt, label);
  if (execErr) throw execErr;
  return { txHash, receipt };
}
