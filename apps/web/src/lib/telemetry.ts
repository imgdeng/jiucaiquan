// 匿名行为埋点：sendBeacon 上报到 /api/track（Cloudflare Pages Function → D1）。
// 设计原则：纯附加能力，任何失败都静默，绝不影响计算器主流程；
// 不采集身份信息（sid 为 localStorage 内随机串，可随浏览器数据清除）。

export type TrackEvent =
  | "page_view"
  | "search"
  | "select_quote"
  | "calculate"
  | "copy"
  | "asset_switch"
  | "watch_add"
  | "watch_remove";

export type TrackPayload = {
  asset?: "etf" | "stock";
  code?: string;
  name?: string;
  term?: string;
};

const ENDPOINT = "/api/track";
const SID_KEY = "jcq-sid";

function getSid(): string {
  try {
    let sid = localStorage.getItem(SID_KEY);
    if (!sid || !/^[a-f0-9]{32}$/.test(sid)) {
      sid = Array.from(crypto.getRandomValues(new Uint8Array(16)))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
      localStorage.setItem(SID_KEY, sid);
    }
    return sid;
  } catch {
    return "";
  }
}

export function track(event: TrackEvent, payload: TrackPayload = {}): void {
  try {
    const body = JSON.stringify({ e: event, ts: Date.now(), sid: getSid(), ...payload });
    if (typeof navigator !== "undefined" && navigator.sendBeacon) {
      navigator.sendBeacon(ENDPOINT, new Blob([body], { type: "application/json" }));
    } else {
      void fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        keepalive: true,
      }).catch(() => {});
    }
  } catch {
    // 埋点是附加能力，失败静默
  }
}
