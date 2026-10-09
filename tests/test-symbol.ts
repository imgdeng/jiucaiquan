// us-104 回归用例：标的代码归一化 + ETF 白名单分类
// 运行：node --experimental-strip-types tests/test-symbol.ts
// 同时校验前端 (apps/web/src/lib/symbol.ts) 与后端镜像 (functions/_lib/symbol.ts) 输出一致。

import assert from "node:assert/strict";
import * as web from "../apps/web/src/lib/symbol.ts";
import * as fn from "../functions/_lib/symbol.ts";

let pass = 0;
let fail = 0;
function check(name: string, actual: unknown, expected: unknown): void {
  try {
    assert.deepStrictEqual(actual, expected);
    pass++;
  } catch {
    fail++;
    console.error(`✗ ${name}\n  expected: ${JSON.stringify(expected)}\n  actual:   ${JSON.stringify(actual)}`);
  }
}

// —— normalizeCode 样本（覆盖 us-104 卡片要求 + 边界）——
const normCases: Array<[string, string | null]> = [
  ["sh600519", "600519"], // 茅台（带沪前缀）
  ["600519", "600519"], // 茅台（无前缀，手动输入）
  ["sz300308", "300308"], // 中际旭创（带深前缀）
  ["300308", "300308"], // 无前缀
  ["sh511360", "511360"], // 短融ETF（带前缀）
  ["510300", "510300"], // 沪深300ETF（无前缀）
  ["sh510300", "510300"], // 沪深300ETF（带前缀）
  ["sz159915", "159915"], // 深市ETF
  ["bj430047", "430047"], // 北交所
  ["SH600519", "600519"], // 大小写兼容
  [" sh600519 ", "600519"], // 首尾空白
  ["", null], // 空
  ["12345", null], // 5 位
  ["1234567", null], // 7 位
  ["abc123", null], // 非法
  ["sh1234", null], // 去前缀后不足 6 位
];
for (const [input, expected] of normCases) {
  check(`web.normalizeCode(${JSON.stringify(input)})`, web.normalizeCode(input), expected);
  check(`fn.normalizeCode(${JSON.stringify(input)})`, fn.normalizeCode(input), expected);
}

// —— buildEtfSet + classifyAsset（ETF 白名单为准，不用启发式）——
const etfSet = web.buildEtfSet(["sh510300", "sh511360", "sz159915", "510500"]);
check("etfSet 内容", [...etfSet].sort(), ["159915", "510300", "510500", "511360"]);
// 白名单拉取异常/为空时应给出空集合而非崩溃
check("buildEtfSet([])", [...web.buildEtfSet([])], []);

const clsCases: Array<[string, "etf" | "stock" | null]> = [
  ["600519", "stock"], // 茅台是股票，不是 etf（修复历史脏值）
  ["sh600519", "stock"],
  ["510300", "etf"], // 沪深300ETF
  ["sh510300", "etf"],
  ["511360", "etf"],
  ["sz300308", "stock"], // 中际旭创是股票
  ["159915", "etf"],
  ["510500", "etf"],
  ["600000", "stock"], // 浦发银行（不在 ETF 白名单 → stock）
  ["", null],
  ["garbage", null],
];
for (const [code, expected] of clsCases) {
  check(`classifyAsset(${JSON.stringify(code)})`, web.classifyAsset(code, etfSet), expected);
  check(`fn.classifyAsset(${JSON.stringify(code)})`, fn.classifyAsset(code, etfSet), expected);
}

// —— 前后端镜像一致性（防止两份实现漂移）——
const mirrorSamples = ["sh600519", "600519", "sz300308", "sh511360", "510300", "bj430047", "", "abc", "12345"];
for (const s of mirrorSamples) {
  check(`mirror normalizeCode(${JSON.stringify(s)})`, fn.normalizeCode(s), web.normalizeCode(s));
  check(`mirror classifyAsset(${JSON.stringify(s)})`, fn.classifyAsset(s, etfSet), web.classifyAsset(s, etfSet));
}

console.log(`\n${pass} passed, ${fail} failed`);
if (fail > 0) process.exit(1);
