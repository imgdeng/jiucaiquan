// US-990 接口自测：GET /api/quote
// 运行：node --experimental-strip-types tests/test-quote.ts
//
// 覆盖：5 组固定输入、非法参数 400、同参数两次逐字一致、响应时间 < 1s。
// 直接调用 Pages Function 的 onRequestGet，不依赖 D1 / 外部网络。

import assert from "node:assert/strict";
import { onRequestGet } from "../functions/api/quote.ts";

let pass = 0;
let fail = 0;

async function check(name: string, fn: () => Promise<void> | void): Promise<void> {
  try {
    await fn();
    pass++;
  } catch (err) {
    fail++;
    console.error(`✗ ${name}\n  ${(err as Error).message}`);
  }
}

function call(query: string): Response {
  return onRequestGet({ request: new Request(`https://jiucaiquan.com/api/quote?${query}`) });
}

async function body(res: Response): Promise<Record<string, any>> {
  return JSON.parse(await res.text()) as Record<string, any>;
}

interface Case {
  query: string;
  valid: boolean;
}

const fixedCases: Case[] = [
  { query: "high=9&low=0.338&close=0.342", valid: false },
  { query: "high=3&low=1&close=1", valid: false },
  { query: "high=10&low=9&close=9.5", valid: true },
  { query: "high=999999999999999&low=1.0&close=1.5", valid: false },
  { query: "high=1e308&low=1.0&close=1.5", valid: false },
];

for (const c of fixedCases) {
  await check(`200 + business_valid=${c.valid} (${c.query})`, async () => {
    const res = call(c.query);
    assert.equal(res.status, 200);
    assert.match(res.headers.get("content-type") || "", /application\/json/);
    const data = await body(res);
    assert.equal(data.business_valid, c.valid);
    assert.equal(data.contract_version, "v0.1");
    assert.ok(data.expected && typeof data.expected === "object");
    assert.ok(typeof data.reason === "string" && data.reason.length > 0);
  });
}

await check("首组参照值逐字段匹配契约", async () => {
  const data = await body(call("high=9&low=0.338&close=0.342"));
  assert.deepEqual(data.input, { high: 9, low: 0.338, close: 0.342 });
  assert.equal(data.expected["基准价"], 2.5055);
  assert.equal(data.expected["波动区间"], 8.662);
  assert.equal(data.expected["低吸价"], -6.1565);
  assert.equal(data.expected["高抛价"], 11.1675);
});

await check("3/1/1 与 10/9/9.5 低吸价参照值", async () => {
  assert.equal((await body(call("high=3&low=1&close=1"))).expected["低吸价"], -0.5);
  assert.equal((await body(call("high=10&low=9&close=9.5"))).expected["低吸价"], 8.5);
});

await check("999999999999999 低吸价为负数", async () => {
  const data = await body(call("high=999999999999999&low=1.0&close=1.5"));
  assert.ok(typeof data.expected["低吸价"] === "number" && data.expected["低吸价"] < 0);
});

await check("1e308 不抛异常，溢出字段为 null 或数字", async () => {
  const data = await body(call("high=1e308&low=1.0&close=1.5"));
  const dip = data.expected["低吸价"];
  assert.ok(dip === null || typeof dip === "number");
});

await check("open 可选且不影响结果", async () => {
  const withOpen = call("high=9&low=0.338&close=0.342&open=1.23");
  const without = call("high=9&low=0.338&close=0.342");
  assert.equal(withOpen.status, 200);
  assert.equal(await withOpen.text(), await without.text());
});

const badCases = [
  "low=0.338&close=0.342",
  "high=9&close=0.342",
  "high=9&low=0.338",
  "high=abc&low=0.338&close=0.342",
  "high=9&low=&close=0.342",
  "high=9&low=0.338&close=NaN",
  "high=Infinity&low=0.338&close=0.342",
  "high=1&low=9&close=5",
];

for (const q of badCases) {
  await check(`400 而非 500 (${q})`, async () => {
    const res = call(q);
    assert.equal(res.status, 400);
    const data = await body(res);
    assert.ok(typeof data.error === "string" && data.error.length > 0);
  });
}

await check("同参数连跑两次响应逐字一致", async () => {
  const q = "high=9&low=0.338&close=0.342";
  const first = await call(q).text();
  const second = await call(q).text();
  assert.equal(first, second);
});

await check("单次请求耗时 < 1000ms", () => {
  const start = performance.now();
  call("high=9&low=0.338&close=0.342");
  assert.ok(performance.now() - start < 1000);
});

console.log(`\n${pass} passed, ${fail} failed`);
if (fail > 0) process.exit(1);
