// Part 2 locations: row-size workbook -> preview (read only) -> apply exactly that preview.
// Every value from the file is shown with textContent (never innerHTML), so a cell can't inject markup.

let fileData = null;      // { filename, data_base64 }
let lastPlanHash = null;  // apply only what was previewed

function el(tag, cls, txt) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt !== undefined && txt !== null) e.textContent = String(txt);
  return e;
}

function showToast(msg, kind) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "fixed bottom-4 right-4 max-w-md px-4 py-3 rounded-xl text-sm font-semibold shadow-xl " +
    (kind === "error" ? "bg-red-600 text-white" : "bg-emerald-500 text-slate-950");
  t.hidden = false;
  setTimeout(() => { t.hidden = true; }, 6000);
}

async function loadSummary() {
  const box = document.getElementById("summary");
  try {
    const res = await fetch("/api/locations/summary");
    const data = await res.json();
    if (!res.ok) { box.textContent = data.detail || "Could not load"; return; }
    if (!data.length) { box.textContent = "No Part 2 locations yet."; return; }
    box.textContent = "";
    data.forEach(r => box.appendChild(el("div", "", `${r.type}${r.area ? " / " + r.area : ""}: ${r.count} ${r.active ? "active" : "deactivated"}`)));
  } catch (e) {
    box.textContent = "Could not load";
  }
}

function countBox(label, n, cls) {
  const d = el("div", "rounded-xl border border-slate-800 p-3 " + (cls || ""));
  d.appendChild(el("div", "text-2xl font-black", n));
  d.appendChild(el("div", "text-[10px] uppercase text-slate-400", label));
  return d;
}

function listBlock(title, items, cls) {
  const wrap = el("div", "rounded-xl border p-3 " + cls);
  wrap.appendChild(el("div", "font-bold mb-1", `${title} (${items.length})`));
  const ul = el("ul", "list-disc pl-5 space-y-0.5 max-h-48 overflow-y-auto");
  items.forEach(i => ul.appendChild(el("li", "", i)));
  wrap.appendChild(ul);
  return wrap;
}

function renderPreview(p) {
  document.getElementById("previewSection").hidden = false;
  const counts = document.getElementById("counts");
  counts.textContent = "";
  counts.appendChild(countBox("spots in the table", p.target_total));
  counts.appendChild(countBox("active now", p.existing_active));
  counts.appendChild(countBox("to create", p.create_count, "text-emerald-300"));
  counts.appendChild(countBox("to reactivate", p.reactivate.length, "text-sky-300"));
  counts.appendChild(countBox("to deactivate", p.deactivate.length, "text-amber-300"));

  const problems = document.getElementById("problems");
  problems.textContent = "";
  if (p.errors.length) problems.appendChild(listBlock("Errors in the file: fix them in the workbook", p.errors, "border-red-500/50 text-red-200"));
  if (p.unconfirmed.length) problems.appendChild(listBlock("Lines not marked OK: check them, then write OK in the last column", p.unconfirmed, "border-amber-500/50 text-amber-200"));
  if (p.blocked.length) problems.appendChild(listBlock("Spots that would be deactivated but still hold stock: refused", p.blocked, "border-red-500/50 text-red-200"));
  if (p.stock_outside_table.length) problems.appendChild(listBlock("Stock today at spots outside this table (not changed; handled when rows are linked)", p.stock_outside_table, "border-slate-600 text-slate-300"));

  const tbody = document.getElementById("perRow");
  tbody.textContent = "";
  p.per_row.forEach(r => {
    const tr = el("tr", "border-t border-slate-800");
    [r.row, r.shelf_sections ?? "", r.shelf_levels ?? r.levels ?? "", r.ground_front ?? "", r.ground_back ?? "", r.spots]
      .forEach((v, i) => tr.appendChild(el("td", i === 0 ? "py-1 pr-3" : "text-right pr-3", v)));
    tbody.appendChild(tr);
  });
  const specials = Object.entries(p.specials || {}).map(([c, keep]) => `${c}: ${keep ? "keep" : "not wanted"}`);

  const lists = document.getElementById("lists");
  lists.textContent = "";
  if (specials.length) lists.appendChild(el("div", "text-slate-300", "Special spots: " + specials.join(", ")));
  if (p.create.length) lists.appendChild(el("div", "text-slate-400", `First codes to create: ${p.create.join(", ")}${p.create_count > p.create.length ? " …" : ""}`));
  if (p.reactivate.length) lists.appendChild(listBlock("To reactivate", p.reactivate, "border-sky-500/40 text-sky-200"));
  if (p.deactivate.length) lists.appendChild(listBlock("To deactivate", p.deactivate, "border-amber-500/40 text-amber-200"));

  lastPlanHash = p.can_apply ? p.plan_hash : null;
  document.getElementById("applyBtn").disabled = !p.can_apply;
  document.getElementById("applyHint").textContent = p.can_apply
    ? "Applies exactly the counts above, in one step. Each change is recorded with your name."
    : (p.errors.length || p.unconfirmed.length || p.blocked.length ? "Not possible until the problems above are fixed." : "Nothing to change.");
}

async function post(url, body) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  let data = {};
  try { data = await res.json(); } catch (e) { /* non-JSON */ }
  return { res, data };
}

document.getElementById("fileInput").addEventListener("change", (ev) => {
  const f = ev.target.files[0];
  fileData = null;
  lastPlanHash = null;
  document.getElementById("previewSection").hidden = true;
  document.getElementById("applyBtn").disabled = true;
  document.getElementById("previewBtn").disabled = !f;
  if (!f) return;
  const reader = new FileReader();
  reader.onload = () => { fileData = { filename: f.name, data_base64: String(reader.result) }; };
  reader.readAsDataURL(f);
});

document.getElementById("previewBtn").addEventListener("click", async () => {
  if (!fileData) { showToast("Choose the workbook first", "error"); return; }
  const { res, data } = await post("/api/locations/import/preview", fileData);
  if (!res.ok) { showToast(data.detail || "Preview failed", "error"); return; }
  renderPreview(data);
});

document.getElementById("applyBtn").addEventListener("click", async () => {
  if (!fileData || !lastPlanHash) return;
  const n = document.getElementById("counts").innerText.replace(/\s+/g, " ");
  if (!confirm("Apply this preview to the live locations?\n\n" + n + "\n\nSpots are never deleted; every change is recorded with your name.")) return;
  const { res, data } = await post("/api/locations/import/apply", { ...fileData, plan_hash: lastPlanHash });
  if (!res.ok) { showToast(data.detail || "Apply failed: nothing was changed", "error"); return; }
  showToast(`Done: ${data.created} created, ${data.reactivated} reactivated, ${data.deactivated} deactivated`, "success");
  lastPlanHash = null;
  document.getElementById("applyBtn").disabled = true;
  loadSummary();
});

document.querySelectorAll(".label-btn").forEach(btn => btn.addEventListener("click", () => {
  const kind = btn.dataset.label;
  let qs = "all=true";
  if (kind === "code" || kind === "row") {
    const v = document.getElementById(kind === "code" ? "labelCode" : "labelRow").value.trim();
    if (!v) { showToast(kind === "code" ? "Type a code first" : "Type a row number, WALL or SPECIAL", "error"); return; }
    qs = `${kind}=${encodeURIComponent(v)}`;
  }
  window.open(`/api/locations/labels.pdf?${qs}`, "_blank");
}));

loadSummary();
