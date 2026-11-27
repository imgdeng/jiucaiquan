#!/usr/bin/env python3
"""韭菜圈独立看板 · 零依赖（Python 标准库）

启动:  python3 app.py
访问:  http://localhost:8001/kanban
故事目录: ../us/  (team/us/)

阶段判定（文件存在自动判定）:
  00_card.md   → Backlog
  01_req.md    → 需求 · 产品马
  02_eng.md    → 工程 · 工程马
  03_deliver.md→ 交付 · 项目马
  00~03 全在   → 完成
"""

import json
import os
import re
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# ── 路径 ──────────────────────────────────────────────
APP_DIR = os.path.dirname(os.path.abspath(__file__))
STORIES_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "us"))

# ── 看板列（三阶段角色分工）──────────────────────────
COLUMNS = [
    {"key": "backlog", "label": "Backlog", "order": 0},
    {"key": "req", "label": "需求 · 产品马", "order": 1},
    {"key": "eng", "label": "工程 · 工程马", "order": 2},
    {"key": "deliver", "label": "交付 · 项目马", "order": 3},
    {"key": "done", "label": "完成", "order": 4},
]

# 阶段序号 → 文件名
PHASE_FILES = {
    0: "00_card.md",
    1: "01_req.md",
    2: "02_eng.md",
    3: "03_deliver.md",
}

# 列 key → 阶段序号
KEY_TO_PHASE = {c["key"]: c["order"] for c in COLUMNS}


def scan_stories():
    """扫描 team/us/ 目录，返回卡片列表。"""
    cards = []
    if not os.path.isdir(STORIES_DIR):
        return cards
    for entry in sorted(os.listdir(STORIES_DIR)):
        dir_path = os.path.join(STORIES_DIR, entry)
        if not os.path.isdir(dir_path) or entry == "archive":
            continue
        card_file = os.path.join(dir_path, "00_card.md")
        if not os.path.isfile(card_file):
            continue
        meta = parse_card_meta(card_file)
        phase = detect_phase(dir_path)
        cards.append({
            "dir": entry,
            "id": meta.get("id", entry),
            "title": meta.get("title", entry),
            "owner": meta.get("owner", "—"),
            "created": meta.get("created", "—"),
            "priority": meta.get("priority", "P1"),
            "phase": phase,
        })
    return cards


def parse_card_meta(card_path):
    """解析 00_card.md 的元数据表格与标题。"""
    result = {"id": "", "title": "", "owner": "", "created": "", "priority": "P1"}
    try:
        with open(card_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return result

    m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if m:
        result["title"] = m.group(1).strip()

    for field, key in [("编号", "id"), ("当前负责人", "owner"),
                        ("创建日期", "created"), ("优先级", "priority")]:
        pattern = rf"\|\s*\*?\*?{field}\*?\*?\s*\|\s*(.+?)\s*\|"
        m = re.search(pattern, content)
        if m:
            val = m.group(1).strip()
            if key == "priority":
                val = re.sub(r"[^\w]", "", val)
            result[key] = val
    return result


def detect_phase(dir_path):
    """根据存在的阶段文件判定阶段序号 (0-4)。"""
    max_phase = 0
    for phase_num, filename in sorted(PHASE_FILES.items()):
        if phase_num == 0:
            continue
        if os.path.isfile(os.path.join(dir_path, filename)):
            max_phase = phase_num
    # 01/02/03 全部存在 → 完成
    if all(os.path.isfile(os.path.join(dir_path, PHASE_FILES[p])) for p in (1, 2, 3)):
        return 4
    return max_phase


def group_by_column(cards):
    """按列分组，列内按优先级+创建日期排序。"""
    p_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    grouped = {c["key"]: [] for c in COLUMNS}
    for card in cards:
        ph = card["phase"]
        key = COLUMNS[ph]["key"] if 0 <= ph < len(COLUMNS) else "backlog"
        grouped[key].append(card)
    for key in grouped:
        grouped[key].sort(key=lambda c: (p_order.get(c.get("priority", "P1"), 1),
                                         c.get("created", "")))
    return grouped


def move_card(card_dir, target_phase):
    """移动卡片到目标阶段：创建/删除对应阶段文件。"""
    dir_path = os.path.join(STORIES_DIR, card_dir)
    if not os.path.isdir(dir_path):
        return False, f"目录不存在: {card_dir}"

    current = detect_phase(dir_path)
    if target_phase == current:
        return True, "已在目标列"

    # 回退：删除当前及以上的阶段文件
    if target_phase < current:
        for p in range(current, target_phase, -1):
            if p in PHASE_FILES and p > 0:
                fp = os.path.join(dir_path, PHASE_FILES[p])
                if os.path.isfile(fp):
                    os.remove(fp)
        return True, f"已退回 {COLUMNS[target_phase]['label']}"

    # 前进：创建缺失的阶段文件（占位）
    for p in range(current + 1, target_phase + 1):
        if p in PHASE_FILES and p > 0:
            fp = os.path.join(dir_path, PHASE_FILES[p])
            if not os.path.isfile(fp):
                create_placeholder(fp, p)
    return True, f"已移动到 {COLUMNS[target_phase]['label']}"


def create_placeholder(filepath, phase_num):
    labels = {
        1: "需求文档",
        2: "工程记录",
        3: "交付验收",
    }
    owners = {1: "产品马", 2: "工程马", 3: "项目马"}
    label = labels.get(phase_num, "文档")
    owner = owners.get(phase_num, "—")
    content = (f"# {label}\n\n"
               f"> 负责人：{owner}\n\n"
               f"占位文件，请补充内容。\n\n"
               f"---\n\n*看板自动生成 | 请对应角色补充*\n")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


# ── HTML 模板 ─────────────────────────────────────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>韭菜圈看板</title>
<style>
:root{
  --bg:#f5f6fa;--card:#fff;--text:#2c3e50;--muted:#8f959e;
  --border:#e1e4e8;--primary:#e74c3c;--primary-light:#fdecea;
  --radius:8px;--radius-sm:6px;--shadow:0 1px 3px rgba(0,0,0,.08);
  --shadow-hover:0 4px 12px rgba(0,0,0,.12);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);padding:20px}
.header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.header h1{font-size:20px}
.header .sub{font-size:12px;color:var(--muted)}
.kanban-board{display:flex;gap:12px;overflow-x:auto;padding-bottom:16px;min-height:calc(100vh - 100px)}
.kanban-column{flex:1;min-width:220px;max-width:300px;background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);display:flex;flex-direction:column}
.kanban-column-header{padding:14px 16px 10px;border-bottom:2px solid var(--border);font-weight:700;font-size:14px;display:flex;align-items:center;justify-content:space-between}
.kanban-column-header .count{background:var(--primary-light);color:var(--primary);font-size:12px;padding:2px 8px;border-radius:10px;font-weight:600}
.kanban-column-body{flex:1;padding:8px;min-height:120px;display:flex;flex-direction:column;gap:8px;transition:background .2s}
.kanban-column-body.drag-over{background:var(--primary-light)}
.kanban-card{background:#fff;border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;cursor:grab;transition:box-shadow .15s,transform .15s;user-select:none}
.kanban-card:hover{box-shadow:var(--shadow-hover)}
.kanban-card.dragging{opacity:.4;transform:rotate(2deg)}
.kanban-card-id{font-size:11px;color:var(--muted);margin-bottom:4px}
.kanban-card-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px}
.kanban-card-priority{font-size:10px;font-weight:700;padding:1px 6px;border-radius:3px;line-height:1.5;flex-shrink:0}
.priority-p0{background:#ffe0e0;color:#c0392b}
.priority-p1{background:#fff3e0;color:#e67e22}
.priority-p2{background:#f0f0f0;color:#8f959e}
.kanban-card-title{font-size:13px;font-weight:600;margin-bottom:6px;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.kanban-card-meta{font-size:11px;color:var(--muted);display:flex;justify-content:space-between}
.kanban-empty{text-align:center;color:var(--muted);font-size:12px;padding:24px 8px}
.kanban-loading{text-align:center;color:var(--muted);padding:40px;font-size:14px}
.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);padding:10px 20px;border-radius:6px;color:#fff;font-size:13px;opacity:0;transition:opacity .3s;z-index:999}
.toast.show{opacity:1}
.toast.success{background:#27ae60}
.toast.danger{background:#e74c3c}
</style>
</head>
<body>
<div class="header">
  <h1>🐴 韭菜圈看板</h1>
  <div class="sub">三阶段角色分工 · 拖拽推进 · 点击卡片查看</div>
</div>
<div id="kanban-root"><div class="kanban-loading">加载中...</div></div>
<div id="toast" class="toast"></div>
<script>
const COLUMNS=__COLUMNS_JSON__;
let draggedCard=null,draggedFrom=null;

function toast(msg,type){
  const el=document.getElementById('toast');
  el.textContent=msg;el.className='toast show '+(type||'');
  setTimeout(()=>el.className='toast',2000);
}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}

function render(data){
  const root=document.getElementById('kanban-root');
  let html='<div class="kanban-board">';
  COLUMNS.forEach(col=>{
    const cards=(data.cards&&data.cards[col.key])||[];
    html+='<div class="kanban-column" data-column="'+col.key+'">'
       + '<div class="kanban-column-header">'+col.label
       + '<span class="count">'+cards.length+'</span></div>'
       + '<div class="kanban-column-body" data-column="'+col.key+'">';
    if(cards.length===0){html+='<div class="kanban-empty">暂无卡片</div>';}
    else{cards.forEach(c=>{html+=cardHtml(c);});}
    html+='</div></div>';
  });
  html+='</div>';
  root.innerHTML=html;
  bind();
}
function cardHtml(c){
  return '<div class="kanban-card" draggable="true" data-dir="'+esc(c.dir)+'">'
    + '<div class="kanban-card-header">'
    + (c.id?'<div class="kanban-card-id">'+esc(c.id)+'</div>':'')
    + '<span class="kanban-card-priority priority-'+(c.priority||'P1').toLowerCase()+'">'+esc(c.priority||'P1')+'</span>'
    + '</div>'
    + '<div class="kanban-card-title">'+esc(c.title||c.dir)+'</div>'
    + '<div class="kanban-card-meta"><span>'+esc(c.owner||'—')+'</span><span>'+esc(c.created||'—')+'</span></div>'
    + '</div>';
}
function bind(){
  document.querySelectorAll('.kanban-card').forEach(card=>{
    card.addEventListener('dragstart',e=>{
      draggedCard=card;draggedFrom=card.closest('.kanban-column').dataset.column;
      card.classList.add('dragging');e.dataTransfer.effectAllowed='move';
      e.dataTransfer.setData('text/plain',card.dataset.dir);
    });
    card.addEventListener('dragend',()=>{
      card.classList.remove('dragging');draggedCard=null;draggedFrom=null;
      document.querySelectorAll('.kanban-column-body').forEach(c=>c.classList.remove('drag-over'));
    });
    card.addEventListener('click',()=>{
      if(draggedCard)return;
      window.open('/kanban/story/'+encodeURIComponent(card.dataset.dir),'_blank');
    });
  });
  document.querySelectorAll('.kanban-column-body').forEach(col=>{
    col.addEventListener('dragover',e=>{e.preventDefault();e.dataTransfer.dropEffect='move';col.classList.add('drag-over');});
    col.addEventListener('dragleave',()=>col.classList.remove('drag-over'));
    col.addEventListener('drop',e=>{
      e.preventDefault();col.classList.remove('drag-over');
      if(!draggedCard)return;
      const target=col.dataset.column;
      if(target===draggedFrom)return;
      const dir=draggedCard.dataset.dir;
      const phase=COLUMNS.findIndex(c=>c.key===target);
      move(dir,phase,draggedCard);
    });
  });
}
function move(dir,phase,el){
  el.style.opacity='.5';
  fetch('/api/kanban/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dir,phase})})
    .then(r=>{if(!r.ok)return r.json().then(d=>{throw new Error(d.error||'移动失败');});return r.json();})
    .then(d=>{toast(d.message||'已移动','success');load();})
    .catch(e=>{toast(e.message||'移动失败','danger');el.style.opacity='1';});
}
function load(){
  document.getElementById('kanban-root').innerHTML='<div class="kanban-loading">加载中...</div>';
  fetch('/api/kanban').then(r=>r.json()).then(render)
    .catch(()=>{document.getElementById('kanban-root').innerHTML='<div class="kanban-loading">加载失败，请刷新</div>';});
}
document.addEventListener('DOMContentLoaded',load);
</script>
</body>
</html>""".replace("__COLUMNS_JSON__", json.dumps(COLUMNS, ensure_ascii=False))


def render_story_page(dir_name):
    """渲染故事详情页：读取目录下所有 .md 文件，用 marked.js 渲染 Markdown。"""
    dir_path = os.path.join(STORIES_DIR, dir_name)
    if not os.path.isdir(dir_path):
        return ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
                "<title>404</title></head><body><h1>404</h1><p>故事不存在</p>"
                "<a href='/kanban'>← 返回看板</a></body></html>", 404)

    # 读取所有 .md 文件
    md_files = []
    for f in sorted(os.listdir(dir_path)):
        if f.endswith(".md"):
            fp = os.path.join(dir_path, f)
            try:
                with open(fp, "r", encoding="utf-8") as fh:
                    content = fh.read()
                md_files.append({"name": f, "content": content})
            except OSError:
                pass

    if not md_files:
        return (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
                f"<title>{dir_name}</title></head><body>"
                f"<a href='/kanban'>← 返回看板</a><h2>{dir_name}</h2>"
                f"<p>暂无内容</p></body></html>", 200)

    # 将 Markdown 内容嵌入 JSON，前端用 marked.js 渲染
    files_json = json.dumps(md_files, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{dir_name} · 韭菜圈看板</title>
<style>
:root{{--primary:#e74c3c;--bg:#f5f6fa;--card:#fff;--text:#2c3e50;--muted:#8f959e;--border:#e1e4e8;--radius:8px}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);padding:24px}}
.back-link{{display:inline-block;margin-bottom:16px;color:var(--primary);font-size:13px;text-decoration:none}}
.page-wrapper{{max-width:820px;margin:0 auto}}
.file-section{{background:var(--card);border-radius:var(--radius);box-shadow:0 1px 3px rgba(0,0,0,.08);padding:24px 32px;margin-bottom:20px}}
.file-name{{font-size:12px;color:var(--muted);background:#f0f0f0;padding:4px 10px;border-radius:4px;display:inline-block;margin-bottom:16px}}
/* Markdown 样式 */
.md-body{{font-size:15px;line-height:1.75;color:#3e3e3e}}
.md-body h1{{font-size:22px;font-weight:700;margin:20px 0 14px;padding-bottom:8px;border-bottom:2px solid var(--border)}}
.md-body h2{{font-size:18px;font-weight:700;margin:18px 0 10px;padding:8px 12px;background:#1e3a8a;color:#fff;border-radius:4px}}
.md-body h3{{font-size:16px;font-weight:700;margin:14px 0 8px}}
.md-body p{{margin:10px 0}}
.md-body blockquote{{border-left:4px solid #07c160;padding:8px 16px;color:#666;margin:14px 0;background:#f8f8f8;border-radius:0 4px 4px 0}}
.md-body blockquote p{{margin:4px 0}}
.md-body ul,.md-body ol{{padding-left:24px;margin:10px 0}}
.md-body li{{margin:4px 0;line-height:1.7}}
.md-body table{{border-collapse:collapse;width:100%;margin:14px 0;font-size:14px}}
.md-body th,.md-body td{{padding:8px 12px;border:1px solid #dbdbdb;text-align:left}}
.md-body th{{background:#f0f0f0;font-weight:700}}
.md-body code{{background:#f4f4f4;padding:2px 6px;border-radius:3px;font-size:13px;font-family:"SF Mono",Consolas,monospace}}
.md-body pre{{background:#2d2d2d;color:#f8f8f2;padding:14px;border-radius:6px;overflow-x:auto;margin:14px 0}}
.md-body pre code{{background:none;padding:0;color:inherit}}
.md-body a{{color:var(--primary);text-decoration:none}}
.md-body a:hover{{text-decoration:underline}}
.md-body hr{{border:none;border-top:1px solid var(--border);margin:20px 0}}
.md-body strong{{font-weight:700;color:#1e3a8a}}
</style>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
</head>
<body>
<div class="page-wrapper">
  <a href="/kanban" class="back-link">← 返回看板</a>
  <div id="story-content"></div>
</div>
<script>
const FILES = {files_json};
const root = document.getElementById('story-content');
FILES.forEach(f => {{
  const sec = document.createElement('div');
  sec.className = 'file-section';
  const tag = document.createElement('span');
  tag.className = 'file-name';
  tag.textContent = f.name;
  const body = document.createElement('div');
  body.className = 'md-body';
  try {{
    body.innerHTML = marked.parse(f.content);
  }} catch(e) {{
    body.textContent = f.content;
  }}
  sec.appendChild(tag);
  sec.appendChild(body);
  root.appendChild(sec);
}});
</script>
</body>
</html>"""
    return html, 200


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 静默日志

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/kanban" or path == "/":
            self._send(200, HTML_PAGE)
        elif path == "/api/kanban":
            cards = scan_stories()
            grouped = group_by_column(cards)
            self._send(200, json.dumps({"columns": COLUMNS, "cards": grouped},
                                        ensure_ascii=False),
                       "application/json; charset=utf-8")
        elif path.startswith("/kanban/story/"):
            dir_name = path[len("/kanban/story/"):]
            html, code = render_story_page(dir_name)
            self._send(code, html)
        else:
            self._send(404, "Not Found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/kanban/move":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                self._send(400, json.dumps({"error": "JSON 解析失败"}),
                           "application/json; charset=utf-8")
                return
            card_dir = payload.get("dir")
            phase = payload.get("phase")
            if not card_dir or phase is None:
                self._send(400, json.dumps({"error": "缺少 dir 或 phase"}),
                           "application/json; charset=utf-8")
                return
            ok, msg = move_card(card_dir, int(phase))
            code = 200 if ok else 404
            self._send(code, json.dumps({"ok": ok, "message": msg},
                                        ensure_ascii=False),
                       "application/json; charset=utf-8")
        else:
            self._send(404, "Not Found")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"🐴 韭菜圈看板已启动: http://localhost:{port}/kanban")
    print(f"   故事目录: {STORIES_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.server_close()


if __name__ == "__main__":
    main()
