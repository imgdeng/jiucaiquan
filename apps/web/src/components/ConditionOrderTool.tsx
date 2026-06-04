import { useEffect, useMemo, useState } from "react";

type AssetType = "etf" | "stock";

type QuoteSnapshot = {
  code: string;
  name: string;
  latest: number;
  open?: number;
  high: number;
  low: number;
  close: number;
  changePct?: number;
  amount?: number;
  snapshotAt: string;
  source: string;
};

type DataStatus = {
  generatedAt?: string;
  stockCount?: number;
  etfCount?: number;
  lastSuccessAt?: string;
  errors?: string[];
};

type FormState = {
  code: string;
  name: string;
  open: string;
  high: string;
  low: string;
  close: string;
};

const emptyForm: FormState = {
  code: "",
  name: "",
  open: "",
  high: "",
  low: "",
  close: "",
};

function toNumber(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : NaN;
}

function roundByType(value: number, type: AssetType) {
  const digits = type === "etf" ? 4 : 2;
  return Number(value.toFixed(digits));
}

function formatPrice(value: number, type: AssetType) {
  const digits = type === "etf" ? 4 : 2;
  return value.toFixed(digits);
}

function calculate(form: FormState, type: AssetType) {
  const close = toNumber(form.close);
  const high = toNumber(form.high);
  const low = toNumber(form.low);

  if (![close, high, low].every(Number.isFinite) || high <= 0 || low <= 0 || close <= 0 || high < low) {
    return null;
  }

  const range = high - low;
  const basePrice = (2 * close + high + low) / 4;
  const buyPrice = basePrice - range;
  const sellPrice = basePrice + range;
  const smallWatchPrice = 2 * basePrice - high;
  const bigWatchPrice = 2 * basePrice - low;

  return {
    range: roundByType(range, type),
    basePrice: roundByType(basePrice, type),
    buyPrice: roundByType(buyPrice, type),
    sellPrice: roundByType(sellPrice, type),
    smallWatchPrice: roundByType(smallWatchPrice, type),
    bigWatchPrice: roundByType(bigWatchPrice, type),
  };
}

function quoteToForm(quote: QuoteSnapshot): FormState {
  return {
    code: quote.code,
    name: quote.name,
    open: quote.open ? String(quote.open) : "",
    high: String(quote.high),
    low: String(quote.low),
    close: String(quote.close || quote.latest),
  };
}

async function loadJson<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as T;
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
  const [form, setForm] = useState<FormState>(emptyForm);
  const [copied, setCopied] = useState(false);
  const [watchlist, setWatchlist] = useState<string[]>(() => {
    if (typeof localStorage === "undefined") return [];
    try {
      return JSON.parse(localStorage.getItem("jcq-watchlist") || "[]");
    } catch {
      return [];
    }
  });
  const [history, setHistory] = useState<string[]>(() => {
    if (typeof localStorage === "undefined") return [];
    try {
      return JSON.parse(localStorage.getItem("jcq-history") || "[]");
    } catch {
      return [];
    }
  });

  useEffect(() => {
    Promise.all([
      loadJson<QuoteSnapshot[]>("/data/etf-latest.json"),
      loadJson<QuoteSnapshot[]>("/data/stock-latest.json"),
      loadJson<DataStatus>("/data/data-status.json"),
    ]).then(([etf, stock, dataStatus]) => {
      setEtfQuotes(etf || []);
      setStockQuotes(stock || []);
      setStatus(dataStatus);
    });
  }, []);

  const quotes = assetType === "etf" ? etfQuotes : stockQuotes;

  const matches = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return quotes.slice(0, 12);
    return quotes
      .filter((quote) => `${quote.code} ${quote.name}`.toLowerCase().includes(keyword))
      .slice(0, 20);
  }, [query, quotes]);

  const result = useMemo(() => calculate(form, assetType), [form, assetType]);

  const copyText = result
    ? `${form.name || form.code}(${form.code}) 条件单参考：低吸价 ${formatPrice(result.buyPrice, assetType)}，高抛价 ${formatPrice(result.sellPrice, assetType)}，小观察价 ${formatPrice(result.smallWatchPrice, assetType)}，大观察价 ${formatPrice(result.bigWatchPrice, assetType)}。仅供学习研究，不构成投资建议。`
    : "";

  function selectQuote(quote: QuoteSnapshot) {
    setForm(quoteToForm(quote));
    setQuery(`${quote.code} ${quote.name}`);
  }

  function updateForm(key: keyof FormState, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function persistWatchlist(next: string[]) {
    setWatchlist(next);
    localStorage.setItem("jcq-watchlist", JSON.stringify(next));
  }

  function addToWatchlist() {
    if (!form.code) return;
    const label = `${assetType}:${form.code}:${form.name || form.code}`;
    const next = [label, ...watchlist.filter((item) => item !== label)].slice(0, 30);
    persistWatchlist(next);
  }

  function persistHistory(label: string) {
    const next = [label, ...history.filter((item) => item !== label)].slice(0, 10);
    setHistory(next);
    localStorage.setItem("jcq-history", JSON.stringify(next));
  }

  async function copyResult() {
    if (!copyText) return;
    await navigator.clipboard.writeText(copyText);
    setCopied(true);
    persistHistory(`${new Date().toLocaleString()} ${form.code} ${form.name}`);
    window.setTimeout(() => setCopied(false), 1600);
  }

  const dataCount = assetType === "etf" ? etfQuotes.length : stockQuotes.length;
  const latestTime = status?.lastSuccessAt || status?.generatedAt || quotes[0]?.snapshotAt;

  return (
    <div className="grid gap-5 lg:grid-cols-[0.95fr_1.05fr]">
      <section className="rounded-lg border border-line bg-white p-5 shadow-sm">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold">今日行情数据</h2>
            <p className="mt-1 text-sm text-stone-600">
              已加载 {dataCount} 条，更新时间：{latestTime || "暂无"}
            </p>
          </div>
          <div className="grid grid-cols-2 rounded-md border border-line bg-rice p-1 text-sm">
            <button
              className={`rounded px-3 py-2 font-semibold ${assetType === "etf" ? "bg-leaf text-white" : ""}`}
              onClick={() => setAssetType("etf")}
            >
              ETF
            </button>
            <button
              className={`rounded px-3 py-2 font-semibold ${assetType === "stock" ? "bg-leaf text-white" : ""}`}
              onClick={() => setAssetType("stock")}
            >
              股票
            </button>
          </div>
        </div>

        <label className="block text-sm font-semibold" htmlFor="quote-search">
          搜索代码或名称
        </label>
        <input
          id="quote-search"
          className="focus-ring mt-2 w-full rounded-md border border-line px-3 py-3"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="例如 512480 半导体"
        />

        <div className="mt-4 max-h-80 overflow-auto rounded-md border border-line">
          {matches.length ? (
            matches.map((quote) => (
              <button
                key={`${assetType}-${quote.code}`}
                className="grid w-full grid-cols-[1fr_auto] gap-2 border-b border-line px-3 py-3 text-left last:border-b-0 hover:bg-rice"
                onClick={() => selectQuote(quote)}
              >
                <span>
                  <span className="font-semibold">{quote.code}</span>
                  <span className="ml-2 text-stone-700">{quote.name}</span>
                </span>
                <span className="text-sm text-stone-600">{quote.latest}</span>
              </button>
            ))
          ) : (
            <p className="p-4 text-sm text-stone-600">没有匹配数据，可直接在右侧手动输入。</p>
          )}
        </div>

        <div className="mt-5 rounded-md bg-amber-50 p-4 text-sm leading-7 text-amber-900">
          行情源可能延迟或失败。若数据为空，请使用手动输入模式，按券商 App 或行情软件的 OHLC 数据计算。
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
                value={form[key as keyof FormState]}
                onChange={(event) => updateForm(key as keyof FormState, event.target.value)}
                placeholder={label}
              />
            </label>
          ))}
        </div>

        <div className="mt-6 flex flex-wrap gap-3">
          <button className="rounded-md bg-leaf px-4 py-3 font-semibold text-white hover:bg-emerald-800" onClick={addToWatchlist}>
            加入自选
          </button>
          <button className="rounded-md border border-line px-4 py-3 font-semibold hover:border-leaf" onClick={() => setForm(emptyForm)}>
            清空输入
          </button>
        </div>

        <div className="mt-6 rounded-lg border border-line bg-rice p-5">
          <h3 className="font-bold">次日条件单参考</h3>
          {result ? (
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <Metric label="低吸价" value={formatPrice(result.buyPrice, assetType)} highlight />
              <Metric label="高抛价" value={formatPrice(result.sellPrice, assetType)} highlight />
              <Metric label="基准价" value={formatPrice(result.basePrice, assetType)} />
              <Metric label="波动区间" value={formatPrice(result.range, assetType)} />
              <Metric label="小观察价" value={formatPrice(result.smallWatchPrice, assetType)} />
              <Metric label="大观察价" value={formatPrice(result.bigWatchPrice, assetType)} />
            </div>
          ) : (
            <p className="mt-3 text-sm text-stone-600">请输入有效的最高价、最低价、收盘价，且最高价不能低于最低价。</p>
          )}
          <button
            disabled={!result}
            className="mt-5 rounded-md bg-ink px-4 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
            onClick={copyResult}
          >
            {copied ? "已复制" : "复制条件单文案"}
          </button>
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <ListPanel title="本地自选" items={watchlist.map((item) => item.split(":").slice(1).join(" "))} />
          <ListPanel title="最近计算" items={history} />
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
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-stone-500">暂无记录</p>
      )}
    </div>
  );
}
