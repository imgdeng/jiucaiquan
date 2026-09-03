// Cloudflare Pages Function: POST /api/track
// 接收前端匿名埋点，字段白名单收敛后写入 Cloudflare D1。
// 未绑定 D1（env.DB 不存在）时静默返回 204，保证站点在未配置阶段也不受影响。

interface D1Statement {
  bind(...values: unknown[]): { run(): Promise<unknown> };
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

const EVENTS = new Set([
  "page_view",
  "search",
  "select_quote",
  "calculate",
  "copy",
  "asset_switch",
  "watch_add",
  "watch_remove",
]);
const ASSETS = new Set(["etf", "stock"]);
const MAX_BODY_BYTES = 2048;

function cleanText(value: unknown, max: number): string | null {
  if (typeof value !== "string") return null;
  const v = value
    .replace(/[\x00-\x1f\x7f]/g, "")
    .trim()
    .slice(0, max);
  return v || null;
}

function cleanCode(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const v = value.trim().slice(0, 16);
  return /^[A-Za-z0-9._-]{1,16}$/.test(v) ? v : null;
}

function cleanSid(value: unknown): string | null {
  if (typeof value !== "string") return null;
  return /^[a-f0-9]{16,64}$/.test(value) ? value : null;
}

/** 按 UTC+8 计算日历日（YYYY-MM-DD） */
function cstDay(ts: number): string {
  return new Date(ts + 8 * 3600 * 1000).toISOString().slice(0, 10);
}

export async function onRequestPost({ request, env }: FunctionContext): Promise<Response> {
  const noop = new Response(null, { status: 204 });
  try {
    if (!env?.DB) return noop;
    const raw = await request.text();
    if (raw.length > MAX_BODY_BYTES) return noop;

    const data = JSON.parse(raw) as Record<string, unknown>;
    const event = typeof data.e === "string" ? data.e : "";
    if (!EVENTS.has(event)) return noop;

    const ts =
      typeof data.ts === "number" && data.ts > 0 && data.ts < 4.1e12 ? data.ts : Date.now();
    const asset = ASSETS.has(data.asset as string) ? (data.asset as string) : null;
    const countryMatch = (request.headers.get("cf-ipcountry") || "").match(/^[A-Z]{2}$/);
    const country = countryMatch ? countryMatch[0] : null;

    await env.DB.prepare(
      `INSERT INTO events (ts, received_at, day, event, asset, code, name, term, sid, country)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
      .bind(
        ts,
        Date.now(),
        cstDay(ts),
        event,
        asset,
        cleanCode(data.code),
        cleanText(data.name, 20),
        cleanText(data.term, 24),
        cleanSid(data.sid),
        country,
      )
      .run();
  } catch {
    // 埋点为附加能力，任何异常静默处理，不向用户暴露
  }
  return noop;
}
