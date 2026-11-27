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

// ---- D0: deactivate empty Part 2 rows
let emptyPlan = null;

function rowLine(r) {
  return `${r.style} · ${r.color || ""} · ${r.size || ""} · ${r.location} → ${r.code} · ${r.quantity} pcs`;
}

async function getJson(url) {
  const res = await fetch(url);
  let data = {};
  try { data = await res.json(); } catch (e) { /* non-JSON */ }
  return { res, data };
}

document.getElementById("emptyPreviewBtn").addEventListener("click", async () => {
  const { res, data } = await getJson("/api/locations/empty-rows/preview");
  if (!res.ok) { showToast(data.detail || "Preview failed", "error"); return; }
  emptyPlan = data;
  const box = document.getElementById("emptyResult");
  box.textContent = "";
  box.appendChild(listBlock("Always deactivated: spot no longer exists", data.outside.map(rowLine), "border-amber-500/40 text-amber-200"));
  const wrap = el("div", "rounded-xl border border-sky-500/40 p-3 text-sky-200");
  wrap.appendChild(el("div", "font-bold mb-1", `At spots that still exist, only if ticked (${data.inside.length})`));
  const list = el("div", "space-y-0.5 max-h-48 overflow-y-auto");
  data.inside.forEach(r => {
    const label = el("label", "flex items-center gap-2");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "empty-include";
    cb.value = String(r.id);
    label.appendChild(cb);
    label.appendChild(el("span", "", rowLine(r)));
    list.appendChild(label);
  });
  wrap.appendChild(list);
  box.appendChild(wrap);
  box.hidden = false;
  const can = data.outside.length > 0 || data.inside.length > 0;
  document.getElementById("emptyApplyBtn").disabled = !can;
  document.getElementById("emptyHint").textContent = can ? "" : "No empty Part 2 rows.";
});

document.getElementById("emptyApplyBtn").addEventListener("click", async () => {
  if (!emptyPlan) return;
  const include = [...document.querySelectorAll(".empty-include:checked")].map(cb => parseInt(cb.value, 10));
  const n = emptyPlan.outside.length + include.length;
  if (!n) { showToast("Nothing selected", "error"); return; }
  if (!confirm(`Deactivate ${n} Part 2 row(s) at qty 0 (${emptyPlan.outside.length} at old spots + ${include.length} ticked)?\n\nEach one is recorded with your name. Rows are never deleted.`)) return;
  const { res, data } = await post("/api/locations/empty-rows/apply", { plan_hash: emptyPlan.plan_hash, include_ids: include });
  if (!res.ok) { showToast(data.detail || "Nothing was changed", "error"); return; }
  showToast(`Deactivated ${data.deactivated} row(s)`, "success");
  emptyPlan = null;
  document.getElementById("emptyApplyBtn").disabled = true;
  document.getElementById("emptyResult").hidden = true;
});

// ---- D1 / D2: link Part 2 stock to locations
let linkPlan = null;

document.getElementById("linkPreviewBtn").addEventListener("click", async () => {
  const { res, data } = await getJson("/api/locations/link/preview");
  if (!res.ok) { showToast(data.detail || "Report failed", "error"); return; }
  linkPlan = data;
  const box = document.getElementById("linkResult");
  box.textContent = "";
  const counts = el("div", "grid grid-cols-2 md:grid-cols-5 gap-3 text-center");
  counts.appendChild(countBox("will be linked", data.counts.will_link, "text-emerald-300"));
  counts.appendChild(countBox("pieces in them", data.will_link_pieces, "text-emerald-300"));
  counts.appendChild(countBox("already linked", data.counts.linked_ok));
  counts.appendChild(countBox("no spot, with stock", data.counts.unmatched_stock, data.counts.unmatched_stock ? "text-red-300" : ""));
  counts.appendChild(countBox("no spot, at qty 0", data.counts.unmatched_empty));
  box.appendChild(counts);
  box.appendChild(el("div", "text-slate-300", `After linking: ${data.linked_after.rows} rows / ${data.linked_after.pieces} pcs linked. ` +
    "Per row: " + data.per_row.map(r => `Row ${r.row}: ${r.rows} / ${r.pieces}`).join(" · ")));
  if (data.unmatched_stock.length) box.appendChild(listBlock("Rows WITH STOCK and no active spot: fix these first (refused)", data.unmatched_stock.map(rowLine), "border-red-500/50 text-red-200"));
  if (data.linked_other.length) box.appendChild(listBlock("Linked to a different spot: check these first (refused)", data.linked_other.map(r => rowLine(r) + ` · linked to ${r.linked_to}`), "border-red-500/50 text-red-200"));
  if (data.unmatched_empty.length) box.appendChild(listBlock("At qty 0 with no spot (skipped; see step 4)", data.unmatched_empty.map(rowLine), "border-slate-600 text-slate-300"));
  box.hidden = false;
  document.getElementById("linkApplyBtn").disabled = !data.can_apply;
  document.getElementById("linkHint").textContent = data.can_apply ? "" :
    (data.counts.will_link ? "Not possible until the red lists are empty." : "Nothing to link.");
});

document.getElementById("linkApplyBtn").addEventListener("click", async () => {
  if (!linkPlan) return;
  if (!confirm(`Link ${linkPlan.counts.will_link} Part 2 row(s) (${linkPlan.will_link_pieces} pcs) to their locations?\n\nQuantities do not change. Each link is recorded with your name.`)) return;
  const { res, data } = await post("/api/locations/link/apply", { plan_hash: linkPlan.plan_hash });
  if (!res.ok) { showToast(data.detail || "Nothing was changed", "error"); return; }
  showToast(`Linked ${data.linked} row(s), ${data.pieces} pcs. Linked in total: ${data.linked_after.rows} rows / ${data.linked_after.pieces} pcs`, "success");
  linkPlan = null;
  document.getElementById("linkApplyBtn").disabled = true;
  loadLinkRuns();
});

// ---- D2 undo: unlink a whole link run (default: the last one) or every row at one location
let unlinkPlan = null;

async function loadLinkRuns() {
  const sel = document.getElementById("unlinkRun");
  const { res, data } = await getJson("/api/locations/unlink/runs");
  if (!res.ok) return;
  sel.textContent = "";
  sel.appendChild(el("option", "", data.length ? "Link run…" : "No link runs yet"));
  sel.firstChild.value = "";
  data.forEach((r, i) => {
    const o = el("option", "", `${i === 0 ? "Last run: " : ""}${r.run} · ${r.rows} rows · ${r.by} · ${String(r.at).replace("T", " ").slice(0, 16)}`);
    o.value = r.run;
    sel.appendChild(o);
  });
  if (data.length) sel.value = data[0].run;
}

document.getElementById("unlinkPreviewBtn").addEventListener("click", async () => {
  const run = document.getElementById("unlinkRun").value;
  const code = document.getElementById("unlinkCode").value.trim();
  if (!!run === !!code) { showToast("Choose a link run OR type one location code", "error"); return; }
  const qs = run ? `run=${encodeURIComponent(run)}` : `code=${encodeURIComponent(code)}`;
  const { res, data } = await getJson(`/api/locations/unlink/preview?${qs}`);
  if (!res.ok) { showToast(data.detail || "Preview failed", "error"); return; }
  unlinkPlan = data;
  const box = document.getElementById("unlinkResult");
  box.textContent = "";
  box.appendChild(listBlock(`Will be unlinked (${data.pieces} pcs; quantities unchanged)`, data.will_unlink.map(rowLine), "border-red-500/40 text-red-200"));
  if (data.skipped.length) box.appendChild(listBlock("Skipped: changed since that run", data.skipped.map(r => rowLine(r) + ` · now: ${r.now}`), "border-slate-600 text-slate-300"));
  box.hidden = false;
  document.getElementById("unlinkApplyBtn").disabled = !data.can_apply;
});

document.getElementById("unlinkApplyBtn").addEventListener("click", async () => {
  if (!unlinkPlan) return;
  if (!confirm(`Unlink ${unlinkPlan.will_unlink.length} row(s)?\n\nQuantities do not change. Each unlink is recorded with your name.`)) return;
  const body = { plan_hash: unlinkPlan.plan_hash, run: unlinkPlan.run, code: unlinkPlan.code };
  const { res, data } = await post("/api/locations/unlink/apply", body);
  if (!res.ok) { showToast(data.detail || "Nothing was changed", "error"); return; }
  showToast(`Unlinked ${data.unlinked} row(s)${data.skipped ? `, ${data.skipped} skipped` : ""}`, "success");
  unlinkPlan = null;
  document.getElementById("unlinkApplyBtn").disabled = true;
  document.getElementById("unlinkResult").hidden = true;
  loadLinkRuns();
});

loadLinkRuns();

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
