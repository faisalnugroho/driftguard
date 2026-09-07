/**
 * App state store: a minimal React context wiring either the LIVE
 * GenLayer contract (default) or the clearly-labeled DEMO simulation.
 * All on-chain mutations run through the full tx lifecycle
 * (sendWrite with FINALIZED + execution-result checking).
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import type {
  Watch,
  HistoryRecord,
  Stats,
  ContractInfo,
  WalletInfo,
} from './types';
import * as chain from './chain';
import * as demo from './demo';

export type NetKind = 'live' | 'demo';
export type Route =
  | { page: 'dashboard' }
  | { page: 'create' }
  | { page: 'watch'; id: string };

interface AppState {
  net: NetKind;
  route: Route;
  go: (r: Route) => void;
  setNet: (n: NetKind) => void;
  contract: string;
  setContractAddress: (addr: string) => void;
  wallets: WalletInfo[];
  activeWallet: WalletInfo | null;
  newWallet: () => WalletInfo;
  importWallet: (pk: string) => void;
  selectWallet: (idx: number) => void;
  faucet: () => Promise<void>;
  listWatches: () => Promise<Watch[]>;
  getWatch: (id: string) => Promise<Watch>;
  getHistory: (id: string) => Promise<HistoryRecord[]>;
  stats: () => Promise<Stats>;
  contractInfo: () => Promise<ContractInfo>;
  createWatch: (name: string, url: string, criteria: string) => Promise<string>;
  createBaseline: (id: string) => Promise<Record<string, unknown>>;
  checkWatch: (id: string) => Promise<Record<string, unknown>>;
  promoteBaseline: (id: string) => Promise<Record<string, unknown>>;
  deactivateWatch: (id: string) => Promise<Record<string, unknown>>;
  activateWatch: (id: string) => Promise<Record<string, unknown>>;
  updateCriteria: (id: string, criteria: string) => Promise<Record<string, unknown>>;
  busy: string | null;
  setBusy: (s: string | null) => void;
  toast: { msg: string; err?: boolean } | null;
  notify: (msg: string, err?: boolean) => void;
}

const Ctx = createContext<AppState | null>(null);

const WKEY = 'driftguard_wallets';

function parseJsonSafe(s: any): any {
  if (typeof s !== 'string') return s;
  try {
    return JSON.parse(s);
  } catch {
    return s;
  }
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [net, setNet] = useState<NetKind>('live');
  const [route, setRoute] = useState<Route>({ page: 'dashboard' });
  const [contract, setContract] = useState<string>(
    (window as any).DRIFTGUARD_CONTRACT || ''
  );
  const [wallets, setWallets] = useState<WalletInfo[]>(() => {
    try {
      const raw = localStorage.getItem(WKEY);
      if (!raw) return [];
      const saved: Array<{ name: string; pk: string }> = JSON.parse(raw);
      return saved.map((w) => {
        const account = chain.createAccount(w.pk);
        return { ...w, address: (account as any).address, account };
      });
    } catch {
      return [];
    }
  });
  const [activeIdx, setActiveIdx] = useState<number>(() => {
    const v = Number(localStorage.getItem(WKEY + '_active'));
    return isFinite(v) && v >= 0 ? v : -1;
  });
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; err?: boolean } | null>(null);

  useEffect(() => {
    localStorage.setItem(
      WKEY,
      JSON.stringify(wallets.map((w) => ({ name: w.name, pk: w.pk })))
    );
    localStorage.setItem(WKEY + '_active', String(activeIdx));
  }, [wallets, activeIdx]);

  const notify = useCallback((msg: string, err?: boolean) => {
    setToast({ msg, err });
    window.setTimeout(() => setToast(null), 4500);
  }, []);

  const go = useCallback((r: Route) => {
    setRoute(r);
    window.scrollTo({ top: 0 });
  }, []);

  const activeWallet = activeIdx >= 0 ? wallets[activeIdx] ?? null : null;

  const newWallet = useCallback((): WalletInfo => {
    const pk = chain.generatePrivateKey();
    const account = chain.createAccount(pk);
    const w: WalletInfo = {
      name: 'Wallet ' + (wallets.length + 1),
      pk,
      address: (account as any).address,
      account,
    };
    setWallets((prev) => {
      const next = [...prev, w];
      setActiveIdx(next.length - 1);
      return next;
    });
    return w;
  }, [wallets.length]);

  const importWallet = useCallback((pk: string) => {
    const clean = pk.trim().startsWith('0x') ? pk.trim() : '0x' + pk.trim();
    const account = chain.createAccount(clean);
    const w: WalletInfo = {
      name: 'Imported',
      pk: clean,
      address: (account as any).address,
      account,
    };
    setWallets((prev) => {
      const next = [...prev, w];
      setActiveIdx(next.length - 1);
      return next;
    });
  }, []);

  const selectWallet = useCallback(
    (idx: number) => setActiveIdx(idx),
    []
  );

  const faucet = useCallback(async () => {
    if (!activeWallet) throw new Error('No wallet selected');
    await chain.fundAccount(activeWallet.address);
  }, [activeWallet]);

  /* ---------------- data access (live | demo) ---------------- */

  const api = useMemo(() => {
    if (net === 'demo') {
      return {
        listWatches: async () => demo.demoListWatches(),
        getWatch: async (id: string) => {
          const w = demo.demoGetWatch(id);
          if (!w) throw new Error('watch_not_found');
          return w;
        },
        getHistory: async (id: string) => demo.demoGetHistory(id),
        stats: async () => demo.demoStats(),
        contractInfo: async () => demo.demoContractInfo(),
        createWatch: async (name: string, url: string, criteria: string) =>
          demo.demoCreateWatch(name, url, criteria),
        createBaseline: async (id: string) => demo.demoCreateBaseline(id),
        checkWatch: async (id: string) => {
          await new Promise((r) => setTimeout(r, 1500));
          return demo.demoRunCheck(id) as unknown as Record<string, unknown>;
        },
        promoteBaseline: async (id: string) => demo.demoPromoteBaseline(id),
        deactivateWatch: async (id: string) => {
          demo.demoToggleWatch(id, false);
          return { watch_id: id, active: false };
        },
        activateWatch: async (id: string) => {
          demo.demoToggleWatch(id, true);
          return { watch_id: id, active: true };
        },
        updateCriteria: async (id: string, criteria: string) => {
          demo.demoUpdateCriteria(id, criteria);
          return { watch_id: id, criteria };
        },
      };
    }
    const addr = contract;
    const requireAddr = () => {
      if (!/^0x[0-9a-fA-F]{40}$/.test(addr)) {
        throw new Error(
          'Contract not deployed yet — no DriftGuard contract address is configured. Switch to DEMO MODE to explore the UI.'
        );
      }
      return addr;
    };
    const live = {
      listWatches: async (): Promise<Watch[]> => {
        const a = requireAddr();
        const raw = parseJsonSafe(
          await chain.readContract(a, 'list_watches', [50, 0])
        );
        return raw?.watches ?? [];
      },
      getWatch: async (id: string): Promise<Watch> => {
        const a = requireAddr();
        const raw = parseJsonSafe(
          await chain.readContract(a, 'get_watch', [Number(id)])
        );
        if (raw?.error) throw new Error('not found');
        return raw;
      },
      getHistory: async (id: string): Promise<HistoryRecord[]> => {
        const a = requireAddr();
        const raw = parseJsonSafe(
          await chain.readContract(a, 'get_history', [Number(id), 50, 0])
        );
        return raw?.records ?? [];
      },
      stats: async (): Promise<Stats> => {
        const a = requireAddr();
        return parseJsonSafe(await chain.readContract(a, 'get_stats', []));
      },
      contractInfo: async (): Promise<ContractInfo> => {
        const a = requireAddr();
        return parseJsonSafe(await chain.readContract(a, 'get_contract_info', []));
      },
      createWatch: async (name: string, url: string, criteria: string) => {
        const a = requireAddr();
        const w = activeWallet;
        if (!w) throw new Error('No wallet connected — create a signer first');
        const res = await chain.sendWrite(
          a,
          'create_watch',
          [name, url, criteria],
          w.account,
          'Create watch',
          setBusy
        );
        const vid = Number((res.receipt as any)?.data?.result ?? 0);
        // also try decode from calldata via a count read
        if (!vid) {
          const cnt = parseJsonSafe(await chain.readContract(a, 'get_watch_count', []));
          return String(cnt ?? 0);
        }
        return String(vid);
      },
      createBaseline: async (id: string) => {
        const a = requireAddr();
        const w = activeWallet;
        if (!w) throw new Error('No wallet connected');
        const res = await chain.sendWrite(
          a,
          'create_baseline',
          [Number(id)],
          w.account,
          'Create baseline',
          setBusy
        );
        const raw = (res.receipt as any)?.data?.result;
        return parseJsonSafe(typeof raw === 'string' ? raw : raw ?? {});
      },
      checkWatch: async (id: string) => {
        const a = requireAddr();
        const w = activeWallet;
        if (!w) throw new Error('No wallet connected');
        const res = await chain.sendWrite(
          a,
          'check_watch',
          [Number(id)],
          w.account,
          'Check watch',
          setBusy
        );
        const raw = (res.receipt as any)?.data?.result;
        return parseJsonSafe(typeof raw === 'string' ? raw : raw ?? {});
      },
      promoteBaseline: async (id: string) => {
        const a = requireAddr();
        const w = activeWallet;
        if (!w) throw new Error('No wallet connected');
        const res = await chain.sendWrite(
          a,
          'promote_baseline',
          [Number(id)],
          w.account,
          'Promote baseline',
          setBusy
        );
        const raw = (res.receipt as any)?.data?.result;
        return parseJsonSafe(typeof raw === 'string' ? raw : raw ?? {});
      },
      deactivateWatch: async (id: string) => {
        const a = requireAddr();
        const w = activeWallet;
        if (!w) throw new Error('No wallet connected');
        const res = await chain.sendWrite(
          a,
          'deactivate_watch',
          [Number(id)],
          w.account,
          'Pause watch',
          setBusy
        );
        const raw = (res.receipt as any)?.data?.result;
        return parseJsonSafe(typeof raw === 'string' ? raw : raw ?? {});
      },
      activateWatch: async (id: string) => {
        const a = requireAddr();
        const w = activeWallet;
        if (!w) throw new Error('No wallet connected');
        const res = await chain.sendWrite(
          a,
          'activate_watch',
          [Number(id)],
          w.account,
          'Resume watch',
          setBusy
        );
        const raw = (res.receipt as any)?.data?.result;
        return parseJsonSafe(typeof raw === 'string' ? raw : raw ?? {});
      },
      updateCriteria: async (id: string, criteria: string) => {
        const a = requireAddr();
        const w = activeWallet;
        if (!w) throw new Error('No wallet connected');
        const res = await chain.sendWrite(
          a,
          'update_criteria',
          [Number(id), criteria],
          w.account,
          'Update criteria',
          setBusy
        );
        const raw = (res.receipt as any)?.data?.result;
        return parseJsonSafe(typeof raw === 'string' ? raw : raw ?? {});
      },
    };
    // Finalization fix (Sep 2026): every live async operation MUST clear
    // the global busy overlay when it settles. v1 left `busy` set forever
    // after the first consensus wait, freezing the whole UI behind the
    // BusyOverlay. Wrap every function-valued member so busy is always
    // cleared in a finally — regardless of success, user error, or a
    // consensus revert.
    const guarded: Record<string, unknown> = {};
    for (const k of Object.keys(live)) {
      const v = (live as Record<string, unknown>)[k];
      if (typeof v === 'function') {
        guarded[k] = async (...args: unknown[]) => {
          try {
            return await (v as (...a: unknown[]) => unknown)(...args);
          } finally {
            setBusy(null);
          }
        };
      } else {
        guarded[k] = v;
      }
    }
    return guarded as unknown as typeof live;
  }, [net, contract, activeWallet]);

  const value: AppState = {
    net,
    route,
    go,
    setNet: (n) => {
      setNet(n);
      setRoute({ page: 'dashboard' });
    },
    contract,
    setContractAddress: setContract,
    wallets,
    activeWallet,
    newWallet,
    importWallet,
    selectWallet,
    faucet,
    busy,
    setBusy,
    toast,
    notify,
    ...api,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp outside provider');
  return v;
}
