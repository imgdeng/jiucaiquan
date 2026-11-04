import { useEffect, useMemo, useRef, useState } from "react";
import { track } from "../lib/telemetry";
import { copyText } from "../lib/clipboard";

type AssetType = "etf" | "stock";
type WindowKey = "3m" | "6m" | "12m";

type WindowMeta = {
  key: WindowKey;
  label: string;
  minTradingDays: number;
  available: boolean;
  start: string | null;
  end: string | null;
  tradingDays: number | null;
  reason: string | null;
};

type PoolItem = {
  code: string;
  name: string;
  asset: AssetType;
  amount: number;
  summary: string;
};

type StrategyMeta = {
  id: string;
  label: string;
  holdDays: number;
  rangeMultiplier: number;
  basePriceMode: string;
};

type BacktestIndex = {
  schemaVersion: number;
  generatedAt: string;
  latestDate: string;
  dataStart: string;
  tradingDays: number;
  strategy: StrategyMeta;
  windows: WindowMeta[];
  poolStats: { total: number; etf: number; stock: number };
  pool: PoolItem[];
};

type WindowResult = {
  available: boolean;
  start: string | null;
  end: string | null;
  tradingDays: number | null;
  trades?: number;
  wins?: number;
  winRate?: number | null;
  cumReturn?: number;
  maxDrawdown?: number;
  sampleInsufficient?: boolean;
  reason?: string | null;
};

type SummaryData = {
  schemaVersion: number;
  generatedAt: string;
  code: string;
  name: string;
  asset: AssetType;
  latestDate: string;
  strategy: StrategyMeta;
  windows: Partial<Record<WindowKey, WindowResult>>;
};

/** 索引未生成时的静态档位：全部不可用，不展示任何数字 */
const STATIC_WINDOWS: WindowMeta[] = [
  { key: "3m", label: "近 3 个月", minTradingDays: 60, available: false, start: null, end: null, tradingDays: null, reason: "数据准备中" },
  { key: "6m", label: "近 6 个月", minTradingDays: 120, available: false, start: null, end: null, tradingDays: null, reason: "数据积累中" },
  { key: "12m", label: "近 12 个月", minTradingDays: 240, available: false, start: null, end: null, tradingDays: null, reason: "数据积累中" },
];

const ASSET_LABEL: Record<AssetType, string> = { etf: "ETF", stock: "个股" };

async function loadJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function formatPct(value: number | null | undefined, digits: number, withSign = false, empty = "待数据"): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return empty;
  const sign = withSign && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

function buildSummaryText(
  name: string,
  code: string,
  strategyLabel: string,
  windowLabel: string,
  result: WindowResult,
): string {
  const start = result.start ?? "";
  const end = result.end ?? "";
  const days = result.tradingDays ?? 0;
  const trades = result.trades ?? 0;
  const wins = result.wins ?? 0;
  return [
    `${name}(${code}) 回测摘要 · ${strategyLabel} · ${windowLabel}`,
    `区间：${start} ~ ${end}（${days} 个交易日）`,
    `胜率：${formatPct(result.winRate, 1)}（${wins}/${trades} 笔）`,
    `累计收益率：${formatPct(result.cumReturn, 2, true)}（等额 1 万元/笔，未计佣金与滑点）`,
    `最大回撤：${formatPct(result.maxDrawdown, 2)}`,
    `规则：次日跌至低吸价买入，达到高抛价卖出，最长持有 5 个交易日`,
    `历史表现不代表未来收益，仅供学习研究，不构成投资建议。`,
  ].join("\n");
}

export default function BacktestTool() {
  const [index, setIndex] = useState<BacktestIndex | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "pending" | "ready">("loading");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<PoolItem | null>(null);
  const [windowKey, setWindowKey] = useState<WindowKey>("3m");
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [summaryState, setSummaryState] = useState<"idle" | "loading" | "ready" | "missing">("idle");
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);

  const summaryCache = useRef(new Map<string, SummaryData>());
  const requestId = useRef(0);
  const didPageView = useRef(false);
  const lastResult = useRef("");

  // 首屏埋点（一次）
  useEffect(() => {
    if (didPageView.current) return;
    didPageView.current = true;
    track("backtest_view");
  }, []);

  // 读取预计算索引；不存在时进入「数据准备中」，不展示任何推测数字
  useEffect(() => {
    loadJson<BacktestIndex>("/data/backtest/index.json").then((data) => {
      if (!data) {
        setLoadState("pending");
        return;
      }
      setIndex(data);
      setLoadState("ready");
      const firstAvailable = data.windows.find((w) => w.available);
      if (firstAvailable) setWindowKey(firstAvailable.key);
    });
  }, []);

  const pool = index?.pool ?? [];
  const windows = index?.windows ?? STATIC_WINDOWS;

  const matches = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return pool.slice(0, 12);
    return pool
      .filter((item) => `${item.code} ${item.name}`.toLowerCase().includes(keyword))
      .slice(0, 20);
  }, [pool, query]);

  const queryHasNoMatch = query.trim().length > 0 && matches.length === 0;

  async function selectItem(item: PoolItem) {
    setSelected(item);
    setSummary(null);
    setSummaryState("loading");
    const id = ++requestId.current;
    const cached = summaryCache.current.get(item.code);
    if (cached) {
      if (id === requestId.current) {
        setSummary(cached);
        setSummaryState("ready");
      }
      return;
    }
    const data = await loadJson<SummaryData>(`/data/backtest/${item.summary}`);
    if (id !== requestId.current) return;
    if (!data) {
      setSummaryState("missing");
      return;
    }
    summaryCache.current.set(item.code, data);
    setSummary(data);
    setSummaryState("ready");
  }

  // 出结果埋点：同标的同档位只记一次
  useEffect(() => {
    if (!selected || summaryState !== "ready" || !summary) return;
    const result = summary.windows[windowKey];
    if (!result?.available) return;
    const key = `${selected.code}:${windowKey}`;
    if (lastResult.current === key) return;
    lastResult.current = key;
    track("backtest_result", { code: selected.code, asset: selected.asset, window: windowKey });
  }, [selected, summary, summaryState, windowKey]);

  const activeWindow = windows.find((w) => w.key === windowKey) ?? windows[0];
  const result = summary?.windows[windowKey];

  async function copySummary() {
    if (!selected || !summary || !result?.available) return;
    const payload = { code: selected.code, asset: selected.asset, window: windowKey };
    track("backtest_copy", payload);
    const text = buildSummaryText(
      summary.name,
      summary.code,
      summary.strategy.label,
      activeWindow.label,
      result,
    );
    const outcome = await copyText(text);
    if (outcome.ok) {
      setCopied(true);
      setCopyFailed(false);
    } else {
      track("backtest_copy_fail", { ...payload, reason: outcome.reason });
      setCopied(false);
      setCopyFailed(true);
    }
    setTimeout(() => {
      setCopied(false);
      setCopyFailed(false);
    }, 1600);
  }

  const controlsDisabled = loadState !== "ready";

  return (
    <div className="grid gap-5 lg:grid-cols-[0.95fr_1.05fr]">
      {/* 左：选标的 / 选策略 / 选区间 */}
      <section className="min-w-0 rounded-lg border border-line bg-white p-5 shadow-sm">
        <h2 className="text-xl font-bold">选择标的与区间</h2>
        <p className="mt-1 text-sm text-stone-600">
          标的池固定，按末日成交额排序（仅代表成交活跃度，不构成任何投资暗示）；不提供自由输入参数。
        </p>

        <label className="mt-5 block text-sm font-semibold" htmlFor="backtest-search">
          搜索代码或名称
        </label>
        <input
          id="backtest-search"
          className="focus-ring mt-2 min-h-[44px] w-full rounded-md border border-line px-3 py-3 disabled:bg-stone-100"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && matches[0]) selectItem(matches[0]);
          }}
          placeholder={controlsDisabled ? "标的池准备中" : "例如 510300 / 沪深300"}
          disabled={controlsDisabled}
        />

        <div className="mt-3 max-h-80 overflow-auto rounded-md border border-line">
          {loadState === "pending" ? (
            <div className="space-y-2 p-4 text-sm leading-6 text-stone-600">
              <p>回测数据准备中，标的池暂未开放。</p>
              <p>数据前置结论完成后，本页会自动读取预计算文件，无需改代码。</p>
            </div>
          ) : loadState === "loading" ? (
            <p className="p-4 text-sm text-stone-600">正在读取标的池…</p>
          ) : matches.length ? (
            matches.map((item) => (
              <button
                key={item.code}
                type="button"
                onClick={() => selectItem(item)}
                className={`grid min-h-[44px] w-full grid-cols-[1fr_auto] items-center gap-2 border-b border-line px-3 py-3 text-left last:border-b-0 hover:bg-rice ${
                  selected?.code === item.code ? "bg-rice" : ""
                }`}
              >
                <span className="min-w-0">
                  <span className="font-semibold">{item.code}</span>
                  <span className="ml-2 text-stone-700">{item.name}</span>
                </span>
                <span className="rounded-full border border-line px-2 py-0.5 text-xs text-stone-600">
                  {ASSET_LABEL[item.asset]}
                </span>
              </button>
            ))
          ) : queryHasNoMatch ? (
            <p className="p-4 text-sm leading-6 text-stone-600">
              暂未覆盖该标的（标的池共 {index?.poolStats.total ?? 0} 只）。
            </p>
          ) : (
            <p className="p-4 text-sm text-stone-600">标的池暂无数据。</p>
          )}
        </div>

        <label className="mt-5 block text-sm font-semibold" htmlFor="backtest-strategy">
          策略
        </label>
        <select
          id="backtest-strategy"
          className="focus-ring mt-2 min-h-[44px] w-full rounded-md border border-line px-3 py-3 disabled:bg-stone-100"
          value="pivot-condition-order"
          disabled={controlsDisabled}
          onChange={() => {}}
        >
          <option value="pivot-condition-order">Pivot 条件单（次日低吸/高抛）</option>
        </select>

        <p className="mt-5 text-sm font-semibold">区间</p>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3" role="group" aria-label="回测区间">
          {windows.map((w) => {
            const active = w.key === windowKey;
            return (
              <button
                key={w.key}
                type="button"
                aria-pressed={active}
                disabled={controlsDisabled || !w.available}
                onClick={() => setWindowKey(w.key)}
                className={`inline-flex min-h-[44px] flex-col items-center justify-center rounded-md border px-3 py-2 text-sm transition-colors ${
                  active
                    ? "border-leaf bg-rice font-semibold text-leaf"
                    : "border-line bg-white text-stone-600"
                } ${!w.available ? "cursor-not-allowed opacity-50" : "hover:border-leaf"}`}
              >
                <span>{w.label}</span>
                {!w.available && <span className="text-xs text-stone-500">{w.reason ?? "数据不足"}</span>}
              </button>
            );
          })}
        </div>
      </section>

      {/* 右：结果摘要 */}
      <section className="min-w-0 rounded-lg border border-line bg-white p-5 shadow-sm">
        <h2 className="text-xl font-bold">历史表现摘要</h2>

        {loadState === "pending" ? (
          <div className="mt-5 rounded-md border border-line bg-rice p-4 text-sm leading-7 text-stone-700">
            <p className="font-semibold text-ink">回测数据准备中</p>
            <p className="mt-2">数据前置结论与预计算文件就绪后自动开放；本页不展示推测数据。</p>
          </div>
        ) : !selected ? (
          <p className="mt-5 text-sm text-stone-600">选择标的后查看其历史表现。</p>
        ) : summaryState === "loading" ? (
          <p className="mt-5 text-sm text-stone-600">正在读取该标的的预计算摘要…</p>
        ) : summaryState === "missing" ? (
          <p className="mt-5 text-sm text-stone-600">该标的暂无足够数据。</p>
        ) : result?.available ? (
          <>
            <p className="mt-4 text-sm text-stone-600">
              {selected.name}（{selected.code}）· {activeWindow.label}
            </p>
            <p className="mt-1 text-sm text-stone-600">
              区间：{result.start} ~ {result.end}（{result.tradingDays} 个交易日）
            </p>

            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <Metric
                label="胜率"
                value={formatPct(result.winRate, 1, false, "暂无交易")}
                sub={`${result.wins ?? 0}/${result.trades ?? 0} 笔`}
              />
              <Metric
                label="累计收益率"
                value={formatPct(result.cumReturn, 2, true)}
                sub="等额 1 万元/笔"
              />
              <Metric
                label="最大回撤"
                value={formatPct(result.maxDrawdown, 2)}
                sub="按逐日权益计算"
              />
            </div>

            <p className="mt-3 text-xs leading-6 text-stone-600">
              数据口径：前复权；等额 1 万元/笔，未计佣金与滑点。
            </p>

            {result.sampleInsufficient && (
              <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                样本不足（{result.trades ?? 0} 笔），结果仅供参考。
              </p>
            )}

            <div className="mt-4 rounded-md bg-rice p-4 text-sm leading-7 text-stone-700">
              <p className="font-semibold text-ink">规则</p>
              <p>次日跌至低吸价买入；达到高抛价卖出。</p>
              <p>最长持有 5 个交易日，未达高抛价按第 5 日收盘价结算。</p>
            </div>

            <p className="mt-4 text-sm font-semibold text-ink">历史表现不代表未来收益</p>

            <button
              type="button"
              disabled={!result.available}
              onClick={copySummary}
              className={`mt-4 inline-flex min-h-[44px] items-center justify-center rounded-md px-4 py-3 font-semibold text-white ${
                copyFailed ? "bg-amber-600" : copied ? "bg-leaf" : "bg-ink"
              }`}
            >
              {copyFailed ? "复制失败，请手动选中" : copied ? "已复制到剪贴板" : "复制回测摘要"}
            </button>
          </>
        ) : (
          <p className="mt-5 text-sm text-stone-600">该标的在该区间暂无足够数据。</p>
        )}
      </section>
    </div>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-white/75 p-4">
      <p className="text-sm text-stone-600">{label}</p>
      <p className="mt-1 truncate text-2xl font-bold tabular-nums text-ink">{value}</p>
      <p className="mt-1 text-xs leading-5 text-stone-500">{sub}</p>
    </div>
  );
}
