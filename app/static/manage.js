let knownStylesSet = new Set();
let rowCounter = 0;

function initManagePage() {
  loadKnownStyles();
  resetSheetGrid(15);
  searchExistingLocations();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initManagePage);
} else {
  initManagePage();
}

async function loadKnownStyles() {
  try {
    const res = await fetch("/api/styles?limit=5000");
    if (!res.ok) return;
    const list = await res.json();
    knownStylesSet = new Set(list.map(s => s.style.toUpperCase()));
    const dl = document.getElementById("existingStylesDatalist");
    if (dl) {
      dl.innerHTML = list.map(s => `<option value="${escapeHtml(s.style)}">${s.total_quantity} pcs (${s.location_count} locs)</option>`).join("");
    }
    recalculateSheetSummary();
  } catch (err) {
    console.error("Error loading styles:", err);
  }
}

function addSheetRows(count = 1, prefillList = null) {
  const tbody = document.getElementById("sheetGridBody");
  if (!tbody) return;
  const defaultAction = (document.getElementById("globalSheetMode") && document.getElementById("globalSheetMode").value) || "IN";

  for (let i = 0; i < count; i++) {
    rowCounter++;
    const pf = (prefillList && prefillList[i]) || {};
    const act = pf.action || defaultAction;
    const tr = document.createElement("tr");
    tr.className = "sheet-row hover:bg-slate-800/40 transition";
    tr.innerHTML = `
      <td class="py-1.5 px-2 text-center font-mono text-slate-500 row-num">${rowCounter}</td>
      <td class="py-1.5 px-2">
        <select class="row-action w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-bold text-white" onchange="recalculateSheetSummary()">
          <option value="IN" ${act === 'IN' ? 'selected' : ''}>📥 IN (+Add)</option>
          <option value="OUT" ${act === 'OUT' ? 'selected' : ''}>📤 OUT (-Ship)</option>
          <option value="SET" ${act === 'SET' ? 'selected' : ''}>✏️ SET (=Exact)</option>
          <option value="DELETE" ${act === 'DELETE' ? 'selected' : ''}>🗑️ DELETE</option>
        </select>
      </td>
      <td class="py-1.5 px-2">
        <div class="flex items-center gap-1.5">
          <input type="text" list="existingStylesDatalist" value="${escapeHtml(pf.style || '')}" placeholder="e.g. A12501"
            oninput="recalculateSheetSummary()"
            class="row-style w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono font-bold text-white uppercase focus:border-amber-500 focus:outline-none" />
          <span class="row-style-badge hidden text-[9px] font-bold px-1.5 py-0.5 rounded whitespace-nowrap"></span>
        </div>
      </td>
      <td class="py-1.5 px-2">
        <input type="text" value="${escapeHtml(pf.color || '')}" placeholder="STANDARD"
          class="row-color w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white uppercase focus:border-amber-500 focus:outline-none" />
      </td>
      <td class="py-1.5 px-2">
        <input type="text" value="${escapeHtml(pf.size || '')}" placeholder="OS / 10"
          class="row-size w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white text-center font-mono focus:border-amber-500 focus:outline-none" />
      </td>
      <td class="py-1.5 px-2">
        <input type="text" value="${escapeHtml(pf.line || '')}" placeholder="1-13"
          class="row-line w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white text-center font-mono focus:border-amber-500 focus:outline-none" />
      </td>
      <td class="py-1.5 px-2">
        <input type="text" value="${escapeHtml(pf.section || '')}" placeholder="Sec"
          class="row-section w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white text-center font-mono focus:border-amber-500 focus:outline-none" />
      </td>
      <td class="py-1.5 px-2">
        <input type="text" value="${escapeHtml(pf.level || '')}" placeholder="Lvl"
          class="row-level w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white text-center font-mono focus:border-amber-500 focus:outline-none" />
      </td>
      <td class="py-1.5 px-2">
        <input type="text" value="${escapeHtml(pf.row_pos || '')}" placeholder="Row"
          class="row-pos w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white text-center font-mono focus:border-amber-500 focus:outline-none" />
      </td>
      <td class="py-1.5 px-2">
        <input type="text" value="${escapeHtml(pf.box_num || '')}" placeholder="Cartons"
          oninput="autoCalcRowPieces(this)"
          class="row-box w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-purple-300 text-center font-mono font-bold focus:border-amber-500 focus:outline-none" />
      </td>
      <td class="py-1.5 px-2">
        <input type="number" min="0" value="${pf.pcs_per_box != null ? pf.pcs_per_box : ''}" placeholder="Pcs/Ctn"
          oninput="autoCalcRowPieces(this)"
          class="row-pcs-box w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-300 text-center font-mono focus:border-amber-500 focus:outline-none" />
      </td>
      <td class="py-1.5 px-2">
        <input type="number" min="0" value="${pf.quantity != null ? pf.quantity : ''}" placeholder="0"
          oninput="recalculateSheetSummary()"
          class="row-qty w-full bg-slate-950 border border-emerald-500/40 rounded-lg px-2 py-1.5 text-xs text-emerald-400 text-center font-mono font-black focus:border-emerald-400 focus:outline-none" />
      </td>
      <td class="py-1.5 px-2 text-center">
        <button type="button" onclick="this.closest('tr').remove(); renumberSheetRows(); recalculateSheetSummary();" class="text-slate-500 hover:text-red-400 font-bold px-1">✕</button>
      </td>
    `;
    tbody.appendChild(tr);
  }
  renumberSheetRows();
  recalculateSheetSummary();
}

function renumberSheetRows() {
  const rows = document.querySelectorAll("#sheetGridBody .sheet-row");
  rows.forEach((tr, idx) => {
    const numCell = tr.querySelector(".row-num");
    if (numCell) numCell.textContent = idx + 1;
  });
  rowCounter = rows.length;
}

function resetSheetGrid(defaultRows = 15) {
  const tbody = document.getElementById("sheetGridBody");
  if (tbody) tbody.innerHTML = "";
  rowCounter = 0;
  const banner = document.getElementById("sheetResultBanner");
  if (banner) banner.classList.add("hidden");
  addSheetRows(defaultRows);
}

function applyGlobalModeToRows(mode) {
  document.querySelectorAll("#sheetGridBody .row-action").forEach(sel => {
    sel.value = mode;
  });
  recalculateSheetSummary();
}

function autoCalcRowPieces(inputEl) {
  const tr = inputEl.closest("tr");
  if (!tr) return;
  const boxVal = (tr.querySelector(".row-box").value || "").trim();
  const pcsVal = parseFloat(tr.querySelector(".row-pcs-box").value);
  const qtyInput = tr.querySelector(".row-qty");
  const cartonsNum = parseFloat(boxVal);
  if (!isNaN(cartonsNum) && cartonsNum > 0 && !isNaN(pcsVal) && pcsVal > 0) {
    qtyInput.value = Math.round(cartonsNum * pcsVal);
  } else if (!isNaN(pcsVal) && pcsVal > 0 && !boxVal) {
    qtyInput.value = Math.round(pcsVal);
  }
  recalculateSheetSummary();
}

function recalculateSheetSummary() {
  const rows = document.querySelectorAll("#sheetGridBody .sheet-row");
  let filled = 0;
  let totalCartons = 0;
  let totalPieces = 0;
  const stylesInSheet = new Set();
  let existingCount = 0;
  let newCount = 0;

  rows.forEach(tr => {
    const styleInput = tr.querySelector(".row-style");
    const badge = tr.querySelector(".row-style-badge");
    const style = (styleInput ? styleInput.value : "").trim().toUpperCase();
    const boxVal = (tr.querySelector(".row-box").value || "").trim();
    const qtyVal = parseInt(tr.querySelector(".row-qty").value, 10) || 0;

    if (!style) {
      if (badge) badge.classList.add("hidden");
      return;
    }

    filled++;
    stylesInSheet.add(style);
    if (boxVal && !isNaN(parseInt(boxVal, 10))) {
      totalCartons += parseInt(boxVal, 10);
    } else {
      totalCartons += 1;
    }
    totalPieces += qtyVal;

    if (badge) {
      if (knownStylesSet.has(style)) {
        badge.textContent = "OLD";
        badge.className = "row-style-badge text-[9px] font-bold px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30";
      } else {
        badge.textContent = "NEW";
        badge.className = "row-style-badge text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30";
      }
    }
  });

  stylesInSheet.forEach(st => {
    if (knownStylesSet.has(st)) existingCount++;
    else newCount++;
  });

  document.getElementById("sumRowsFilled").textContent = filled.toLocaleString();
  document.getElementById("sumTotalStyles").textContent = stylesInSheet.size.toLocaleString();
  document.getElementById("sumOldNewStyles").textContent = `(${existingCount} existing, ${newCount} new)`;
  document.getElementById("sumTotalCartons").textContent = totalCartons.toLocaleString();
  document.getElementById("sumTotalPieces").textContent = totalPieces.toLocaleString();
}

function parseCsvLine(line) {
  const res = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
    } else if (ch === ',' && !inQuotes) {
      res.push(cur.trim());
      cur = "";
    } else {
      cur += ch;
    }
  }
  res.push(cur.trim());
  return res;
}

function loadCsvIntoSheetGrid(e) {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  const defaultAction = document.getElementById("globalSheetMode").value || "IN";

  const reader = new FileReader();
  reader.onload = function(evt) {
    const text = (evt.target.result || "").trim();
    const lines = text.split(/\r?\n/).filter(l => l.trim().length > 0);
    if (lines.length < 2) {
      showToast("CSV file has no data rows", "error");
      return;
    }
    const headers = parseCsvLine(lines[0]).map(h => h.toUpperCase().trim());
    const idxOf = (...names) => {
      for (const n of names) {
        const i = headers.indexOf(n);
        if (i !== -1) return i;
      }
      return -1;
    };

    const iSku = idxOf("SKU", "STYLE", "STYLE CODE");
    const iColor = idxOf("COLOR", "COLOUR");
    const iSize = idxOf("SIZE");
    const iLine = idxOf("LINE");
    const iSec = idxOf("SECTION", "SEC");
    const iLvl = idxOf("LEVEL", "LVL");
    const iRow = idxOf("ROW");
    const iBox = idxOf("BOX #", "BOX", "CARTONS", "TOTAL CARTONS");
    const iPcs = idxOf("PCS/BOX", "PCS/CARTON", "PCS_PER_BOX");
    const iQty = idxOf("QTY", "QUANTITY", "TOTAL PIECES", "PIECES");

    if (iSku === -1) {
      showToast("CSV must have a SKU or STYLE column header", "error");
      return;
    }

    const parsed = [];
    for (let r = 1; r < lines.length; r++) {
      const cols = parseCsvLine(lines[r]);
      const style = (cols[iSku] || "").trim();
      if (!style) continue;
      const boxVal = iBox !== -1 ? (cols[iBox] || "").trim() : "";
      const pcsVal = iPcs !== -1 && cols[iPcs] ? parseInt(cols[iPcs], 10) : null;
      let qtyVal = iQty !== -1 && cols[iQty] ? parseInt(cols[iQty], 10) : 0;
      if (!qtyVal && pcsVal && boxVal && !isNaN(parseInt(boxVal, 10))) {
        qtyVal = pcsVal * parseInt(boxVal, 10);
      } else if (!qtyVal && pcsVal) {
        qtyVal = pcsVal;
      }
      parsed.push({
        action: defaultAction,
        style: style.toUpperCase(),
        color: iColor !== -1 ? (cols[iColor] || "STANDARD").toUpperCase() : "STANDARD",
        size: iSize !== -1 ? (cols[iSize] || "OS") : "OS",
        line: iLine !== -1 ? cols[iLine] : "",
        section: iSec !== -1 ? cols[iSec] : "",
        level: iLvl !== -1 ? cols[iLvl] : "",
        row_pos: iRow !== -1 ? cols[iRow] : "",
        box_num: boxVal,
        pcs_per_box: pcsVal,
        quantity: qtyVal || 0,
      });
    }

    const tbody = document.getElementById("sheetGridBody");
    if (tbody) tbody.innerHTML = "";
    rowCounter = 0;
    addSheetRows(parsed.length, parsed);
    showToast(`Loaded ${parsed.length.toLocaleString()} rows from "${file.name}" into sheet!`, "success");
    e.target.value = "";
  };
  reader.readAsText(file);
}

async function submitManagerSheet() {
  const trs = document.querySelectorAll("#sheetGridBody .sheet-row");
  const rowsPayload = [];

  trs.forEach(tr => {
    const style = (tr.querySelector(".row-style").value || "").trim().toUpperCase();
    if (!style) return;
    const action = tr.querySelector(".row-action").value;
    const color = (tr.querySelector(".row-color").value || "STANDARD").trim().toUpperCase();
    const size = (tr.querySelector(".row-size").value || "OS").trim().toUpperCase();
    const line = (tr.querySelector(".row-line").value || "").trim() || null;
    const section = (tr.querySelector(".row-section").value || "").trim() || null;
    const level = (tr.querySelector(".row-level").value || "").trim() || null;
    const row_pos = (tr.querySelector(".row-pos").value || "").trim() || null;
    const box_num = (tr.querySelector(".row-box").value || "").trim() || null;
    const pcsRaw = tr.querySelector(".row-pcs-box").value;
    const pcs_per_box = pcsRaw ? parseInt(pcsRaw, 10) : null;
    const quantity = parseInt(tr.querySelector(".row-qty").value, 10) || 0;

    rowsPayload.push({
      action, style, color, size, line, section, level, row_pos, box_num, pcs_per_box, quantity
    });
  });

  if (rowsPayload.length === 0) {
    showToast("Please enter at least 1 row with a Style code", "error");
    return;
  }

  const btn = document.getElementById("submitSheetBtn");
  const banner = document.getElementById("sheetResultBanner");
  const sheet_note = (document.getElementById("sheetNoteInput").value || "Manager Sheet").trim();
  const staff_name = (document.getElementById("sheetStaffInput").value || "Nandu").trim();

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = "<span>⏳</span><span>Saving Sheet to PostgreSQL...</span>";
  }

  try {
    const res = await fetch("/api/sheet-submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows: rowsPayload, sheet_note, staff_name })
    });
    const data = await res.json();

    if (!res.ok) {
      if (banner) {
        banner.className = "rounded-xl p-4 border bg-red-500/10 border-red-500/40 text-red-300 text-xs space-y-1";
        banner.innerHTML = `<div class="font-black text-red-400">❌ Sheet Not Saved (Safe Rollback):</div><div>${escapeHtml(data.detail || "Error submitting sheet")}</div>`;
        banner.classList.remove("hidden");
      }
      showToast(data.detail || "Failed to submit sheet", "error");
      return;
    }

    if (banner) {
      banner.className = "rounded-xl p-4 border bg-emerald-500/10 border-emerald-500/40 text-emerald-200 text-xs space-y-1.5";
      banner.innerHTML = `
        <div class="text-sm font-black text-emerald-400">✅ Sheet Saved to PostgreSQL (${data.processed_rows.toLocaleString()} rows processed)</div>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 font-mono">
          <div>• Styles in Sheet: <strong>${data.existing_styles_count + data.new_styles_count}</strong> (${data.existing_styles_count} old, ${data.new_styles_count} new)</div>
          <div>• New Locations Created: <strong>${data.inserted_count}</strong></div>
          <div>• Existing Locations Updated: <strong>${data.updated_count}</strong></div>
          <div>• Cartons: <strong>${data.total_cartons}</strong> | IN: <strong>+${data.total_pieces_in} pcs</strong> | OUT: <strong>-${data.total_pieces_out} pcs</strong></div>
        </div>
      `;
      banner.classList.remove("hidden");
    }

    showToast(`Saved ${data.processed_rows} sheet rows to PostgreSQL!`, "success");
    await loadKnownStyles();
    if (data.touched_styles && data.touched_styles.length > 0) {
      document.getElementById("locSearchStyle").value = data.touched_styles[0];
      searchExistingLocations();
    }
  } catch (err) {
    showToast("Network error while saving sheet", "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = "<span>🚀</span><span>Save Entire Sheet to PostgreSQL</span>";
    }
  }
}

async function searchExistingLocations(e) {
  if (e) e.preventDefault();
  const style = (document.getElementById("locSearchStyle").value || "").trim();
  const line = (document.getElementById("locSearchLine").value || "").trim();
  const section = (document.getElementById("locSearchSection").value || "").trim();
  const level = (document.getElementById("locSearchLevel").value || "").trim();
  const color = (document.getElementById("locSearchColor").value || "").trim();

  const params = new URLSearchParams();
  if (style) params.set("style", style);
  if (line) params.set("line", line);
  if (section) params.set("section", section);
  if (level) params.set("level", level);
  if (color) params.set("color", color);
  params.set("limit", "150");

  const tbody = document.getElementById("existingLocationsBody");
  if (tbody) {
    tbody.innerHTML = '<tr><td colspan="12" class="text-center py-8 text-slate-400">Loading locations from PostgreSQL...</td></tr>';
  }

  try {
    const res = await fetch(`/api/location-search?${params.toString()}`);
    const items = await res.json();
    if (!items || items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="12" class="text-center py-8 text-amber-400">No matching location records found.</td></tr>';
      return;
    }

    tbody.innerHTML = items.map(item => `
      <tr data-item-id="${item.id}" class="hover:bg-slate-800/40 transition">
        <td class="py-1.5 px-2 text-center">
          <input type="checkbox" class="existing-row-check" value="${item.id}" />
        </td>
        <td class="py-1.5 px-2">
          <input type="text" value="${escapeHtml(item.style)}" class="edit-style w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono font-bold text-amber-400 uppercase" />
        </td>
        <td class="py-1.5 px-2">
          <input type="text" value="${escapeHtml(item.color || '')}" class="edit-color w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-white uppercase" />
        </td>
        <td class="py-1.5 px-2">
          <input type="text" value="${escapeHtml(item.size || '')}" class="edit-size w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-white text-center font-mono" />
        </td>
        <td class="py-1.5 px-2">
          <input type="text" value="${escapeHtml(item.line || '')}" class="edit-line w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-white text-center font-mono" />
        </td>
        <td class="py-1.5 px-2">
          <input type="text" value="${escapeHtml(item.section || '')}" class="edit-section w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-white text-center font-mono" />
        </td>
        <td class="py-1.5 px-2">
          <input type="text" value="${escapeHtml(item.level || '')}" class="edit-level w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-white text-center font-mono" />
        </td>
        <td class="py-1.5 px-2">
          <input type="text" value="${escapeHtml(item.row_pos || '')}" class="edit-row w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-white text-center font-mono" />
        </td>
        <td class="py-1.5 px-2">
          <input type="text" value="${escapeHtml(item.box_num || '')}" class="edit-box w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-purple-300 text-center font-mono" />
        </td>
        <td class="py-1.5 px-2">
          <input type="number" value="${item.pcs_per_box != null ? item.pcs_per_box : ''}" class="edit-pcs w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-300 text-center font-mono" />
        </td>
        <td class="py-1.5 px-2">
          <input type="number" value="${item.quantity}" class="edit-qty w-full bg-slate-950 border border-emerald-500/40 rounded px-2 py-1 text-xs text-emerald-400 text-center font-mono font-black" />
        </td>
        <td class="py-1.5 px-2 text-right whitespace-nowrap space-x-1">
          <button type="button" onclick="saveExistingRow(${item.id}, this)" class="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold px-2.5 py-1 rounded text-[11px] transition">
            Save
          </button>
          <button type="button" onclick="deleteSingleExistingRow(${item.id})" class="bg-red-500/15 hover:bg-red-500/30 text-red-300 border border-red-500/30 font-bold px-2 py-1 rounded text-[11px] transition">
            Del
          </button>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="12" class="text-center py-8 text-red-400">Error loading locations.</td></tr>';
  }
}

async function saveExistingRow(itemId, btnEl) {
  const tr = btnEl.closest("tr");
  if (!tr) return;
  const payload = {
    style: tr.querySelector(".edit-style").value.trim().toUpperCase(),
    color: tr.querySelector(".edit-color").value.trim().toUpperCase() || "STANDARD",
    size: tr.querySelector(".edit-size").value.trim().toUpperCase() || "OS",
    line: tr.querySelector(".edit-line").value.trim() || null,
    section: tr.querySelector(".edit-section").value.trim() || null,
    level: tr.querySelector(".edit-level").value.trim() || null,
    row_pos: tr.querySelector(".edit-row").value.trim() || null,
    box_num: tr.querySelector(".edit-box").value.trim() || null,
    pcs_per_box: tr.querySelector(".edit-pcs").value ? parseInt(tr.querySelector(".edit-pcs").value, 10) : null,
    quantity: parseInt(tr.querySelector(".edit-qty").value, 10) || 0,
    staff_name: (document.getElementById("sheetStaffInput").value || "Nandu").trim()
  };

  try {
    const res = await fetch(`/api/items/${itemId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "Update failed", "error");
      return;
    }
    showToast(`Saved ${data.style} @ ${data.location} (${data.quantity} pcs)`, "success");
    loadKnownStyles();
  } catch (err) {
    showToast("Error saving row", "error");
  }
}

async function deleteSingleExistingRow(itemId) {
  if (!confirm("Delete this location record from PostgreSQL?")) return;
  try {
    const res = await fetch(`/api/items/${itemId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed");
    showToast("Location deleted", "success");
    searchExistingLocations();
  } catch (err) {
    showToast("Delete failed", "error");
  }
}

function toggleSelectAllExisting(checked) {
  document.querySelectorAll(".existing-row-check").forEach(cb => {
    cb.checked = checked;
  });
}

async function deleteSelectedExistingRows() {
  const checked = [...document.querySelectorAll(".existing-row-check:checked")].map(cb => parseInt(cb.value, 10));
  if (checked.length === 0) {
    showToast("Check at least one row to delete", "error");
    return;
  }
  if (!confirm(`Delete ${checked.length} selected location row(s) from PostgreSQL?`)) return;

  try {
    const res = await fetch("/api/items/bulk-delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_ids: checked, staff_name: "Nandu" })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "Bulk delete failed", "error");
      return;
    }
    showToast(`Deleted ${data.deleted_count} location rows`, "success");
    searchExistingLocations();
  } catch (err) {
    showToast("Error deleting selected rows", "error");
  }
}

async function handleQuickRenameStyle(e) {
  e.preventDefault();
  const old_style = document.getElementById("quickOldStyle").value.trim().toUpperCase();
  const new_style = document.getElementById("quickNewStyle").value.trim().toUpperCase();
  if (!old_style || !new_style) return;

  try {
    const res = await fetch("/api/styles/rename", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_style, new_style, staff_name: "Nandu" })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "Style rename failed", "error");
      return;
    }
    showToast(`Renamed ${data.updated_records} rows: ${old_style} → ${new_style}`, "success");
    document.getElementById("quickOldStyle").value = "";
    document.getElementById("quickNewStyle").value = "";
    document.getElementById("locSearchStyle").value = new_style;
    loadKnownStyles();
    searchExistingLocations();
  } catch (err) {
    showToast("Error renaming style", "error");
  }
}

function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  const bg = type === "error" ? "bg-red-600 text-white" : "bg-emerald-600 text-white";
  toast.className = `${bg} px-4 py-2.5 rounded-xl shadow-2xl text-xs font-semibold flex items-center space-x-2 transition transform duration-200`;
  toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 200);
  }, 3500);
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
