// 韭菜圈行情 workflow 外部定时触发器（Cloudflare Worker，单文件，可直接粘贴到后台编辑器）
// 无 import、无构建、纯 JS。密钥：GITHUB_PAT（fine-grained，仅 Actions: Read and write）

const OWNER = "imgdeng";
const REPO = "jiucaiquan";
const WORKFLOW = "market-data.yml";
const REF = "main";
const API = "https://api.github.com";

function headers(env) {
  return {
    Authorization: `Bearer ${env.GITHUB_PAT}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "jcq-cron-worker",
  };
}

function cstToday() {
  return new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 10);
}

async function listTodayRuns(env) {
  const since = `${cstToday()}T00:00:00+08:00`;
  const query = encodeURIComponent(`>=${since}`);
  const url = `${API}/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/runs?created=${query}&per_page=50`;
  const res = await fetch(url, { headers: headers(env) });
  if (!res.ok) throw new Error(`list runs ${res.status}: ${await res.text()}`);
  const body = await res.json();
  return body.workflow_runs || [];
}

async function trigger(env) {
  const runs = await listTodayRuns(env);

  const busy = runs.find((r) => r.status === "queued" || r.status === "in_progress");
  if (busy) {
    console.log(`skip: run ${busy.id} is ${busy.status}`);
    return "skip-busy";
  }

  const done = runs.find((r) => r.conclusion === "success");
  if (done) {
    console.log(`skip: run ${done.id} already succeeded today`);
    return "skip-success";
  }

  const res = await fetch(
    `${API}/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: { ...headers(env), "Content-Type": "application/json" },
      body: JSON.stringify({ ref: REF }),
    },
  );
  if (res.status !== 204) throw new Error(`dispatch ${res.status}: ${await res.text()}`);

  console.log(`dispatched ${WORKFLOW}@${REF} for ${cstToday()}`);
  return "dispatched";
}

export default {
  async scheduled(event, env) {
    try {
      const result = await trigger(env);
      console.log(`cron ${event.cron} -> ${result}`);
    } catch (err) {
      console.error(`cron ${event.cron} failed: ${err && err.message ? err.message : err}`);
      throw err;
    }
  },
};
