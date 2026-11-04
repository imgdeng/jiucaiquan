import { useEffect, useMemo, useRef, useState } from "react";
import { track } from "../lib/telemetry";
import { copyText } from "../lib/clipboard";

type AssetType = "etf" | "stock";
type WindowKey = "3m" | "2w" | "4w" | "6m" | "9m" | "12m";

type WindowMeta = {
  key: WindowKey;
  label: string;
  minTradingDays: number;
  available: boolean;
  start: string | null;
  end: string | null;
  tradingDays: number | null;
  reason: string | null;
  availableSymbols?: number | null;
  sample?: number | null;
  coverageNote?: string | null;
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
  priceAdjustment?: string;
  costNote?: string;
};

type Distribution = {
  start: string;
  end: string;
  tradingDays: number;
  sample: number;
  positiveCount: number;
  positiveShare: number;
  medianCumReturn: number | null;
  medianWinRate: number | null;
  medianMaxDrawdown: number | null;
  buckets: { lt0: number; "0to20": number; "20to50": number; gt50: number };
};

type Methodology = {
  priceAdjustment?: string;
  driftVsOfficialQfq?: { medianPp: number | null; maxAbsPp: number | null; worstName: string | null };
  note?: string;
};

type BacktestIndex = {
  schemaVersion: number;
  generatedAt: string;
  latestDate: string;
  dataStart: string;
  tradingDays: number;
  strategy: StrategyMeta;
  methodology?: Methodology;
  windows: WindowMeta[];
  poolStats: { total: number; etf: number; stock: number };
  distribution?: Partial<Record<WindowKey, Distribution>>;
  pool: PoolItem[];
};

type WindowResult = {
  available: boolean;
  start: string | null;
  end: string | null;
  tradingDays: number | null;
  availableTradingDays?: number | null;
  minTradingDays?: number | null;
  trades: number | null;
  wins: number | null;
  winRate: number | null;
  cumReturn: number | null;
  maxDrawdown: number | null;
  sampleWarning: "insufficient" | "noTrades" | null;
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

/** 逐笔数组顺序：买入日、买入价、卖出日、卖出价、持有天数、单笔收益率%、单笔盈亏元、平仓原因 */
type DetailTrade = [string, number, string, number, number, number, number, string];

type DetailWindow = {
  start: string;
  end: string;
  tradingDays: number;
  trades: DetailTrade[];
  pnlTotal: number;
  cumReturn: number;
  maxDrawdown: number;
  equity: number[];
  peak: { date: string; value: number };
  maxDrawdownRange: { start: string; end: string; pct: number } | null;
};

type DetailData = {
  schemaVersion: number;
  generatedAt: string;
  code: string;
  name: string;
  asset: AssetType;
  latestDate: string;
  notional: number;
  strategy: StrategyMeta;
  windows: Partial<Record<WindowKey, DetailWindow>>;
};

/** 索引未生成时的静态档位：只用于占位，未就绪时不渲染任何档位按钮 */
const STATIC_WINDOWS: WindowMeta[] = [
  { key: "3m", label: "近 3 个月", minTradingDays: 20, available: false, start: null, end: null, tradingDays: null, reason: "数据准备中" },
  { key: "2w", label: "近 2 周", minTradingDays: 10, available: false, start: null, end: null, tradingDays: null, reason: "数据准备中" },
  { key: "4w", label: "近 4 周", minTradingDays: 20, available: false, start: null, end: null, tradingDays: null, reason: "数据准备中" },
  { key: "6m", label: "近 6 个月", minTradingDays: 120, available: false, start: null, end: null, tradingDays: null, reason: "数据准备中" },
  { key: "9m", label: "近 9 个月", minTradingDays: 180, available: false, start: null, end: null, tradingDays: null, reason: "数据准备中" },
  { key: "12m", label: "近 12 个月", minTradingDays: 240, available: false, start: null, end: null, tradingDays: null, reason: "数据准备中" },
];

const ASSET_LABEL: Record<AssetType, string> = { etf: "ETF", stock: "个股" };
const BUCKET_LABEL: Array<{ key: keyof Distribution["buckets"]; label: string }> = [
  { key: "lt0", label: "负收益" },
  { key: "0to20", label: "0~20%" },
  { key: "20to50", label: "20~50%" },
  { key: "gt50", label: ">50%" },
];

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

function formatMoney(value: number | null | undefined, empty = "待数据"): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return empty;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)} 元`;
}

function priceDigits(asset: AssetType): number {
  return asset === "etf" ? 4 : 2;
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
  const lines = [
    `${name}(${code}) 回测摘要 · ${strategyLabel} · ${windowLabel}`,
    `区间：${start} ~ ${end}（${days} 个交易日）`,
    `胜率：${formatPct(result.winRate, 1, false, "无触发交易")}（${wins}/${trades} 笔）`,
    `累计收益率：${formatPct(result.cumReturn, 2, true)}（等额 1 万元/笔，未计佣金与滑点）`,
    `最大回撤：${formatPct(result.maxDrawdown, 2)}`,
    `规则：次日跌至低吸价买入，达到高抛价卖出，最长持有 5 个交易日`,
  ];
  if (result.sampleWarning === "insufficient") {
    lines.push(`样本提示：仅 ${trades} 笔，样本不足，胜率与收益率的统计意义有限`);
  } else if (result.sampleWarning === "noTrades") {
    lines.push("样本提示：该区间未触发交易");
  }
  lines.push("历史表现不代表未来收益，仅供学习研究，不构成投资建议。");
  return lines.join("\n");
}

export default function BacktestTool() {
  const [index, setIndex] = useState<BacktestIndex | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "pending" | "ready">("loading");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<PoolItem | null>(null);
  const [windowKey, setWindowKey] = useState<WindowKey>("3m");
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [summaryState, setSummaryState] = useState<"idle" | "loading" | "ready" | "missing">("idle");
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<DetailData | null>(null);
  const [detailState, setDetailState] = useState<"idle" | "loading" | "ready" | "missing">("idle");
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);

  const summaryCache = useRef(new Map<string, SummaryData>());
  const detailCache = useRef(new Map<string, DetailData>());
  const requestId = useRef(0);
  const detailRequestId = useRef(0);
  const didPageView = useRef(false);
  const lastResult = useRef("");
  const lastDetailView = useRef("");

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
  // 只渲染真正可用的档位：不可用档位不出现按钮，也不出现“数据积累中”占位
  const availableWindows = windows.filter((w) => w.available);

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
    setDetailOpen(false);
    setDetail(null);
    setDetailState("idle");
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

  async function toggleDetail() {
    if (!selected) return;
    if (detailOpen) {
      setDetailOpen(false);
      return;
    }
    setDetailOpen(true);
    const payload = { code: selected.code, asset: selected.asset, window: windowKey };
    track("backtest_detail_expand", payload);
    if (detailState === "ready" && detail?.code === selected.code) {
      markDetailViewed();
      return;
    }
    const id = ++detailRequestId.current;
    setDetailState("loading");
    const cached = detailCache.current.get(selected.code);
    if (cached) {
      if (id !== detailRequestId.current) return;
      setDetail(cached);
      setDetailState("ready");
      markDetailViewed();
      return;
    }
    const data = await loadJson<DetailData>(`/data/backtest/detail/${selected.code}.json`);
    if (id !== detailRequestId.current) return;
    if (!data) {
      setDetailState("missing");
      return;
    }
    detailCache.current.set(selected.code, data);
    setDetail(data);
    setDetailState("ready");
    markDetailViewed();
  }

  function markDetailViewed() {
    if (!selected) return;
    const key = `${selected.code}:${windowKey}`;
    if (lastDetailView.current === key) return;
    lastDetailView.current = key;
    track("backtest_detail_view", { code: selected.code, asset: selected.asset, window: windowKey });
  }

  // 出结果埋点：同标的同档位只记一次
  useEffect(() => {
    if (!selected || summaryState !== "ready" || !summary) return;
    const resultForTrack = summary.windows[windowKey];
    if (!resultForTrack?.available) return;
    const key = `${selected.code}:${windowKey}`;
    if (lastResult.current === key) return;
    lastResult.current = key;
    track("backtest_result", { code: selected.code, asset: selected.asset, window: windowKey });
  }, [selected, summary, summaryState, windowKey]);

  const activeWindow = availableWindows.find((w) => w.key === windowKey) ?? availableWindows[0] ?? windows[0];
  const result = summary?.windows[windowKey];
  const detailWindow = detail?.windows[windowKey];
  const distribution = index?.distribution?.[windowKey];

  async function copySummary() {
    if (!selected || !summary || !result?.available) return;
    const payload = { code: selected.code, asset: selected.asset, window: windowKey };
    track("backtest_copy", payload);
    const text = buildSummaryText(
      summary.name,
      summary.code,
      summary.strategy.label,
      activeWindow?.label ?? "",
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
    <>
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
            <option value="pivot-condition-order">Pivot 条件单</option>
          </select>
          <p className="mt-2 text-xs leading-5 text-stone-600">
            规则：次日低吸/高抛；最长持有 5 个交易日，到期按收盘平仓。
          </p>

          <p className="mt-5 text-sm font-semibold">区间</p>
          {availableWindows.length ? (
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3" role="group" aria-label="回测区间">
              {availableWindows.map((w) => {
                const active = w.key === windowKey;
                return (
                  <button
                    key={w.key}
                    type="button"
                    aria-pressed={active}
                    disabled={controlsDisabled}
                    onClick={() => setWindowKey(w.key)}
                    className={`inline-flex min-h-[44px] flex-col items-center justify-center rounded-md border px-2 py-2 text-sm transition-colors ${
                      active
                        ? "border-leaf bg-rice font-semibold text-leaf"
                        : "border-line bg-white text-stone-600 hover:border-leaf"
                    }`}
                  >
                    <span>{w.label}</span>
                    {w.tradingDays !== null && (
                      <span className="text-xs text-stone-500">{w.tradingDays} 个交易日</span>
                    )}
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="mt-2 text-sm text-stone-600">区间档位准备中。</p>
          )}
          {activeWindow?.coverageNote && (
            <p className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800">
              {activeWindow.coverageNote}
            </p>
          )}
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
                {selected.name}（{selected.code}）· {activeWindow?.label}
              </p>
              <p className="mt-1 text-sm text-stone-600">
                区间：{result.start} ~ {result.end}（{result.tradingDays} 个交易日）
              </p>

              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <Metric
                  label="胜率"
                  value={formatPct(result.winRate, 1, false, "无触发交易")}
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

              {result.sampleWarning === "insufficient" && (
                <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-800">
                  样本不足（{result.trades ?? 0} 笔）：短周期内触发次数很少，胜率与收益率的统计意义有限。
                </p>
              )}
              {result.sampleWarning === "noTrades" && (
                <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-800">
                  该区间未触发交易（0 笔），不构成任何结论。
                </p>
              )}

              <div className="mt-4 rounded-md bg-rice p-4 text-sm leading-7 text-stone-700">
                <p className="font-semibold text-ink">规则</p>
                <p>次日跌至低吸价买入；达到高抛价卖出。</p>
                <p>最长持有 5 个交易日，未达高抛价按第 5 日收盘价结算。</p>
              </div>

              <p className="mt-4 text-sm font-semibold text-ink">历史表现不代表未来收益</p>

              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  type="button"
                  disabled={!result.available}
                  onClick={copySummary}
                  className={`inline-flex min-h-[44px] items-center justify-center rounded-md px-4 py-3 font-semibold text-white ${
                    copyFailed ? "bg-amber-600" : copied ? "bg-leaf" : "bg-ink"
                  }`}
                >
                  {copyFailed ? "复制失败，请手动选中" : copied ? "已复制到剪贴板" : "复制回测摘要"}
                </button>
                <button
                  type="button"
                  onClick={toggleDetail}
                  aria-expanded={detailOpen}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-md border border-line bg-white px-4 py-3 font-semibold text-ink hover:border-leaf"
                >
                  {detailOpen ? "收起逐笔与曲线" : "查看逐笔与权益曲线"}
                </button>
              </div>

              {detailOpen && (
                <div className="mt-4 rounded-md border border-line p-4">
                  {detailState === "loading" ? (
                    <p className="text-sm text-stone-600">正在读取逐笔明细…</p>
                  ) : detailState === "missing" ? (
                    <p className="text-sm text-stone-600">该标的逐笔明细暂不可用。</p>
                  ) : detailWindow ? (
                    <DetailPanel detail={detailWindow} asset={selected.asset} />
                  ) : (
                    <p className="text-sm text-stone-600">该区间暂无逐笔明细。</p>
                  )}
                </div>
              )}
            </>
          ) : result ? (
            <div className="mt-5 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm leading-7 text-amber-800">
              <p className="font-semibold">{result.reason ?? "该标的此区间数据不足"}</p>
              {result.minTradingDays && (
                <p className="mt-1">该档位至少需要 {result.minTradingDays} 个交易日，请选择其他区间。</p>
              )}
            </div>
          ) : (
            <p className="mt-5 text-sm text-stone-600">该标的在该区间暂无足够数据。</p>
          )}
        </section>
      </div>

      {/* 池内分布概览：不点名标的、不排序、不出现 TOP/热门/推荐 */}
      {distribution && (
        <section className="mt-5 rounded-lg border border-line bg-white p-5 shadow-sm">
          <h2 className="text-xl font-bold">回测结果概览</h2>
          <p className="mt-1 text-sm leading-6 text-stone-600">
            以下为池内标的在所选区间的统计分布：不点名标的、不按收益排序，不构成对任何标的的提示。
          </p>
          <p className="mt-2 text-xs leading-5 text-stone-500">
            区间：{distribution.start} ~ {distribution.end}（{distribution.tradingDays} 个交易日）· 样本{" "}
            {distribution.sample} 只 · 未计佣金与滑点
          </p>

          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric
              label="正收益标的"
              value={`${distribution.positiveCount}/${distribution.sample}`}
              sub={`占比 ${distribution.positiveShare.toFixed(1)}%`}
            />
            <Metric
              label="累计收益率中位数"
              value={formatPct(distribution.medianCumReturn, 2, true, "暂无")}
              sub="按标的等权统计"
            />
            <Metric
              label="胜率中位数"
              value={formatPct(distribution.medianWinRate, 1, false, "暂无")}
              sub="仅统计有平仓的标的"
            />
            <Metric
              label="最大回撤中位数"
              value={formatPct(distribution.medianMaxDrawdown, 2, false, "暂无")}
              sub="按逐日权益计算"
            />
          </div>

          <div className="mt-4">
            <p className="text-sm font-semibold text-ink">累计收益率分布</p>
            <div className="mt-2 space-y-2">
              {BUCKET_LABEL.map((bucket) => {
                const count = distribution.buckets[bucket.key];
                const share = distribution.sample ? (count / distribution.sample) * 100 : 0;
                return (
                  <div key={bucket.key} className="grid grid-cols-[4.5rem_1fr_3.5rem] items-center gap-2 text-xs">
                    <span className="text-stone-600">{bucket.label}</span>
                    <span className="h-2 overflow-hidden rounded-full bg-stone-100">
                      <span className="block h-full rounded-full bg-stone-400" style={{ width: `${share}%` }} />
                    </span>
                    <span className="text-right tabular-nums text-stone-600">{count} 只</span>
                  </div>
                );
              })}
            </div>
          </div>

          <p className="mt-4 text-xs leading-5 text-stone-500">历史表现不代表未来收益。</p>
        </section>
      )}
    </>
  );
}

function DetailPanel({ detail, asset }: { detail: DetailWindow; asset: AssetType }) {
  const digits = priceDigits(asset);
  const pnlSum = detail.trades.reduce((sum, trade) => sum + trade[6], 0);
  const lastEquity = detail.equity[detail.equity.length - 1];
  return (
    <div>
      <p className="text-sm font-semibold text-ink">逐笔交易</p>
      <p className="mt-1 text-xs leading-5 text-stone-500">
        等额 1 万元/笔、串行单仓、不复利；未计佣金、滑点与费用。
      </p>

      {detail.trades.length === 0 ? (
        <p className="mt-3 text-sm text-stone-600">该区间未触发交易，权益曲线保持 100。</p>
      ) : (
        <>
          <div className="mt-3 hidden overflow-x-auto sm:block">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-line text-left text-stone-500">
                  <th className="py-2 pr-2 font-medium">买入</th>
                  <th className="py-2 pr-2 font-medium">卖出</th>
                  <th className="py-2 pr-2 font-medium">持有</th>
                  <th className="py-2 pr-2 text-right font-medium">单笔收益</th>
                  <th className="py-2 pr-2 text-right font-medium">单笔盈亏</th>
                  <th className="py-2 font-medium">平仓</th>
                </tr>
              </thead>
              <tbody>
                {detail.trades.map((trade, i) => (
                  <tr key={i} className="border-b border-line/70 last:border-b-0">
                    <td className="py-2 pr-2 align-top">
                      <span className="block tabular-nums">{trade[0]}</span>
                      <span className="block tabular-nums text-stone-500">{trade[1].toFixed(digits)}</span>
                    </td>
                    <td className="py-2 pr-2 align-top">
                      <span className="block tabular-nums">{trade[2]}</span>
                      <span className="block tabular-nums text-stone-500">{trade[3].toFixed(digits)}</span>
                    </td>
                    <td className="py-2 pr-2 align-top tabular-nums">{trade[4]} 日</td>
                    <td className="py-2 pr-2 text-right align-top tabular-nums">{formatPct(trade[5], 2, true)}</td>
                    <td className="py-2 pr-2 text-right align-top tabular-nums">{formatMoney(trade[6])}</td>
                    <td className="py-2 align-top">{trade[7]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-3 space-y-2 sm:hidden">
            {detail.trades.map((trade, i) => (
              <div key={i} className="rounded-md border border-line p-3 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-ink">{trade[7]}</span>
                  <span className="tabular-nums text-stone-600">{trade[4]} 个交易日</span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <div>
                    <p className="text-stone-500">买入</p>
                    <p className="tabular-nums">{trade[0]}</p>
                    <p className="tabular-nums">{trade[1].toFixed(digits)}</p>
                  </div>
                  <div>
                    <p className="text-stone-500">卖出</p>
                    <p className="tabular-nums">{trade[2]}</p>
                    <p className="tabular-nums">{trade[3].toFixed(digits)}</p>
                  </div>
                </div>
                <div className="mt-2 flex justify-between border-t border-line/70 pt-2">
                  <span className="tabular-nums">{formatPct(trade[5], 2, true)}</span>
                  <span className="tabular-nums">{formatMoney(trade[6])}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <p className="mt-3 text-xs leading-5 text-stone-600">
        逐笔合计 {formatMoney(pnlSum)} · 累计收益率 {formatPct(detail.cumReturn, 2, true)} · 曲线终值{" "}
        <span className="tabular-nums">{lastEquity.toFixed(2)}</span>（起点 100）
      </p>

      <p className="mt-5 text-sm font-semibold text-ink">累计权益曲线</p>
      <EquityCurve equity={detail.equity} peak={detail.peak} />
      <p className="mt-2 text-xs leading-5 text-stone-600">
        峰值 {detail.peak.date}（{detail.peak.value.toFixed(2)}）
        {detail.maxDrawdownRange && (
          <>
            {" · "}
            最大回撤 {detail.maxDrawdownRange.pct.toFixed(2)}%（{detail.maxDrawdownRange.start} ~{" "}
            {detail.maxDrawdownRange.end}）
          </>
        )}
      </p>
      <p className="mt-2 text-xs leading-5 text-stone-500">
        权益指数起点 100，按交易日绘制；终值 = 100 + 累计收益率。等额 1 万元/笔、串行单仓、不复利；不计费用。
      </p>
    </div>
  );
}

function EquityCurve({
  equity,
  peak,
}: {
  equity: number[];
  peak: { date: string; value: number };
}) {
  if (equity.length < 2) {
    return <p className="mt-3 text-sm text-stone-600">该区间交易日不足，暂不绘制曲线。</p>;
  }
  const values = [...equity, 100];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 0.5);
  const lo = min - span * 0.08;
  const hi = max + span * 0.08;
  const width = 320;
  const height = 120;
  const padX = 6;
  const padTop = 10;
  const padBottom = 18;
  const plotW = width - padX * 2;
  const plotH = height - padTop - padBottom;
  const point = (value: number, index: number) => {
    const x = padX + (index / (equity.length - 1)) * plotW;
    const y = padTop + ((hi - value) / (hi - lo)) * plotH;
    return [x, y] as const;
  };
  const points = equity.map((value, index) => point(value, index));
  const path = points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const baselineY = padTop + ((hi - 100) / (hi - lo)) * plotH;
  const peakIndex = Math.max(0, equity.findIndex((value) => value === peak.value));
  const [peakX, peakY] = point(equity[peakIndex], peakIndex);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="累计权益曲线，起点 100"
      className="mt-3 w-full rounded-md border border-line bg-white"
    >
      <line x1={padX} x2={width - padX} y1={baselineY} y2={baselineY} stroke="#d6d3d1" strokeDasharray="4 4" />
      <text x={padX} y={baselineY - 4} fontSize="7" fill="#a8a29e">
        100
      </text>
      <polyline points={path} fill="none" stroke="#365314" strokeWidth="1.5" />
      <circle cx={peakX} cy={peakY} r="2.6" fill="#365314" />
      <text x={Math.min(width - 62, Math.max(2, peakX + 5))} y={Math.max(9, peakY - 5)} fontSize="7" fill="#57534e">
        峰值 {peak.date.slice(5)}
      </text>
    </svg>
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
