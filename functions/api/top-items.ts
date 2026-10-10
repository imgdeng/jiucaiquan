// Cloudflare Pages Function: GET /api/top-items
// 公开聚合接口（无鉴权）：返回近 30 天 calculate 事件的 Top5 热门标的，
// 仅含 {code,name,asset} 不含次数，避免被刷榜游戏。
// 复用 D1 `events` 表，参照 functions/api/report.ts 的归一化聚合（us-104）。
// 未绑定 D1（env.DB 不存在）或查询异常时返回空 items + HTTP 200，保证前端不报错。
// 30 天不足 5 条时回退 60 天兜底（01_req 技术备注允许）。

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
}
interface FunctionContext {
  request: Request;
  env: Env;
}

const DAYS = 30;
const FALLBACK_DAYS = 60;
const LIMIT = 5;

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

/** us-105：从本站 /data/etf-latest.json 拉 ETF 白名单用于 asset 重分类（与 report.ts 一致） */
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

interface AggItem {
  code: string;
  name: string;
  asset: string;
  calc: number;
  users: Set<string>;
}

/** 拉取指定天数内 calculate 明细，JS 侧归一化聚合（合并 sh600519/600519） */
async function aggregateCalculate(
  env: Env,
  since: string,
  days: number,
): Promise<AggItem[]> {
  const { results } = await env
    .DB!.prepare(
      `SELECT code, name, asset, sid
       FROM events WHERE event = 'calculate' AND day >= ? AND code IS NOT NULL`,
    )
    .bind(since)
    .all<{ code: string; name: string | null; asset: string | null; sid: string | null }>();

  const agg = new Map<string, AggItem>();
  for (const r of results || []) {
    const nc = normalizeCode(r.code);
    if (!nc) continue; // 归一化失败的脏码不计入
    let g = agg.get(nc);
    if (!g) {
      g = { code: nc, name: "", asset: "", calc: 0, users: new Set<string>() };
      agg.set(nc, g);
    }
    g.calc += 1;
    if (typeof r.sid === "string" && r.sid) g.users.add(r.sid);
    if (!g.name && r.name) g.name = String(r.name);
    if (!g.asset && r.asset) g.asset = String(r.asset);
  }
  return [...agg.values()].sort((a, b) => b.calc - a.calc || b.users.size - a.users.size);
}

export async function onRequestGet({ request, env }: FunctionContext): Promise<Response> {
  const since30 = cstDay(Date.now() - (DAYS - 1) * 86400000);
  const empty = { items: [], since: since30, days: DAYS, source: "calculate" };
  if (!env?.DB) return json(empty);

  try {
    let items = await aggregateCalculate(env, since30, DAYS);
    // 30 天不足 5 条 → 回退 60 天兜底（技术备注允许，AC 不强制）
    if (items.length < LIMIT) {
      const since60 = cstDay(Date.now() - (FALLBACK_DAYS - 1) * 86400000);
      const fallback = await aggregateCalculate(env, since60, FALLBACK_DAYS);
      if (fallback.length > items.length) items = fallback;
    }

    const etfSet = await fetchEtfSet(request);

    const top = items
      .slice(0, LIMIT)
      .map((g) => ({
        code: g.code,
        name: g.name || g.code,
        // 有白名单则按标的属性重分类（修正历史脏值），否则沿用历史 asset
        asset: etfSet ? (classifyAsset(g.code, etfSet) ?? g.asset) : g.asset,
      }));

    return json({ items: top, since: since30, days: DAYS, source: "calculate" });
  } catch {
    // 任何异常静默降级为空列表，不向用户暴露
    return json(empty);
  }
}
