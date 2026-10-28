// Multi-Style State: Array of active style codes
let selectedStyles = ["A12501"];
let allStylesList = [];
let batchData = null;
let activeItemForAdjust = null;
let searchDebounce = null;

// Self-invoking immediate initialization
function initApp() {
  console.log("Initializing Warehouse OS Frontend...");
  loadStats();
  loadStylesList();
  renderSelectedStylesChips();
  loadBatchStylesDetails();

  const searchInput = document.getElementById("styleSearchInput");
  const dropdown = document.getElementById("styleDropdown");

  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      const query = e.target.value.trim().toUpperCase();
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => {
        renderStyleDropdown(query);
      }, 150);
    });

    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        handleAddInputStyles();
      }
    });
  }

  const addBtn = document.getElementById("addStyleBtn");
  if (addBtn) {
    addBtn.addEventListener("click", () => {
      handleAddInputStyles();
    });
  }

  document.addEventListener("click", (e) => {
    if (searchInput && dropdown && !searchInput.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.classList.add("hidden");
    }
  });

  const fStyle = document.getElementById("filterStyleSelect");
  if (fStyle) fStyle.addEventListener("change", renderFilteredRows);
  const fColor = document.getElementById("filterColorSelect");
  if (fColor) fColor.addEventListener("change", renderFilteredRows);
  const fSize = document.getElementById("filterSizeSelect");
  if (fSize) fSize.addEventListener("change", renderFilteredRows);
}

// Ensure execution whether ready or loading
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}

// Handle adding styles from search input
function handleAddInputStyles() {
  const input = document.getElementById("styleSearchInput");
  if (!input) return;
  const val = input.value.trim();
  if (!val) return;

  const parts = val.split(/[,\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean);
  let added = false;
  parts.forEach(st => {
    if (!selectedStyles.includes(st)) {
      selectedStyles.push(st);
      added = true;
    }
  });

  input.value = "";
  const dropdown = document.getElementById("styleDropdown");
  if (dropdown) dropdown.classList.add("hidden");

  if (added) {
    renderSelectedStylesChips();
    loadBatchStylesDetails();
  }
}

function renderSelectedStylesChips() {
  const container = document.getElementById("selectedStylesContainer");
  if (!container) return;
  if (selectedStyles.length === 0) {
    container.innerHTML = '<span class="text-xs text-slate-500 italic">No styles selected. Enter one above.</span>';
    return;
  }

  container.innerHTML = selectedStyles.map(st => `
    <span class="style-tag-badge inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-mono font-bold shadow-sm">
      <span>${escapeHtml(st)}</span>
      <button onclick="removeSelectedStyle('${escapeHtml(st)}')" class="hover:text-red-400 p-0.5 rounded transition">
        ✕
      </button>
    </span>
  `).join("");
}

function removeSelectedStyle(styleCode) {
  selectedStyles = selectedStyles.filter(s => s !== styleCode);
  renderSelectedStylesChips();
  if (selectedStyles.length > 0) {
    loadBatchStylesDetails();
  } else {
    batchData = null;
    const title = document.getElementById("currentStyleTitle");
    if (title) title.textContent = "None Selected";
    const badge = document.getElementById("styleCountBadge");
    if (badge) badge.textContent = "0 Styles Selected";
    const qty = document.getElementById("currentStyleTotalQty");
    if (qty) qty.textContent = "0 units";
    const sub = document.getElementById("styleSummarySubtitle");
    if (sub) sub.textContent = "Add styles above to view inventory.";
    const tbody = document.getElementById("styleLocationTableBody");
    if (tbody) tbody.innerHTML = `
      <tr><td colspan="8" class="text-center py-10 text-slate-500">No styles currently selected. Enter style codes above.</td></tr>
    `;
  }
}

function clearAllStyles() {
  selectedStyles = [];
  removeSelectedStyle("");
}

function addStyleToSelection(styleCode) {
  const upper = styleCode.trim().toUpperCase();
  if (!selectedStyles.includes(upper)) {
    selectedStyles.push(upper);
    renderSelectedStylesChips();
    loadBatchStylesDetails();
  }
}

async function loadStats() {
  try {
    const res = await fetch("/api/stats");
    if (!res.ok) return;
    const stats = await res.json();
    const stEl = document.getElementById("statTotalStyles");
    if (stEl) stEl.textContent = stats.total_styles.toLocaleString();
    const unEl = document.getElementById("statTotalUnits");
    if (unEl) unEl.textContent = stats.total_units.toLocaleString();
    const recEl = document.getElementById("statTotalRecords");
    if (recEl) recEl.textContent = stats.total_records.toLocaleString();
    const locEl = document.getElementById("statTotalLocations");
    if (locEl) locEl.textContent = stats.total_locations.toLocaleString();
  } catch (err) {
    console.error("Stats load error:", err);
  }
}

async function loadStylesList() {
  try {
    const res = await fetch("/api/styles?limit=250");
    if (!res.ok) return;
    allStylesList = await res.json();

    const chipsContainer = document.getElementById("quickStyleChips");
    if (chipsContainer) {
      chipsContainer.innerHTML = allStylesList.slice(0, 10).map(s => `
        <button 
          onclick="addStyleToSelection('${s.style}')" 
          class="style-chip px-2.5 py-1 rounded-lg text-xs font-mono font-semibold ${selectedStyles.includes(s.style) ? 'active' : 'text-slate-300'}">
          + ${s.style}
        </button>
      `).join("");
    }
  } catch (err) {
    console.error("Styles list error:", err);
  }
}

function renderStyleDropdown(query) {
  const dropdown = document.getElementById("styleDropdown");
  if (!dropdown) return;
  if (!query) {
    dropdown.classList.add("hidden");
    return;
  }

  const matches = allStylesList.filter(s => s.style.toUpperCase().includes(query)).slice(0, 15);
  if (matches.length === 0) {
    dropdown.innerHTML = `<div class="p-3 text-xs text-slate-500">No styles matching "${escapeHtml(query)}"</div>`;
    dropdown.classList.remove("hidden");
    return;
  }

  dropdown.innerHTML = matches.map(s => {
    const isSelected = selectedStyles.includes(s.style);
    return `
      <div 
        onclick="addStyleToSelection('${s.style}'); document.getElementById('styleDropdown').classList.add('hidden'); document.getElementById('styleSearchInput').value='';" 
        class="p-2.5 hover:bg-slate-800 cursor-pointer flex justify-between items-center transition ${isSelected ? 'bg-slate-800/40' : ''}">
        <span class="font-mono font-bold text-amber-400 text-sm flex items-center gap-2">
          ${s.style} ${isSelected ? '<span class="text-[10px] text-emerald-400 font-sans">(added)</span>' : ''}
        </span>
        <span class="text-xs text-slate-400 font-mono">${s.total_quantity.toLocaleString()} units • ${s.location_count} locs</span>
      </div>
    `;
  }).join("");

  dropdown.classList.remove("hidden");
}

async function loadBatchStylesDetails() {
  if (selectedStyles.length === 0) return;

  const tbody = document.getElementById("styleLocationTableBody");
  if (tbody) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="text-center py-12 text-slate-400">
          Loading locations for styles: ${selectedStyles.join(", ")}...
        </td>
      </tr>
    `;
  }

  try {
    const stylesParam = encodeURIComponent(selectedStyles.join(","));
    const res = await fetch(`/api/styles-batch?styles=${stylesParam}`);
    if (!res.ok) {
      if (tbody) {
        tbody.innerHTML = `
          <tr>
            <td colspan="8" class="text-center py-10 text-amber-400">
              None of the selected styles have records in PostgreSQL.
            </td>
          </tr>
        `;
      }
      return;
    }

    batchData = await res.json();

    const styleCount = batchData.found_styles.length;
    const badge = document.getElementById("styleCountBadge");
    if (badge) badge.textContent = `${styleCount} Style${styleCount === 1 ? '' : 's'} Selected`;
    const title = document.getElementById("currentStyleTitle");
    if (title) title.textContent = batchData.found_styles.join("  •  ");
    const qty = document.getElementById("currentStyleTotalQty");
    if (qty) qty.textContent = `${batchData.total_quantity.toLocaleString()} units`;

    const allLocations = new Set(batchData.items.map(i => i.location));
    const allColors = [...new Set(batchData.items.map(i => i.color).filter(Boolean))].sort();
    const allSizes = [...new Set(batchData.items.map(i => i.size).filter(Boolean))].sort();

    const subtitle = document.getElementById("styleSummarySubtitle");
    if (subtitle) {
      subtitle.innerHTML = `
        <span>📍 <strong>${allLocations.size}</strong> Total Locations</span>
        <span>🎨 <strong>${allColors.length}</strong> Colors</span>
        <span>📏 <strong>${allSizes.length}</strong> Sizes</span>
        <span>📦 <strong>${batchData.total_records}</strong> Rows</span>
      `;
    }

    const styleSelect = document.getElementById("filterStyleSelect");
    if (styleSelect) {
      styleSelect.innerHTML = '<option value="ALL">All Styles</option>' +
        batchData.found_styles.map(s => `<option value="${s}">Style ${s}</option>`).join("");
    }

    const colorSelect = document.getElementById("filterColorSelect");
    if (colorSelect) {
      colorSelect.innerHTML = '<option value="ALL">All Colors</option>' + 
        allColors.map(c => `<option value="${c}">${c}</option>`).join("");
    }

    const sizeSelect = document.getElementById("filterSizeSelect");
    if (sizeSelect) {
      sizeSelect.innerHTML = '<option value="ALL">All Sizes</option>' + 
        allSizes.map(s => `<option value="${s}">Size ${s}</option>`).join("");
    }

    renderFilteredRows();
  } catch (err) {
    console.error("Batch styles error:", err);
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" class="text-center py-10 text-red-400 font-bold">
            Failed to connect to backend server. Make sure server is running on port 8000.
          </td>
        </tr>
      `;
    }
  }
}

function getActiveFilteredItems() {
  if (!batchData || !batchData.items) return [];
  const sStyle = document.getElementById("filterStyleSelect");
  const sColor = document.getElementById("filterColorSelect");
  const sSize = document.getElementById("filterSizeSelect");

  const selectedStyle = sStyle ? sStyle.value : "ALL";
  const selectedColor = sColor ? sColor.value : "ALL";
  const selectedSize = sSize ? sSize.value : "ALL";

  let items = batchData.items;
  if (selectedStyle !== "ALL") items = items.filter(i => i.style.toUpperCase() === selectedStyle.toUpperCase());
  if (selectedColor !== "ALL") items = items.filter(i => i.color === selectedColor);
  if (selectedSize !== "ALL") items = items.filter(i => i.size === selectedSize);
  return items;
}

function renderFilteredRows() {
  const items = getActiveFilteredItems();
  const countEl = document.getElementById("filteredRowCount");
  if (countEl) {
    countEl.textContent = `Showing ${items.length} of ${batchData ? batchData.items.length : 0} locations`;
  }

  const tbody = document.getElementById("styleLocationTableBody");
  if (!tbody) return;

  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-8 text-slate-500">No locations matching active filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(item => {
    const isZero = item.quantity === 0;
    const qtyBadge = isZero 
      ? 'bg-red-500/10 text-red-400 border-red-500/30' 
      : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';

    return `
      <tr class="hover:bg-slate-800/40 transition group">
        <td class="py-3.5 px-4">
          <span class="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-mono font-black bg-amber-500/10 text-amber-400 border border-amber-500/30">
            ${escapeHtml(item.style)}
          </span>
        </td>

        <td class="py-3.5 px-4">
          <span class="location-tag inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-bold text-amber-300 shadow-sm">
            <span>📍</span>
            ${escapeHtml(item.location || "Unassigned")}
          </span>
          <div class="text-[10px] text-slate-500 font-mono mt-1">
            Line: ${escapeHtml(item.line || "-")}, Sec: ${escapeHtml(item.section || "-")}, Lvl: ${escapeHtml(item.level || "-")}, Row: ${escapeHtml(item.row_pos || "-")}
          </div>
        </td>

        <td class="py-3.5 px-4 font-mono text-xs">
          <span class="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 font-semibold">
            ${escapeHtml(item.color || "STANDARD")}
          </span>
        </td>

        <td class="py-3.5 px-4 text-center">
          <span class="px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 font-mono font-bold text-xs">
            ${escapeHtml(item.size || "OS")}
          </span>
        </td>

        <td class="py-3.5 px-4 text-center font-mono text-xs text-slate-400">
          <div>${item.pcs_per_box ? `${item.pcs_per_box} pcs/box` : "-"}</div>
          <div class="text-[10px] text-slate-500">${item.box_num ? `Box #${item.box_num}` : ""}</div>
        </td>

        <td class="py-3.5 px-4 text-center">
          <span class="inline-block px-3.5 py-1 rounded-full text-sm font-black border font-mono ${qtyBadge}">
            ${item.quantity.toLocaleString()} units
          </span>
        </td>

        <td class="py-3.5 px-4 text-center">
          <div class="inline-flex items-center space-x-1.5 bg-slate-950 border border-slate-800 rounded-xl p-1 shadow-md">
            <button 
              onclick="realtimeQuickAdjust(${item.id}, -1)" 
              ${item.quantity <= 0 ? "disabled" : ""}
              title="Quick deduct 1 unit" 
              class="w-8 h-8 rounded-lg bg-slate-800 hover:bg-red-500/20 text-slate-300 hover:text-red-400 font-black disabled:opacity-20 transition flex items-center justify-center">
              -
            </button>
            <button 
              onclick='openAdjustModal(${JSON.stringify(item)})' 
              title="Add or Remove custom quantity" 
              class="px-2.5 py-1 text-xs font-mono font-bold text-slate-300 hover:text-amber-400 transition">
              Adjust
            </button>
            <button 
              onclick="realtimeQuickAdjust(${item.id}, 1)" 
              title="Quick add 1 unit" 
              class="w-8 h-8 rounded-lg bg-slate-800 hover:bg-emerald-500/20 text-slate-300 hover:text-emerald-400 font-black transition flex items-center justify-center">
              +
            </button>
            <button 
              onclick='openExactQtyModal(${JSON.stringify(item)})' 
              title="Set exact stock balance" 
              class="p-1.5 text-slate-500 hover:text-white rounded-lg transition text-xs">
              ✏️
            </button>
          </div>
        </td>

        <td class="py-3.5 px-4 text-right">
          <button onclick="deleteLocationRecord(${item.id})" class="p-1.5 text-slate-600 hover:text-red-400 rounded-lg transition text-xs" title="Remove Location Record">
            🗑️
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

function triggerPrintPickSheet() {
  if (!batchData) {
    showToast("Please select styles first", "error");
    return;
  }

  const items = getActiveFilteredItems();
  if (items.length === 0) {
    showToast("No locations found to print", "error");
    return;
  }

  document.getElementById("printStyleCode").textContent = batchData.found_styles.join(", ");
  const now = new Date();
  document.getElementById("printTimestamp").textContent = now.toLocaleDateString() + " " + now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  document.getElementById("printTotalLocations").textContent = `${items.length} locations`;
  
  const totalUnits = items.reduce((sum, i) => sum + i.quantity, 0);
  document.getElementById("printTotalUnits").textContent = `${totalUnits.toLocaleString()} units`;

  const sortedItems = [...items].sort((a, b) => {
    const lineA = parseInt(a.line, 10) || 0;
    const lineB = parseInt(b.line, 10) || 0;
    if (lineA !== lineB) return lineA - lineB;

    const secA = parseInt(a.section, 10) || 0;
    const secB = parseInt(b.section, 10) || 0;
    if (secA !== secB) return secA - secB;

    const lvlA = parseInt(a.level, 10) || 0;
    const lvlB = parseInt(b.level, 10) || 0;
    if (lvlA !== lvlB) return lvlA - lvlB;

    return a.style.localeCompare(b.style);
  });

  const printTbody = document.getElementById("printTableBody");
  printTbody.innerHTML = sortedItems.map((item, idx) => `
    <tr class="${idx % 2 === 1 ? 'bg-gray-50' : 'bg-white'}">
      <td class="p-2 border-r border-black text-center font-bold text-base">
        [ &nbsp; ]
      </td>
      <td class="p-2 border-r border-black font-black font-mono text-sm">
        ${escapeHtml(item.style)}
      </td>
      <td class="p-2 border-r border-black">
        <div class="font-bold text-sm font-mono">${escapeHtml(item.location || 'Unassigned')}</div>
        <div class="text-[10px] text-gray-600">Line: ${escapeHtml(item.line || '-')} | Sec: ${escapeHtml(item.section || '-')} | Lvl: ${escapeHtml(item.level || '-')} | Row: ${escapeHtml(item.row_pos || '-')}</div>
      </td>
      <td class="p-2 border-r border-black font-semibold">
        ${escapeHtml(item.color || 'STANDARD')}
      </td>
      <td class="p-2 border-r border-black text-center font-bold font-mono text-sm">
        ${escapeHtml(item.size || 'OS')}
      </td>
      <td class="p-2 border-r border-black text-center font-mono">
        ${item.box_num ? `Box #${escapeHtml(item.box_num)}` : '-'}
        ${item.pcs_per_box ? ` (${item.pcs_per_box} pcs/box)` : ''}
      </td>
      <td class="p-2 border-r border-black text-center font-bold font-mono text-sm">
        ${item.quantity.toLocaleString()}
      </td>
      <td class="p-2 border-black text-center text-gray-400 font-mono">
        [ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ]
      </td>
    </tr>
  `).join("");

  window.print();
}

async function realtimeQuickAdjust(itemId, delta) {
  try {
    const res = await fetch(`/api/items/${itemId}/adjust`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        change_amount: delta,
        reason: delta > 0 ? "Quick Add (+1)" : "Quick Deduct (-1)",
        staff_name: "Manager",
        movement_type: delta > 0 ? "QUICK_ADD" : "QUICK_SUB"
      })
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail || "Error updating stock", "error");
      return;
    }

    const updated = await res.json();
    showToast(`${updated.style} (${updated.location}): Stock is now ${updated.quantity}`, "success");
    
    loadBatchStylesDetails();
    loadStats();
  } catch (err) {
    showToast("Network error updating stock", "error");
  }
}

function openAdjustModal(item) {
  activeItemForAdjust = item;
  document.getElementById("adjustModalTitle").textContent = `Adjust Stock - ${item.style}`;
  document.getElementById("adjustModalSubtitle").textContent = `Size ${item.size} • ${item.color}`;
  document.getElementById("adjustModalLoc").textContent = item.location;
  document.getElementById("adjustModalCurrentQty").textContent = `${item.quantity} units`;
  document.getElementById("adjustInputAmount").value = "";
  openModal("adjustModal");
}

function setAdjustInput(val) {
  document.getElementById("adjustInputAmount").value = val;
}

async function submitStockAdjustment() {
  if (!activeItemForAdjust) return;
  const val = parseInt(document.getElementById("adjustInputAmount").value, 10);
  if (isNaN(val) || val === 0) {
    showToast("Please enter a valid amount (e.g. +10 or -5)", "error");
    return;
  }

  const reason = document.getElementById("adjustReasonSelect").value;

  try {
    const res = await fetch(`/api/items/${activeItemForAdjust.id}/adjust`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        change_amount: val,
        reason: reason,
        staff_name: "Manager",
        movement_type: val > 0 ? "STOCK_IN" : "STOCK_OUT"
      })
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail || "Adjustment failed", "error");
      return;
    }

    const updated = await res.json();
    closeModal("adjustModal");
    showToast(`Updated: ${updated.style} at ${updated.location} is now ${updated.quantity}`, "success");

    loadBatchStylesDetails();
    loadStats();
  } catch (err) {
    showToast("Adjustment error", "error");
  }
}

function openExactQtyModal(item) {
  activeItemForAdjust = item;
  document.getElementById("exactQtyInput").value = item.quantity;
  openModal("setQtyModal");
}

async function submitExactQuantity() {
  if (!activeItemForAdjust) return;
  const newQty = parseInt(document.getElementById("exactQtyInput").value, 10);
  if (isNaN(newQty) || newQty < 0) {
    showToast("Quantity must be 0 or greater", "error");
    return;
  }

  try {
    const res = await fetch(`/api/items/${activeItemForAdjust.id}/set-quantity`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        new_quantity: newQty,
        reason: "Manager Count Correction",
        staff_name: "Manager"
      })
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail || "Failed to update", "error");
      return;
    }

    closeModal("setQtyModal");
    showToast(`Stock updated to ${newQty}`, "success");
    loadBatchStylesDetails();
    loadStats();
  } catch (err) {
    showToast("Error updating stock", "error");
  }
}

function openAddLocationModal() {
  document.getElementById("newLocStyle").value = selectedStyles[0] || "";
  openModal("addLocationModal");
}

async function handleAddLocationSubmit(e) {
  e.preventDefault();
  const style = document.getElementById("newLocStyle").value.trim().toUpperCase();
  const color = document.getElementById("newLocColor").value.trim().toUpperCase() || "STANDARD";
  const size = document.getElementById("newLocSize").value.trim();
  const line = document.getElementById("newLocLine").value.trim();
  const section = document.getElementById("newLocSection").value.trim();
  const level = document.getElementById("newLocLevel").value.trim();
  const box = document.getElementById("newLocBox").value.trim();
  const qty = parseInt(document.getElementById("newLocQuantity").value, 10) || 0;
  const pcs = parseInt(document.getElementById("newLocPcsBox").value, 10) || null;

  const locParts = [];
  if (line) locParts.push(`Line ${line}`);
  if (section) locParts.push(`Sec ${section}`);
  if (level) locParts.push(`Lvl ${level}`);
  if (box) locParts.push(`Box ${box}`);
  const location = locParts.length > 0 ? locParts.join(" • ") : "Unassigned";

  try {
    const res = await fetch("/api/items", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        style: style,
        color: color,
        size: size,
        line: line || null,
        section: section || null,
        level: level || null,
        box_num: box || null,
        location: location,
        quantity: qty,
        pcs_per_box: pcs
      })
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail || "Failed to add location", "error");
      return;
    }

    closeModal("addLocationModal");
    document.getElementById("addLocationForm").reset();
    showToast(`Added location for style ${style}`, "success");
    addStyleToSelection(style);
    loadStats();
  } catch (err) {
    showToast("Error adding location", "error");
  }
}

async function deleteLocationRecord(itemId) {
  if (!confirm("Are you sure you want to remove this location record from PostgreSQL?")) return;

  try {
    const res = await fetch(`/api/items/${itemId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Delete failed");
    showToast("Location record deleted", "success");
    loadBatchStylesDetails();
    loadStats();
  } catch (err) {
    showToast("Error deleting item", "error");
  }
}

async function loadMovements() {
  const tbody = document.getElementById("movementTableBody");
  try {
    const res = await fetch("/api/movements?limit=50");
    const data = await res.json();
    if (!data || data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center py-6 text-slate-500">No stock movements recorded yet.</td></tr>';
      return;
    }

    tbody.innerHTML = data.map(m => `
      <tr class="hover:bg-slate-800/40">
        <td class="py-2.5 px-3 text-slate-400 font-mono">${m.created_at}</td>
        <td class="py-2.5 px-3">
          <div class="font-bold text-amber-400 font-mono">${escapeHtml(m.style)}</div>
          <div class="text-[10px] text-slate-400">${escapeHtml(m.location)}</div>
        </td>
        <td class="py-2.5 px-3 text-center text-slate-300 font-mono">
          ${escapeHtml(m.size || "-")} / ${escapeHtml(m.color || "-")}
        </td>
        <td class="py-2.5 px-3 text-center font-bold ${m.change_amount > 0 ? 'text-emerald-400' : 'text-red-400'}">
          ${m.change_amount > 0 ? '+' : ''}${m.change_amount}
        </td>
        <td class="py-2.5 px-3 text-center text-slate-300 font-mono font-bold">${m.quantity_after}</td>
        <td class="py-2.5 px-3 text-slate-300">
          <div>${escapeHtml(m.reason || 'Floor adjustment')}</div>
          <div class="text-[10px] text-slate-500">${escapeHtml(m.staff_name || 'Staff')}</div>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-red-400">Failed to load audit trail.</td></tr>';
  }
}

function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("hidden");
  if (id === "movementModal") loadMovements();
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add("hidden");
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
  }, 3200);
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
