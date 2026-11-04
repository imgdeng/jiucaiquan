// 剪贴板写入与失败归类（us-105 实现抽为共享工具，行为不变）
// navigator.clipboard 不可用 / 被拒时，回退到隐藏 textarea + execCommand。

/** 同步兜底：选中隐藏 textarea 复制（非 HTTPS / 权限被拒 / 无用户手势场景） */
export function execCommandFallback(text: string): boolean {
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "0";
    ta.style.left = "-9999px";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

/** 将 clipboard 异常归类为可读 reason（not_allowed/no_user_gesture/unknown） */
export function classifyCopyError(err: unknown): string {
  if (err && typeof err === "object") {
    const name = (err as { name?: string }).name;
    if (name === "NotAllowedError") return "not_allowed";
    if (name === "SecurityError" || name === "AbortError") return "no_user_gesture";
  }
  return "unknown";
}

export type CopyOutcome = { ok: true } | { ok: false; reason: string };

/** 复制文本：优先 clipboard API，失败走 execCommand 兜底 */
export async function copyText(text: string): Promise<CopyOutcome> {
  try {
    await navigator.clipboard.writeText(text);
    return { ok: true };
  } catch (err) {
    if (execCommandFallback(text)) return { ok: true };
    return { ok: false, reason: classifyCopyError(err) };
  }
}
