// Cloudflare Pages Function: GET /api/quote?high=&low=&close=
//
// US-990：只读对照接口（为演示特意补的测试脚手架，不是生产链路的一环）。
// 它只做两件事：
//   1) 给出独立的业务判据 business_valid；
//   2) 给出按被测页面公式独立复刻的参照值 expected（供 compare() 对账）。
//
// 红线：
//   - 纯计算：不读 D1/KV、不 fetch 外部服务、不落库、不写任何状态；
//   - 判据独立编写：不 import / 复制前端的 validateOHLC 与 calculateConditionOrder；
//   - 不修改线上用户计算路径，页面行为保持原样。

interface FunctionContext {
  request: Request;
}

const CONTRACT_VERSION = "v0.1";

/** 页面默认 ETF 档，参照值保留 4 位小数（与 ConditionOrderTool 默认 assetType 一致） */
const DIGITS = 4;
const SCALE = 10 ** DIGITS;

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

interface NumberParam {
  value?: number;
  error?: string;
}

/** 必填、有限数值字符串；缺失、空白、NaN、Infinity 均按非法参数处理 */
function readNumber(params: URLSearchParams, key: string): NumberParam {
  const raw = params.get(key);
  if (raw === null || raw.trim() === "") {
    return { error: `missing required parameter: ${key}` };
  }
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    return { error: `invalid number for ${key}: ${raw}` };
  }
  return { value };
}

/** 参考页面同一取整口径；极大值会溢出为 ±Infinity，JSON 序列化为 null */
function round4(value: number): number {
  return Math.round(value * SCALE) / SCALE;
}

/** 仅用于 reason 的人类可读展示；超大数不参与取整，避免把有限值显示成 Infinity */
function format(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  return String(Math.abs(value) >= 1e15 ? value : round4(value));
}

export function onRequestGet({ request }: FunctionContext): Response {
  const url = new URL(request.url);

  const highParam = readNumber(url.searchParams, "high");
  const lowParam = readNumber(url.searchParams, "low");
  const closeParam = readNumber(url.searchParams, "close");

  const paramError = highParam.error ?? lowParam.error ?? closeParam.error;
  if (paramError) return json({ error: paramError }, 400);

  const high = highParam.value as number;
  const low = lowParam.value as number;
  const close = closeParam.value as number;

  if (high < low) {
    return json({ error: "invalid OHLC: high must be greater than or equal to low" }, 400);
  }

  // —— 独立业务判据 ——
  // 低吸价 = 基准价 - 波动区间；仅当波动区间大于基准价时低吸价为负，业务上不允许。
  // 等价形式：3*high - 5*low > 2*close。
  const businessInvalid = 3 * high - 5 * low > 2 * close;

  // —— 参照值：按被测页面公式独立复刻（故意允许与页面一起错）——
  const swing = high - low;
  const anchor = (2 * close + high + low) / 4;
  const dip = anchor - swing;
  const rally = anchor + swing;

  const reason = businessInvalid
    ? `波动区间 ${format(swing)} ≥ 基准价 ${format(anchor)}，低吸价业务上不允许为负`
    : `波动区间 ${format(swing)} < 基准价 ${format(anchor)}，低吸价非负，业务上允许`;

  return json({
    input: { high, low, close },
    business_valid: !businessInvalid,
    reason,
    expected: {
      基准价: round4(anchor),
      波动区间: round4(swing),
      低吸价: round4(dip),
      高抛价: round4(rally),
    },
    contract_version: CONTRACT_VERSION,
  });
}
