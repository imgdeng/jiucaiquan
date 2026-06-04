export type AssetType = "etf" | "stock";

export type OHLCRaw = {
  open: number;
  high: number;
  low: number;
  close: number;
};

export type ConditionOrderResult = {
  range: number;
  basePrice: number;
  buyPrice: number;
  sellPrice: number;
  smallWatchPrice: number;
  bigWatchPrice: number;
  digits: number;
};

export type StrategyParams = {
  /** 低吸/高抛相对于基准价的波动倍数，默认 1 */
  rangeMultiplier?: number;
  /** 基准价计算方式，默认 weighted（加权 (2*close+high+low)/4），也支持 typical/close/median */
  basePriceMode?: "weighted" | "typical" | "close" | "median";
};

export const DEFAULT_PARAMS: Required<StrategyParams> = {
  rangeMultiplier: 1,
  basePriceMode: "weighted",
};

/** 验证输入是否为有效 OHLC（非 NaN、high>=low、价格为正） */
export function validateOHLC(o: OHLCRaw): string | null {
  const { open, high, low, close } = o;
  if (![open, high, low, close].every((v) => Number.isFinite(v))) return "请输入有效的数字";
  if (high <= 0 || low <= 0 || close <= 0) return "价格必须大于 0";
  if (high < low) return "最高价不能低于最低价";
  if (close > high * 1.5 || close < low * 0.5) return "价格范围看起来异常，请核对";
  return null;
}

/** 核心计算：低吸价、高抛价、观察价 */
export function calculateConditionOrder(
  ohlc: OHLCRaw,
  type: AssetType,
  params: StrategyParams = DEFAULT_PARAMS,
): ConditionOrderResult {
  const { high, low, close } = ohlc;
  const { rangeMultiplier = 1, basePriceMode = "weighted" } = params;

  const range = high - low;

  let basePrice: number;
  switch (basePriceMode) {
    case "typical":
      basePrice = (high + low + close) / 3;
      break;
    case "close":
      basePrice = close;
      break;
    case "median":
      basePrice = (high + low) / 2;
      break;
    case "weighted":
    default:
      basePrice = (2 * close + high + low) / 4;
  }

  const buyPrice = basePrice - range * rangeMultiplier;
  const sellPrice = basePrice + range * rangeMultiplier;
  const smallWatchPrice = 2 * basePrice - high;
  const bigWatchPrice = 2 * basePrice - low;

  const digits = type === "etf" ? 4 : 2;

  return {
    range: round(range, digits),
    basePrice: round(basePrice, digits),
    buyPrice: round(buyPrice, digits),
    sellPrice: round(sellPrice, digits),
    smallWatchPrice: round(smallWatchPrice, digits),
    bigWatchPrice: round(bigWatchPrice, digits),
    digits,
  };
}

function round(value: number, digits: number): number {
  const p = Math.pow(10, digits);
  return Math.round(value * p) / p;
}

export function formatPrice(value: number, digits: number): string {
  return value.toFixed(digits);
}

/** 生成可复制的条件单文案 */
export function buildCopyText(
  code: string,
  name: string,
  result: ConditionOrderResult,
): string {
  const { buyPrice, sellPrice, smallWatchPrice, bigWatchPrice, digits } = result;
  const lines = [
    `${name || code}(${code}) 次日条件单参考：`,
    `· 低吸价：${formatPrice(buyPrice, digits)}`,
    `· 高抛价：${formatPrice(sellPrice, digits)}`,
    `· 小观察价：${formatPrice(smallWatchPrice, digits)}`,
    `· 大观察价：${formatPrice(bigWatchPrice, digits)}`,
    `（仅供学习研究，不构成投资建议，独立判断）`,
  ];
  return lines.join("\n");
}
