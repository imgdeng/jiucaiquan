// Cloudflare Pages Function: GET /api/top-searches
// 公开聚合接口（无鉴权）：返回近 7 天搜索词 Top5，仅含词条不含次数。
// 复用 D1 `events` 表，参照 functions/api/report.ts 的 terms 查询与 cstDay 计算。
// 未绑定 D1（env.DB 不存在）或查询异常时返回空词条数组 + HTTP 200，保证前端不报错。

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
}
interface FunctionContext {
  request: Request;
  env: Env;
}

const DAYS = 7;

/** 按 UTC+8 计算日历日（YYYY-MM-DD） */
function cstDay(ts: number): string {
  return new Date(ts + 8 * 3600 * 1000).toISOString().slice(0, 10);
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

export async function onRequestGet({ env }: FunctionContext): Promise<Response> {
  const since = cstDay(Date.now() - (DAYS - 1) * 86400000);
  const empty = { terms: [], since, days: DAYS };

  if (!env?.DB) return json(empty);

  try {
    const { results } = await env.DB
      .prepare(
        `SELECT term
         FROM events
         WHERE event = 'search' AND day >= ? AND term IS NOT NULL
         GROUP BY term ORDER BY COUNT(*) DESC LIMIT 5`,
      )
      .bind(since)
      .all<{ term: string }>();

    const terms = (results || [])
      .map((r) => (typeof r.term === "string" ? r.term.trim() : ""))
      .filter((t) => t.length > 0);

    return json({ terms, since, days: DAYS });
  } catch {
    // 任何异常静默降级为空列表，不向用户暴露
    return json(empty);
  }
}
