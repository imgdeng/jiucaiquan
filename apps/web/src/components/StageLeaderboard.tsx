import { useEffect, useMemo, useRef, useState } from "react";
import { track } from "../lib/telemetry";

type RetKey = "ret1w" | "ret1m" | "ret3m" | "retYtd";

type RankRow = {
  code: string;
  name: string;
  ret1w: number | null;
  ret1m: number | null;
  ret3m: number | null;
  retYtd: number | null;
  amount?: number;
};

type SectorRow = {
  name: string;
  count: number;
  repCode: string;
  repName: string;
  ret1w: number | null;
  ret1m: number | null;
  ret3m: number | null;
  retYtd: number | null;
  repRet1w?: number | null;
  repRet1m?: number | null;
  repRet3m?: number | null;
  repRetYtd?: number | null;
};

type LeaderboardData = {
  generatedAt: string;
  latestDate: string;
  windowStart: Record<string, string | null>;
  stocks: RankRow[];
  etfs: RankRow[];
  sectors: SectorRow[];
};

type TabKey = "etf" | "stock" | "sector";
type RangeKey = "1w" | "1m" | "3m" | "ytd";
type DirKey = "up" | "down";

const TABS: { key: TabKey; label: string }[] = [
  { key: "etf", label: "ETF" },
  { key: "stock", label: "个股" },
  { key: "sector", label: "板块" },
];

const RANGES: { key: RangeKey; label: string }[] = [
  { key: "1w", label: "近1周" },
  { key: "1m", label: "近1月" },
  { key: "3m", label: "近3月" },
  { key: "ytd", label: "今年来" },
];

const RET_KEY: Record<RangeKey, RetKey> = {
  "1w": "ret1w",
  "1m": "ret1m",
  "3m": "ret3m",
  ytd: "retYtd",
};

const REP_RET_KEY: Record<RangeKey, keyof SectorRow> = {
  "1w": "repRet1w",
  "1m": "repRet1m",
  "3m": "repRet3m",
  ytd: "repRetYtd",
};

function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const pct = value * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

function formatAmount(value: number | undefined): string {
  if (!value) return "";
  if (value >= 1e8) return `成交 ${(value / 1e8).toFixed(1)} 亿`;
  if (value >= 1e4) return `成交 ${(value / 1e4).toFixed(0)} 万`;
  return "";
}

function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "";
  return iso.slice(5).replace("-", "/");
}

/** A 股语义色：红涨绿跌 */
function pctClass(value: number | null | undefined): string {
  if (value === null || value === undefined) return "text-stone-400";
  if (value > 0) return "text-red-600";
  if (value < 0) return "text-green-600";
  return "text-stone-500";
}

function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

async function loadLeaderboard(): Promise<LeaderboardData | null> {
  try {
    const res = await fetch("/data/leaderboard.json", { cache: "no-cache" });
    if (!res.ok) return null;
    return (await res.json()) as LeaderboardData;
  } catch {
    return null;
  }
}

export default function StageLeaderboard() {
  const [data, setData] = useState<LeaderboardData | null>(null);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<TabKey>("etf");
  const [range, setRange] = useState<RangeKey>("3m");
  const [dir, setDir] = useState<DirKey>("up");

  useEffect(() => {
    loadLeaderboard().then((d) => {
      if (d) setData(d);
      else setFailed(true);
    });
  }, []);

  const didView = useRef(false);
  useEffect(() => {
    if (!data || didView.current) return;
    didView.current = true;
    track("leaderboard_view");
  }, [data]);

  const rows = useMemo(() => {
    if (!data) return [];
    const retKey = RET_KEY[range];
    const source: RankRow[] = tab === "stock" ? data.stocks : tab === "etf" ? data.etfs : [];
    if (tab === "sector") {
      const repKey = REP_RET_KEY[range];
      const sectors = data.sectors
        .map((s) => ({ sector: s, ret: s[retKey] as number | null, repRet: s[repKey] as number | null }))
        .filter((r): r is { sector: SectorRow; ret: number; repRet: number | null } => r.ret !== null);
      sectors.sort((a, b) => (dir === "up" ? b.ret - a.ret : a.ret - b.ret));
      return sectors.slice(0, 10);
    }
    const ranked = source
      .map((r) => ({ row: r, ret: r[retKey] }))
      .filter((x): x is { row: RankRow; ret: number } => x.ret !== null);
    ranked.sort((a, b) => (dir === "up" ? b.ret - a.ret : a.ret - b.ret));
    return ranked.slice(0, 10);
  }, [data, tab, range, dir]);

  if (failed) return null; // 数据加载失败时卡片整体降级隐藏

  const switchTab = (key: TabKey) => {
    if (key === tab) return;
    setTab(key);
    track("leaderboard_switch", { term: `tab:${key}` });
  };
  const switchRange = (key: RangeKey) => {
    if (key === range) return;
    setRange(key);
    track("leaderboard_switch", { term: `range:${key}` });
  };
  const switchDir = (key: DirKey) => {
    if (key === dir) return;
    setDir(key);
    track("leaderboard_switch", { term: `dir:${key}` });
  };

  const startDate = data?.windowStart?.[range];

  return (
    <div className="overflow-hidden rounded-lg border border-line bg-white shadow-sm">
      {/* 头部 */}
      <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-bold">阶段排行榜</h2>
          <span className="rounded-full bg-leaf/15 px-2.5 py-0.5 text-xs font-semibold text-leaf">
            {dir === "up" ? "涨幅榜" : "跌幅榜"}
          </span>
        </div>
        {data && (
          <span className="shrink-0 text-xs text-stone-500">数据截至 {formatDateShort(data.latestDate)}</span>
        )}
      </div>

      {/* 筛选区 */}
      <div className="space-y-3 px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-md border border-line p-0.5" role="tablist" aria-label="品类">
            {TABS.map((t) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => switchTab(t.key)}
                className={cx(
                  "rounded px-4 py-1.5 text-sm font-semibold transition-colors",
                  tab === t.key ? "bg-leaf text-white" : "text-stone-600 hover:text-leaf",
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="flex rounded-md border border-line p-0.5" role="group" aria-label="涨跌方向">
            {([
              { key: "up" as DirKey, label: "涨幅 ↑" },
              { key: "down" as DirKey, label: "跌幅 ↓" },
            ]).map((d) => (
              <button
                key={d.key}
                aria-pressed={dir === d.key}
                onClick={() => switchDir(d.key)}
                className={cx(
                  "rounded px-3 py-1.5 text-sm font-semibold transition-colors",
                  dir === d.key
                    ? d.key === "up"
                      ? "bg-red-600 text-white"
                      : "bg-green-600 text-white"
                    : "text-stone-600 hover:text-leaf",
                )}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="时间区间">
          {RANGES.map((r) => (
            <button
              key={r.key}
              aria-pressed={range === r.key}
              onClick={() => switchRange(r.key)}
              className={cx(
                "rounded-full border px-3.5 py-1 text-sm transition-colors",
                range === r.key
                  ? "border-leaf bg-rice font-semibold text-leaf"
                  : "border-line bg-white text-stone-600 hover:border-leaf",
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* 榜单 */}
      <ul className="divide-y divide-line/70 border-t border-line" aria-live="polite">
        {!data &&
          Array.from({ length: 10 }).map((_, i) => (
            <li key={i} className="flex animate-pulse items-center gap-3 px-5 py-3">
              <span className="h-4 w-5 rounded bg-stone-100" />
              <span className="h-4 flex-1 rounded bg-stone-100" />
              <span className="h-4 w-16 rounded bg-stone-100" />
            </li>
          ))}
        {data && rows.length === 0 && (
          <li className="px-5 py-10 text-center text-sm text-stone-500">数据积累中，敬请期待</li>
        )}
        {data &&
          tab !== "sector" &&
          (rows as { row: RankRow; ret: number }[]).map(({ row, ret }, i) => (
            <li key={row.code} className="flex items-center gap-3 px-5 py-2.5">
              <span
                className={cx(
                  "w-6 shrink-0 text-center text-sm font-bold",
                  i < 3 ? "text-leaf" : "text-stone-400",
                )}
              >
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{row.name}</p>
                <p className="mt-0.5 text-xs text-stone-400">
                  {row.code}
                  {row.amount ? ` · ${formatAmount(row.amount)}` : ""}
                </p>
              </div>
              <span className={cx("shrink-0 text-base font-bold tabular-nums", pctClass(ret))}>
                {formatPct(ret)}
              </span>
            </li>
          ))}
        {data &&
          tab === "sector" &&
          (rows as { sector: SectorRow; ret: number; repRet: number | null }[]).map(({ sector, ret, repRet }, i) => (
            <li key={sector.name} className="flex items-center gap-3 px-5 py-2.5">
              <span
                className={cx(
                  "w-6 shrink-0 text-center text-sm font-bold",
                  i < 3 ? "text-leaf" : "text-stone-400",
                )}
              >
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">
                  {sector.name}
                  <span className="ml-1.5 text-xs font-normal text-stone-400">{sector.count} 只</span>
                </p>
                <p className="mt-0.5 truncate text-xs text-stone-400">
                  代表 {sector.repName}
                  {repRet !== null && (
                    <span className={cx("ml-1 font-semibold", pctClass(repRet))}>{formatPct(repRet)}</span>
                  )}
                </p>
              </div>
              <span className={cx("shrink-0 text-base font-bold tabular-nums", pctClass(ret))}>
                {formatPct(ret)}
              </span>
            </li>
          ))}
      </ul>

      {/* 底部 */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line bg-rice/50 px-5 py-3 text-xs text-stone-500">
        <span>
          {startDate && data ? `区间 ${formatDateShort(startDate)} → ${formatDateShort(data.latestDate)}` : ""}
          {tab === "sector" ? " · 板块涨幅取行业 ETF 中位数" : ""}
        </span>
        <span>历史数据统计，不构成投资建议</span>
      </div>
    </div>
  );
}
