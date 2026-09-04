import { useEffect, useMemo, useRef, useState } from "react";
import type { AssetType, OHLCRaw } from "../lib/strategies/condition-order";
import {
  calculateConditionOrder,
  formatPrice,
  buildCopyText,
  validateOHLC,
} from "../lib/strategies/condition-order";
import { track } from "../lib/telemetry";

type QuoteSnapshot = {
  code: string;
  name: string;
  latest: number;
  open?: number;
  high: number;
  low: number;
  close: number;
  snapshotAt?: string;
};

type DataStatus = {
  generatedAt?: string;
  stockCount?: number;
  etfCount?: number;
  lastSuccessAt?: string;
  errors?: string[];
};

type WatchItem = { code: string; name: string };

function toNumber(value: string): number {
  if (!value || value.trim() === "") return NaN;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : NaN;
}

async function loadJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export default function ConditionOrderTool() {
  const [assetType, setAssetType] = useState<AssetType>("etf");
  const [etfQuotes, setEtfQuotes] = useState<QuoteSnapshot[]>([]);
  const [stockQuotes, setStockQuotes] = useState<QuoteSnapshot[]>([]);
  const [status, setStatus] = useState<DataStatus | null>(null);
  const [query, setQuery] = useState("");
  const [form, setForm] = useState<{ code: string; name: string; open: string; high: string; low: string; close: string }>({
    code: "",
    name: "",
    open: "",
    high: "",
    low: "",
    close: "",
  });
  const [copied, setCopied] = useState(false);

  const [watchlist, setWatchlist] = useState<WatchItem[]>(() => {
    if (typeof localStorage === "undefined") return [];
    try {
      return JSON.parse(localStorage.getItem("jcq-watchlist") || "[]");
    } catch {
      return [];
    }
  });

  useEffect(() => {
    Promise.all([
      loadJson<QuoteSnapshot[]>("/data/etf-latest.json"),
      loadJson<QuoteSnapshot[]>("/data/stock-latest.json"),
      loadJson<DataStatus>("/data/data-status.json"),
    ]).then(([etf, stock, st]) => {
      setEtfQuotes(etf || []);
      setStockQuotes(stock || []);
      setStatus(st);
    });
  }, []);

  // 埋点：页面访问（StrictMode 双调用去重）
  const didPageView = useRef(false);
  useEffect(() => {
    if (didPageView.current) return;
    didPageView.current = true;
    track("page_view", { asset: assetType });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 埋点：搜索（800ms 防抖，连续相同关键词只记一次）
  // 降噪：①IME 拼音组词期间不上报 ②过滤拼音碎片（纯字母数字且含空格）
  //       ③长度 <2 的拉丁词不上报 ④点选结果后的自动回填由 selectQuote 置位去重
  const lastSearchKey = useRef("");
  const composingRef = useRef(false);
  useEffect(() => {
    const keyword = query.trim();
    if (keyword.length < 1 || composingRef.current) return;
    // 纯 ASCII 且含空格 → 输入法拼音中间态（如 "si wei"）
    const isPinyinFragment = /^[a-z0-9\s]+$/i.test(keyword) && keyword.includes(" ");
    // 拉丁/数字词至少 2 个字符（过滤 "5" 这类单字符）；中文 1 个起即可
    const tooShort = /^[a-z0-9]+$/i.test(keyword) && keyword.length < 2;
    if (isPinyinFragment || tooShort) return;
    const key = `${assetType}:${keyword.toLowerCase().slice(0, 24)}`;
    if (key === lastSearchKey.current) return;
    lastSearchKey.current = key;
    const timer = setTimeout(() => {
      if (!composingRef.current) {
        track("search", { asset: assetType, term: keyword.slice(0, 24) });
      }
    }, 800);
    return () => clearTimeout(timer);
  }, [query, assetType]);

  const quotes = assetType === "etf" ? etfQuotes : stockQuotes;
  const matches = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return quotes.slice(0, 12);
    return quotes
      .filter((q) => `${q.code} ${q.name}`.toLowerCase().includes(keyword))
      .slice(0, 20);
  }, [query, quotes]);

  const ohlc: OHLCRaw = useMemo(
    () => ({
      open: toNumber(form.open),
      high: toNumber(form.high),
      low: toNumber(form.low),
      close: toNumber(form.close),
    }),
    [form],
  );

  const validation = useMemo(() => {
    if (!form.high || !form.low || !form.close) return null;
    return validateOHLC(ohlc);
  }, [ohlc, form]);

  const result = useMemo(() => {
    if (validation) return null;
    if (![ohlc.high, ohlc.low, ohlc.close].every(Number.isFinite)) return null;
    return calculateConditionOrder(ohlc, assetType);
  }, [ohlc, assetType, validation]);

  const copyText = result ? buildCopyText(form.code, form.name, result) : "";

  // 埋点：有效计算结果（同一标的+tab 只记一次；手动输入按 manual 归并）
  const lastCalcKey = useRef("");
  useEffect(() => {
    if (!result) return;
    const key = `${assetType}:${form.code || "manual"}`;
    if (key === lastCalcKey.current) return;
    lastCalcKey.current = key;
    track("calculate", {
      asset: assetType,
      code: form.code || undefined,
      name: form.name.slice(0, 20) || undefined,
    });
  }, [result, assetType, form.code, form.name]);

  function selectQuote(q: QuoteSnapshot) {
    track("select_quote", { asset: assetType, code: q.code, name: q.name.slice(0, 20) });
    // 回填的"代码 名称"不是用户搜索词：预置去重键，阻止搜索埋点把它记为 term
    const filled = `${q.code} ${q.name}`;
    lastSearchKey.current = `${assetType}:${filled.toLowerCase().slice(0, 24)}`;
    setForm({
      code: q.code,
      name: q.name,
      open: q.open ? String(q.open) : "",
      high: String(q.high),
      low: String(q.low),
      close: String(q.close || q.latest),
    });
    setQuery(`${q.code} ${q.name}`);
  }

  function updateForm(key: keyof typeof form, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function toggleWatch() {
    if (!form.code) return;
    const exists = watchlist.some((w) => w.code === form.code);
    track(exists ? "watch_remove" : "watch_add", {
      asset: assetType,
      code: form.code,
      name: form.name.slice(0, 20) || undefined,
    });
    const next = exists
      ? watchlist.filter((w) => w.code !== form.code)
      : [{ code: form.code, name: form.name || form.code }, ...watchlist].slice(0, 30);
    setWatchlist(next);
    localStorage.setItem("jcq-watchlist", JSON.stringify(next));
  }

  const isWatched = watchlist.some((w) => w.code === form.code && form.code);

  async function copyResult() {
    if (!copyText) return;
    await navigator.clipboard.writeText(copyText);
    track("copy", {
      asset: assetType,
      code: form.code || undefined,
      name: form.name.slice(0, 20) || undefined,
    });
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  const dataCount = assetType === "etf" ? etfQuotes.length : stockQuotes.length;
  const latestTime = status?.lastSuccessAt || status?.generatedAt || quotes[0]?.snapshotAt;

  const isStale = useMemo(() => {
    if (!status?.lastSuccessAt) return false;
    const last = new Date(status.lastSuccessAt).getTime();
    const hoursSince = (Date.now() - last) / 1000 / 3600;
    return hoursSince > 24;
  }, [status?.lastSuccessAt]);

  const dataAvailable = quotes.length > 0;

  return (
    <div className="grid gap-5 lg:grid-cols-[0.95fr_1.05fr]">
      <section className="rounded-lg border border-line bg-white p-5 shadow-sm">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold">今日行情快照</h2>
            <p className="mt-1 text-sm text-stone-600">
              已加载 {dataCount} 条，更新时间：{latestTime || "暂无"}
            </p>
          </div>
          <div className="grid grid-cols-2 rounded-md border border-line bg-rice p-1 text-sm">
            <button
              className={`rounded px-3 py-2 font-semibold ${assetType === "etf" ? "bg-leaf text-white" : ""}`}
              onClick={() => {
                setAssetType("etf");
                track("asset_switch", { asset: "etf" });
              }}
            >
              ETF
            </button>
            <button
              className={`rounded px-3 py-2 font-semibold ${assetType === "stock" ? "bg-leaf text-white" : ""}`}
              onClick={() => {
                setAssetType("stock");
                track("asset_switch", { asset: "stock" });
              }}
            >
              股票
            </button>
          </div>
        </div>

        <label className="block text-sm font-semibold" htmlFor="quote-search">
          搜索代码或名称
        </label>
        {isStale && (
          <div className="mt-3 rounded-md bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800">
            行情数据超过 1 个交易日未更新（最后更新：{latestTime}），仅供参考。请使用下方手动输入模式填入实时价格。
          </div>
        )}
        <input
          id="quote-search"
          className="focus-ring mt-2 w-full rounded-md border border-line px-3 py-3"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onCompositionStart={() => {
            composingRef.current = true;
          }}
          onCompositionEnd={() => {
            composingRef.current = false;
          }}
          placeholder="例如 512480 / 半导体"
        />

        <div className="mt-4 max-h-80 overflow-auto rounded-md border border-line">
          {matches.length ? (
            matches.map((q) => (
              <button
                key={`${assetType}-${q.code}`}
                className="grid w-full grid-cols-[1fr_auto] gap-2 border-b border-line px-3 py-3 text-left last:border-b-0 hover:bg-rice"
                onClick={() => selectQuote(q)}
              >
                <span>
                  <span className="font-semibold">{q.code}</span>
                  <span className="ml-2 text-stone-700">{q.name}</span>
                </span>
                <span className="text-sm text-stone-600">{q.latest}</span>
              </button>
            ))
          ) : dataAvailable ? (
            <p className="p-4 text-sm text-stone-600">
              当前筛选无匹配标的，可直接在<b>右侧手动输入</b>开盘/最高/最低/收盘价完成计算。
            </p>
          ) : (
            <div className="p-4 text-sm text-stone-600 space-y-2">
              <p>行情数据暂不可用，请使用<b>右侧手动输入</b>模式。</p>
              <p>按行情软件（如同花顺、东方财富）的当日 OHLC 数据填入开盘价、最高价、最低价、收盘/最新价即可。</p>
            </div>
          )}
        </div>

        <div className="mt-5 rounded-md bg-amber-50 p-4 text-sm leading-7 text-amber-900">
          行情源为自动快照，非实时行情。若数据为空，请使用下方手动输入模式，按行情软件的 OHLC 数据计算。
        </div>
      </section>

      <section className="rounded-lg border border-line bg-white p-5 shadow-sm">
        <h2 className="text-xl font-bold">手动输入 / 自动填充</h2>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          {[
            ["code", "代码"],
            ["name", "名称"],
            ["open", "开盘价"],
            ["close", "收盘/最新价"],
            ["high", "最高价"],
            ["low", "最低价"],
          ].map(([key, label]) => (
            <label key={key} className="block text-sm font-semibold">
              {label}
              <input
                className="focus-ring mt-2 w-full rounded-md border border-line px-3 py-3 font-normal"
                value={form[key as keyof typeof form]}
                onChange={(e) => updateForm(key as keyof typeof form, e.target.value)}
                placeholder={label}
              />
            </label>
          ))}
        </div>

        <div className="mt-6 flex flex-wrap gap-3">
          <button
            className="rounded-md bg-leaf px-4 py-3 font-semibold text-white hover:bg-emerald-800"
            onClick={toggleWatch}
          >
            {isWatched ? "从自选移除" : "加入自选"}
          </button>
          <button
            className="rounded-md border border-line px-4 py-3 font-semibold hover:border-leaf"
            onClick={() =>
              setForm({ code: "", name: "", open: "", high: "", low: "", close: "" })
            }
          >
            清空输入
          </button>
        </div>

        <div className="mt-6 rounded-lg border border-line bg-rice p-5">
          <h3 className="font-bold">次日条件单参考</h3>
          {validation ? (
            <p className="mt-3 text-sm text-amber-700">{validation}</p>
          ) : result ? (
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <Metric label="低吸价" value={formatPrice(result.buyPrice, result.digits)} highlight />
              <Metric label="高抛价" value={formatPrice(result.sellPrice, result.digits)} highlight />
              <Metric label="基准价" value={formatPrice(result.basePrice, result.digits)} />
              <Metric label="波动区间" value={formatPrice(result.range, result.digits)} />
              <Metric label="小观察价" value={formatPrice(result.smallWatchPrice, result.digits)} />
              <Metric label="大观察价" value={formatPrice(result.bigWatchPrice, result.digits)} />
            </div>
          ) : (
            <p className="mt-3 text-sm text-stone-600">请输入最高价、最低价、收盘价。</p>
          )}
          <button
            disabled={!result}
            className="mt-5 rounded-md bg-ink px-4 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
            onClick={copyResult}
          >
            {copied ? "已复制到剪贴板" : "复制条件单文案"}
          </button>
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <ListPanel
            title="本地自选"
            items={watchlist.map((w) => `${w.code} ${w.name}`)}
          />
          <ListPanel title="说明" items={["结果仅供学习研究", "条件单需在券商 App 设置", "不构成投资建议"]} />
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={`rounded-md border p-4 ${highlight ? "border-leaf bg-white" : "border-line bg-white/75"}`}>
      <p className="text-sm text-stone-600">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
    </div>
  );
}

function ListPanel({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-md border border-line p-4">
      <p className="font-semibold">{title}</p>
      {items.length ? (
        <ul className="mt-3 space-y-2 text-sm text-stone-700">
          {items.map((it) => (
            <li key={it}>{it}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-stone-500">暂无记录</p>
      )}
    </div>
  );
}
