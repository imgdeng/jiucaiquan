// Cloudflare Pages Function: GET /api/report?key=XXX[&days=30][&format=html]
// 从 D1 聚合匿名埋点，输出漏斗/搜索词/热门标的/地域报表。
// 访问控制：需配置环境变量 REPORT_KEY，以 ?key= 传递；未配置时返回 404。

import { normalizeCode, classifyAsset, buildEtfSet } from "../_lib/symbol";

interface D1AllResult<T> {
  results: T[];
}
interface D1Statement {
  bind(...values: unknown[]): {
    run(): Promise<unknown>;
    all<T = Record<string, unknown>>(): Promise<D1AllResult<T>>;
  };
}
interface D1Database {
  prepare(sql: string): D1Statement;
}
interface Env {
  DB?: D1Database;
  REPORT_KEY?: string;
}
interface FunctionContext {
  request: Request;
  env: Env;
}

type Row = Record<string, unknown>;

/** 按 UTC+8 计算日历日（YYYY-MM-DD） */
function cstDay(ts: number): string {
  return new Date(ts + 8 * 3600 * 1000).toISOString().slice(0, 10);
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

function num(v: unknown): number {
  return typeof v === "number" ? v : Number(v) || 0;
}

function table(title: string, cols: string[], rows: Row[]): string {
  const head = cols.map((c) => `<th align="left">${c}</th>`).join("");
  const body = rows
    .map(
      (r) =>
        `<tr>${cols
          .map((c) => `<td>${String(r[c] ?? "")}</td>`)
          .join("")}</tr>`,
    )
    .join("");
  return `<h2>${title}</h2><table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse"><tr>${head}</tr>${body}</table>`;
}

/**
 * us-104：从本站 /data/etf-latest.json 拉取 ETF 名单构建归一化白名单，
 * 用于在报表聚合时按标的属性重分类 asset（股票/ETF），而非沿用历史脏值。
 * 拉取失败返回 null，调用方降级为「沿用历史 asset」。
 */
async function fetchEtfSet(request: Request): Promise<Set<string> | null> {
  try {
    const url = new URL("/data/etf-latest.json", request.url).toString();
    const res = await fetch(url);
    if (!res.ok) return null;
    const data = (await res.json()) as { code?: string }[];
    if (!Array.isArray(data)) return null;
    return buildEtfSet(data.map((d) => d.code ?? ""));
  } catch {
    return null;
  }
}

export async function onRequestGet({ request, env }: FunctionContext): Promise<Response> {
  if (!env?.REPORT_KEY) return json({ error: "report not configured" }, 404);

  const url = new URL(request.url);
  if (url.searchParams.get("key") !== env.REPORT_KEY) {
    return json({ error: "unauthorized" }, 403);
  }
  if (!env.DB) return json({ error: "D1 binding 'DB' not found" }, 503);

  const days = Math.min(Math.max(Number(url.searchParams.get("days")) || 30, 1), 90);
  const since = cstDay(Date.now() - (days - 1) * 86400000);
  const q = (sql: string) => env.DB!.prepare(sql).bind(since).all<Row>();

  const [funnel, daily, terms, codes, countries, etfSet] = await Promise.all([
    q(
      `SELECT event, COUNT(*) AS c, COUNT(DISTINCT sid) AS uv
       FROM events WHERE day >= ? GROUP BY event ORDER BY c DESC`,
    ),
    q(
      `SELECT day, event, COUNT(*) AS c, COUNT(DISTINCT sid) AS uv
       FROM events WHERE day >= ? GROUP BY day, event ORDER BY day, c DESC`,
    ),
    q(
      `SELECT term, COUNT(*) AS c, COUNT(DISTINCT sid) AS uv
       FROM events WHERE event = 'search' AND day >= ? AND term IS NOT NULL
       GROUP BY term ORDER BY c DESC LIMIT 20`,
    ),
    // us-104：取原始明细行（不再 SQL GROUP BY code），交由 JS 按归一化 code 聚合，
    // 以合并 sh600519/600519 等同一标的的不同写法，并按 ETF 白名单重分类 asset
    q(
      `SELECT event, code, name, asset, sid
       FROM events WHERE event IN ('calculate', 'copy') AND day >= ? AND code IS NOT NULL`,
    ),
    q(
      `SELECT COALESCE(country, '--') AS country, COUNT(*) AS c
       FROM events WHERE day >= ? GROUP BY country ORDER BY c DESC LIMIT 10`,
    ),
    fetchEtfSet(request),
  ]);

  const funnelRows = funnel.results.map((r) => ({
    event: String(r.event),
    events: num(r.c),
    users: num(r.uv),
  }));
  const dailyRows = daily.results.map((r) => ({
    day: String(r.day),
    event: String(r.event),
    events: num(r.c),
    users: num(r.uv),
  }));
  const termRows = terms.results.map((r) => ({
    term: String(r.term),
    searches: num(r.c),
    users: num(r.uv),
  }));
  // us-104：按归一化 code 在 JS 侧聚合，合并同一标的的不同写法（sh600519/600519），
  // users 用 Set 去重 sid 避免跨写法重复计数；asset 用 ETF 白名单重分类（拉取失败则沿用历史值）
  const codeAgg = new Map<
    string,
    { code: string; name: string; asset: string; calc: number; copies: number; users: Set<string> }
  >();
  for (const r of codes.results) {
    const nc = normalizeCode(r.code);
    if (!nc) continue; // 归一化失败的脏码不计入热门标的
    let g = codeAgg.get(nc);
    if (!g) {
      g = { code: nc, name: "", asset: "", calc: 0, copies: 0, users: new Set<string>() };
      codeAgg.set(nc, g);
    }
    if (r.event === "calculate") g.calc += 1;
    else if (r.event === "copy") g.copies += 1;
    if (typeof r.sid === "string" && r.sid) g.users.add(r.sid);
    if (!g.name && r.name) g.name = String(r.name);
    if (!g.asset && r.asset) g.asset = String(r.asset);
  }
  const codeRows = [...codeAgg.values()]
    .map((g) => ({
      code: g.code,
      name: g.name,
      // 有白名单则按标的属性重分类，修正历史脏值（茅台 stock、510300 etf）；否则沿用历史 asset
      asset: etfSet ? (classifyAsset(g.code, etfSet) ?? g.asset) : g.asset,
      calc: g.calc,
      copies: g.copies,
      users: g.users.size,
    }))
    .sort((a, b) => b.copies - a.copies || b.calc - a.calc)
    .slice(0, 20);
  const countryRows = countries.results.map((r) => ({
    country: String(r.country),
    events: num(r.c),
  }));

  if (url.searchParams.get("format") === "html") {
    const html = `<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>韭菜圈埋点报表</title></head>
<body style="font-family:system-ui,sans-serif">
<h1>韭菜圈匿名埋点报表</h1>
<p>区间：${since} 起近 ${days} 天 · 生成于 ${new Date().toISOString()}</p>
${table("事件漏斗", ["event", "events", "users"], funnelRows as unknown as Row[])}
${table("热门搜索词 Top20", ["term", "searches", "users"], termRows as unknown as Row[])}
${table("热门标的 Top20（计算/复制）", ["code", "name", "asset", "calc", "copies", "users"], codeRows as unknown as Row[])}
<p style="color:#666;font-size:0.85em">注（us-104）：topCodes 已按归一化 code 聚合（去除 sh/sz/bj 前缀，sh600519/600519 合并为一行）；asset 以 /data/etf-latest.json 白名单重分类，修正历史脏值（股票误标 etf）。D1 原始明细保留带前缀写法，可回溯。</p>
${table("地域分布", ["country", "events"], countryRows as unknown as Row[])}
${table("每日明细（前 30 行）", ["day", "event", "events", "users"], dailyRows.slice(0, 30) as unknown as Row[])}
</body></html>`;
    return new Response(html, {
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  }

  return json({
    generatedAt: new Date().toISOString(),
    since,
    days,
    funnel: funnelRows,
    daily: dailyRows,
    topTerms: termRows,
    topCodes: codeRows,
    // us-104 口径标注：code 已归一化（去前缀），asset 已按 ETF 白名单重分类；D1 原始明细保留可回溯
    topCodesNote:
      "code 归一化为不带前缀 6 位码（sh600519→600519）；asset 按 /data/etf-latest.json 白名单重分类。ETF 白名单拉取失败时 asset 沿用历史值。原始明细保留带前缀写法，可回溯。",
    countries: countryRows,
  });
}
