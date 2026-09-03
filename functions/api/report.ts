// Cloudflare Pages Function: GET /api/report?key=XXX[&days=30][&format=html]
// 从 D1 聚合匿名埋点，输出漏斗/搜索词/热门标的/地域报表。
// 访问控制：需配置环境变量 REPORT_KEY，以 ?key= 传递；未配置时返回 404。

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

  const [funnel, daily, terms, codes, countries] = await Promise.all([
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
    q(
      `SELECT code, name, asset,
         SUM(CASE WHEN event = 'calculate' THEN 1 ELSE 0 END) AS calc,
         SUM(CASE WHEN event = 'copy' THEN 1 ELSE 0 END) AS copies,
         COUNT(DISTINCT sid) AS users
       FROM events WHERE event IN ('calculate', 'copy') AND day >= ? AND code IS NOT NULL
       GROUP BY code ORDER BY copies DESC, calc DESC LIMIT 20`,
    ),
    q(
      `SELECT COALESCE(country, '--') AS country, COUNT(*) AS c
       FROM events WHERE day >= ? GROUP BY country ORDER BY c DESC LIMIT 10`,
    ),
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
  const codeRows = codes.results.map((r) => ({
    code: String(r.code),
    name: String(r.name ?? ""),
    asset: String(r.asset ?? ""),
    calc: num(r.calc),
    copies: num(r.copies),
    users: num(r.users),
  }));
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
    countries: countryRows,
  });
}
