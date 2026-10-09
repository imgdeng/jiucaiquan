// 标的代码归一化 + 资产归类（us-104）
// 修复同一标的出现多个 code（sh600519 / 600519）且股票被错标为 etf 的数据损坏问题。
// 纯函数、无环境依赖，前端与 functions/ 各保留一份同源实现（见 functions/_lib/symbol.ts），
// 由 tests/test-symbol.ts 保证两份实现输出一致。

/** A 股市场前缀：沪 sh / 深 sz / 北 bj */
const MARKET_PREFIXES = ["sh", "sz", "bj"];

/**
 * 归一化标的代码：去除市场前缀，统一为不带前缀的 6 位数字码。
 * - sh600519 → 600519
 * - 600519   → 600519
 * - sz300308 → 300308
 * - sh511360 → 511360
 * - 非法输入 → null
 */
export function normalizeCode(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  let v = raw.trim().toLowerCase();
  for (const p of MARKET_PREFIXES) {
    if (v.startsWith(p)) {
      v = v.slice(p.length);
      break;
    }
  }
  return /^\d{6}$/.test(v) ? v : null;
}

/**
 * 用 ETF 白名单判定资产类型：白名单内为 etf，否则为 stock。
 * 归类以白名单为准，不用代码段启发式（遵 us-104 顾问建议）。
 * 传入的 etfSet 应为 buildEtfSet 构建的「归一化后」代码集合。
 */
export function classifyAsset(
  code: unknown,
  etfSet: Set<string>,
): "etf" | "stock" | null {
  const n = normalizeCode(code);
  if (!n) return null;
  return etfSet.has(n) ? "etf" : "stock";
}

/**
 * 从「带前缀」的代码列表构建 ETF 归一化白名单。
 * 输入如 ["sh511360", "sh510300", ...]，输出 {"511360","510300",...}。
 */
export function buildEtfSet(prefixedCodes: string[]): Set<string> {
  const s = new Set<string>();
  for (const c of prefixedCodes) {
    const n = normalizeCode(c);
    if (n) s.add(n);
  }
  return s;
}
