// ================= GOOGLE-GRADE ALEXANDER WAREHOUSE ZERO-STATE HERO =================
function getAlexanderEmptyStateHtml(isTable = true) {
  const content = `
    <div class="max-w-xl mx-auto flex flex-col items-center text-center py-8 px-4 select-none">
      
      <!-- 1. Custom Google-Grade Alexander Warehouse 3D Isometric Emblem -->
      <div class="relative mb-4 flex flex-col items-center group">
        <div class="relative w-24 h-24 rounded-3xl bg-gradient-to-br from-[#173456] via-[#1e4875] to-[#0070ba] p-1 shadow-2xl shadow-[#173456]/30 border-2 border-[#38bdf8]/40 flex flex-col items-center justify-center transition-all duration-300 group-hover:scale-105 group-hover:shadow-[#0070ba]/25">
          <!-- 3D Warehouse Isometric Box Vector Icon -->
          <svg class="w-12 h-12 text-white drop-shadow-md" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
            <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
            <line x1="12" y1="22.08" x2="12" y2="12"></line>
          </svg>
          <!-- Modern Luminous "Alexander" Typography Badge -->
          <div class="mt-1 px-3 py-0.5 rounded-full bg-[#0a213a] border border-[#38bdf8]/40 shadow-inner flex items-center gap-1.5">
            <span class="w-1.5 h-1.5 rounded-full bg-[#38bdf8] animate-pulse"></span>
            <span class="text-[9px] font-black font-mono tracking-widest text-[#bae6fd] uppercase">ALEXANDER</span>
          </div>
        </div>
      </div>

      <!-- 2. Facility Pill Badge -->
      <div class="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#e8f1fa] border border-[#b8d4ee] text-[11px] font-bold text-[#0d4771] mb-2.5 shadow-2xs">
        <span class="w-2 h-2 rounded-full bg-[#0070ba]"></span>
        <span>Alexander Warehouse &bull; 50,000+ Sq Ft Active Facility</span>
      </div>

      <!-- 3. Prominent Title (Increased Font Size) -->
      <h3 class="text-xl sm:text-2xl font-black font-mono text-[#173456] tracking-tight">
        Alexander Inventory &amp; Location Finder
      </h3>

      <!-- 4. Prominent Subtitle (Increased Font Size) -->
      <p class="text-sm font-medium text-[#475569] max-w-md mx-auto mt-2 leading-relaxed">
        Search any style code (e.g. <span class="font-mono font-bold text-[#0070ba] bg-[#f0f4f8] px-1.5 py-0.5 rounded border border-[#cbd5e1]">A12501</span>, <span class="font-mono font-bold text-[#0070ba] bg-[#f0f4f8] px-1.5 py-0.5 rounded border border-[#cbd5e1]">VDSW</span>), browse aisles, or tap a quick category below to look up real-time shelf coordinates.
      </p>

      <!-- 5. Interactive Google-Style Action Cards -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5 w-full max-w-lg mt-5 text-left">
        <button onclick="switchWarehousePart('PART_1'); inspectWarehouseAisle('PART_1', '1');"
          class="group p-3 rounded-xl bg-white hover:bg-[#f0f7ff] border border-[#c4d3e2] hover:border-[#0070ba] transition shadow-xs flex items-center gap-2.5 active:scale-98">
          <div class="w-10 h-10 rounded-lg bg-[#e8f1fa] group-hover:bg-[#0070ba] text-[#0d4771] group-hover:text-white flex items-center justify-center text-lg font-bold shrink-0 transition">
            👟
          </div>
          <div class="min-w-0">
            <div class="text-xs font-bold text-[#173456] group-hover:text-[#0070ba] truncate">Part 1 (Allbirds)</div>
            <div class="text-[10px] text-[#64748b]">Lines 1–14 &bull; E-Com</div>
          </div>
        </button>

        <button onclick="switchWarehousePart('PART_2'); inspectWarehouseAisle('PART_2', '1');"
          class="group p-3 rounded-xl bg-white hover:bg-[#f0f7ff] border border-[#c4d3e2] hover:border-[#0070ba] transition shadow-xs flex items-center gap-2.5 active:scale-98">
          <div class="w-10 h-10 rounded-lg bg-[#e8f1fa] group-hover:bg-[#0070ba] text-[#0d4771] group-hover:text-white flex items-center justify-center text-lg font-bold shrink-0 transition">
            📦
          </div>
          <div class="min-w-0">
            <div class="text-xs font-bold text-[#173456] group-hover:text-[#0070ba] truncate">Part 2 (Wholesale)</div>
            <div class="text-[10px] text-[#64748b]">Rows 1–15 &bull; VD / Val</div>
          </div>
        </button>

        <button onclick="addStyleToSelection('LINE 14')"
          class="group p-3 rounded-xl bg-white hover:bg-[#f0f7ff] border border-[#c4d3e2] hover:border-[#0070ba] transition shadow-xs flex items-center gap-2.5 active:scale-98">
          <div class="w-10 h-10 rounded-lg bg-[#e8f1fa] group-hover:bg-[#0070ba] text-[#0d4771] group-hover:text-white flex items-center justify-center text-lg font-bold shrink-0 transition">
            ✨
          </div>
          <div class="min-w-0">
            <div class="text-xs font-bold text-[#173456] group-hover:text-[#0070ba] truncate">Line 14 (New)</div>
            <div class="text-[10px] text-[#64748b]">Sheet 6 &bull; 618 Locs</div>
          </div>
        </button>
      </div>

      <!-- 6. Google Search Pro-Tip -->
      <div class="mt-5 pt-3 border-t border-[#e2eaf2] text-[11px] text-[#64748b] flex items-center justify-center gap-1.5 flex-wrap">
        <span class="font-bold text-[#173456]">Tip:</span>
        <span>You can search multiple styles or aisles at once (e.g. <span class="font-mono text-[#0070ba] font-semibold">A12501, Line 14, Row 1</span>)</span>
      </div>
    </div>
  `;

  if (isTable) {
    return `<tr><td colspan="8" class="text-center py-10 px-4">${content}</td></tr>`;
  } else {
    return `<div class="bg-white rounded-xl border border-[#c4d3e2] p-4 shadow-sm">${content}</div>`;
  }
}

function renderAlexanderEmptyState() {
  const title = document.getElementById("currentStyleTitle");
  if (title) title.textContent = "Alexander Warehouse Inventory";
  const badge = document.getElementById("styleCountBadge");
  if (badge) badge.textContent = "0 Selected";
  const qty = document.getElementById("currentStyleTotalQty");
  if (qty) qty.textContent = "-";
  const sub = document.getElementById("styleSummarySubtitle");
  if (sub) sub.textContent = "Search styles above or select a warehouse Line / Row on the left.";
  
  const tbody = document.getElementById("styleLocationTableBody");
  if (tbody) tbody.innerHTML = getAlexanderEmptyStateHtml(true);

  const mobileCards = document.getElementById("styleLocationMobileCards");
  if (mobileCards) mobileCards.innerHTML = getAlexanderEmptyStateHtml(false);
}

// ================= MOBILE NAVIGATION & RESPONSIVE VIEW STATE =================
let activeMobileView = "SEARCH";

function switchMobileView(view) {
  activeMobileView = view;
  const searchPanel = document.getElementById("panelSearchAndZones");
  const detailPanel = document.getElementById("styleDetailContainer");
  const tabSearch = document.getElementById("mobileTabSearchBtn");
  const tabLoc = document.getElementById("mobileTabLocationsBtn");
  const bottomSearch = document.getElementById("mobileBottomSearchBtn");
  const bottomLoc = document.getElementById("mobileBottomLocBtn");

  if (!searchPanel || !detailPanel) return;

  if (view === "SEARCH") {
    searchPanel.classList.remove("hidden");
    searchPanel.classList.add("flex");
    detailPanel.classList.add("hidden");
    detailPanel.classList.remove("flex");

    if (tabSearch) {
      tabSearch.className = "py-2.5 px-3 rounded-lg transition bg-[#173456] text-white shadow-sm flex items-center justify-center gap-1.5 active:scale-95";
    }
    if (tabLoc) {
      tabLoc.className = "py-2.5 px-3 rounded-lg transition text-[#2d4b68] hover:text-[#173456] flex items-center justify-center gap-1.5 active:scale-95";
    }
    if (bottomSearch) {
      bottomSearch.className = "flex-1 py-2 px-2.5 rounded-lg bg-[#244b7a] text-white text-xs font-bold flex items-center justify-center gap-1.5 active:bg-[#1a385c] transition";
    }
    if (bottomLoc) {
      bottomLoc.className = "flex-1 py-2 px-2.5 rounded-lg bg-[#1a385c] text-blue-200 text-xs font-bold flex items-center justify-center gap-1.5 active:bg-[#10243c] transition";
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  } else {
    // LOCATIONS view
    searchPanel.classList.add("hidden");
    searchPanel.classList.remove("flex");
    detailPanel.classList.remove("hidden");
    detailPanel.classList.add("flex");

    if (tabSearch) {
      tabSearch.className = "py-2.5 px-3 rounded-lg transition text-[#2d4b68] hover:text-[#173456] flex items-center justify-center gap-1.5 active:scale-95";
    }
    if (tabLoc) {
      tabLoc.className = "py-2.5 px-3 rounded-lg transition bg-[#173456] text-white shadow-sm flex items-center justify-center gap-1.5 active:scale-95";
    }
    if (bottomSearch) {
      bottomSearch.className = "flex-1 py-2 px-2.5 rounded-lg bg-[#1a385c] text-blue-200 text-xs font-bold flex items-center justify-center gap-1.5 active:bg-[#10243c] transition";
    }
    if (bottomLoc) {
      bottomLoc.className = "flex-1 py-2 px-2.5 rounded-lg bg-[#244b7a] text-white text-xs font-bold flex items-center justify-center gap-1.5 active:bg-[#1a385c] transition";
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function autoSwitchToMobileLocations() {
  if (window.innerWidth < 1024) {
    switchMobileView("LOCATIONS");
  }
}

// Multi-Style State: Array of active style codes
let selectedStyles = [];
let allStylesList = [];
let batchData = null;
let activeItemForAdjust = null;
let searchDebounce = null;

// Self-invoking immediate initialization
function initApp() {
  console.log("Initializing Warehouse OS Frontend...");
  loadStats();
  loadWarehouseOverview();
  loadStylesList();
  renderSelectedStylesChips();

  if (selectedStyles.length > 0) {
    loadBatchStylesDetails();
  } else {
    renderAlexanderEmptyState();
  }

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

  // Split by comma first so style names with spaces (e.g. "VDSW-2092 SND") stay intact
  let parts = [];
  val.split(",").forEach(chunk => {
    const trimmed = chunk.trim().toUpperCase();
    if (!trimmed) return;
    const norm = trimmed.replace(/\s+/g, "");
    const knownMatch = allStylesList.find(
      s => s.style.toUpperCase() === trimmed || s.style.toUpperCase().replace(/\s+/g, "") === norm
    );
    if (knownMatch) {
      parts.push(knownMatch.style.toUpperCase());
    } else if (allStylesList.some(s => s.style.toUpperCase().includes(trimmed))) {
      parts.push(trimmed);
    } else {
      // Check if user pasted multiple space-separated styles that each exist in allStylesList
      const tokens = trimmed.split(/\s+/).filter(Boolean);
      if (tokens.length > 1 && tokens.every(t => allStylesList.some(s => s.style.toUpperCase().startsWith(t)))) {
        parts.push(...tokens);
      } else {
        parts.push(trimmed);
      }
    }
  });
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
    loadBatchStylesDetails(); autoSwitchToMobileLocations();
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
    loadBatchStylesDetails(); autoSwitchToMobileLocations();
  } else {
    batchData = null;
    renderAlexanderEmptyState();
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
    loadBatchStylesDetails(); autoSwitchToMobileLocations();
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
    const res = await fetch("/api/styles?limit=5000");
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

  const qNorm = query.replace(/\s+/g, "");
  const locationSuggestions = [];
  for (let i = 1; i <= 14; i++) {
    const lnCode = `LINE ${i}`;
    if (lnCode.includes(query) || `LINE${i}`.includes(qNorm) || query === String(i)) {
      locationSuggestions.push({ code: lnCode, label: `📍 ${lnCode} (Part 1 Allbirds — View all styles in Line ${i})` });
    }
    const rwCode = `ROW ${i}`;
    if (rwCode.includes(query) || `ROW${i}`.includes(qNorm)) {
      locationSuggestions.push({ code: rwCode, label: `📍 ${rwCode} (Part 2 Von Dutch / Valentino — View all styles in Row ${i})` });
    }
  }
  if ("WALL".includes(query)) {
    locationSuggestions.push({ code: "WALL", label: "📍 WALL ZONE (Part 2 — View all Wall stock)" });
  }

  const matches = allStylesList.filter(s => {
    const stUpper = s.style.toUpperCase();
    return stUpper.includes(query) || stUpper.replace(/\s+/g, "").includes(qNorm);
  }).slice(0, 20);
  if (matches.length === 0 && locationSuggestions.length === 0) {
    dropdown.innerHTML = `<div class="p-3 text-xs text-slate-500">No styles or lines matching "${escapeHtml(query)}"</div>`;
    dropdown.classList.remove("hidden");
    return;
  }

  const locHtml = locationSuggestions.map(loc => `
      <div 
        onclick="addStyleToSelection('${loc.code}'); document.getElementById('styleDropdown').classList.add('hidden'); document.getElementById('styleSearchInput').value='';" 
        class="p-2.5 bg-blue-50 hover:bg-blue-100 cursor-pointer flex justify-between items-center transition border-b border-slate-200">
        <span class="font-mono font-bold text-blue-800 text-xs">${escapeHtml(loc.label)}</span>
        <span class="text-[10px] text-amber-300 font-mono font-bold">+ Load Line/Row</span>
      </div>
    `).join("");
  dropdown.innerHTML = locHtml + matches.map(s => {
    const isSelected = selectedStyles.includes(s.style);
    return `
      <div 
        onclick="addStyleToSelection('${s.style}'); document.getElementById('styleDropdown').classList.add('hidden'); document.getElementById('styleSearchInput').value='';" 
        class="p-2.5 hover:bg-slate-100 cursor-pointer flex justify-between items-center transition ${isSelected ? 'bg-slate-50' : ''}">
        <span class="font-mono font-bold text-[#173456] text-sm flex items-center gap-2">
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

const _JS_SIZE_ORDER = {
  "XXS": 1, "XS": 2, "S": 3, "SM": 3, "M": 4, "MD": 4,
  "L": 5, "LG": 5, "XL": 6, "XXL": 7, "2XL": 7, "3XL": 8, "OS": 900, "ONE SIZE": 900
};
const _JS_SEC_ORDER = { "FRONT": -3, "BACK": -2, "WALL": -1 };
const _JS_ROW_ORDER = { "WALL": 999 };

function _parseNumSort(val, specialMap = null) {
  if (val === null || val === undefined) return 999999;
  const s = String(val).trim().toUpperCase();
  if (!s) return 999999;
  if (specialMap && Object.prototype.hasOwnProperty.call(specialMap, s)) {
    return specialMap[s];
  }
  const num = parseFloat(s);
  if (!isNaN(num)) return num;
  const m = s.match(/[-+]?\d+(?:\.\d+)?/);
  return m ? parseFloat(m[0]) : 999998;
}

function sortItemsByLocationColorSize(items) {
  return [...items].sort((a, b) => {
    const partA = (a.warehouse_part === "PART_2" || (a.row_pos && !a.line)) ? 2 : 1;
    const partB = (b.warehouse_part === "PART_2" || (b.row_pos && !b.line)) ? 2 : 1;
    if (partA !== partB) return partA - partB;

    // 1. Line (Part 1) or Row (Part 2)
    const aisleA = partA === 1 ? _parseNumSort(a.line) : _parseNumSort(a.row_pos, _JS_ROW_ORDER);
    const aisleB = partB === 1 ? _parseNumSort(b.line) : _parseNumSort(b.row_pos, _JS_ROW_ORDER);
    if (aisleA !== aisleB) return aisleA - aisleB;

    // 2. Section (FRONT -> BACK -> WALL -> 1..36)
    const secA = _parseNumSort(a.section, _JS_SEC_ORDER);
    const secB = _parseNumSort(b.section, _JS_SEC_ORDER);
    if (secA !== secB) return secA - secB;

    // 3. Level (1..4)
    const lvlA = _parseNumSort(a.level);
    const lvlB = _parseNumSort(b.level);
    if (lvlA !== lvlB) return lvlA - lvlB;

    // 4. Color (A..Z)
    const colA = String(a.color || "STANDARD").trim().toUpperCase();
    const colB = String(b.color || "STANDARD").trim().toUpperCase();
    if (colA !== colB) return colA.localeCompare(colB);

    // 5. Size (numeric shoe size 5..14 or apparel XS..XL..OS)
    const szA = _parseNumSort(a.size, _JS_SIZE_ORDER);
    const szB = _parseNumSort(b.size, _JS_SIZE_ORDER);
    if (szA !== szB) return szA - szB;

    return String(a.style || "").localeCompare(String(b.style || ""));
  });
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
  return sortItemsByLocationColorSize(items);
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
    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-8 text-slate-400">No locations matching active filter.</td></tr>`;
    return;
  }

  const isAdmin = window.currentWarehouseUser && window.currentWarehouseUser.role === "ADMIN";

  tbody.innerHTML = items.map((item, idx) => {
    const isPart2 = item.warehouse_part === "PART_2" || (item.row_pos && !item.line);
    const coordSummary = isPart2
      ? `Row ${escapeHtml(item.row_pos || "-")} • Sec ${escapeHtml(item.section || "-")} • Lvl ${escapeHtml(item.level || "-")}`
      : `Line ${escapeHtml(item.line || "-")} • Sec ${escapeHtml(item.section || "-")} • Lvl ${escapeHtml(item.level || "-")}`;

    const rowBg = idx % 2 === 1 ? 'bg-[#f7fafc]' : 'bg-white';
    return `
      <tr class="${rowBg} hover:bg-[#e4effa] transition">
        <td class="py-2.5 px-3 font-mono font-bold text-[#173456]">
          ${escapeHtml(item.style)}
        </td>

        <td class="py-2.5 px-3">
          <div class="font-mono font-bold text-[#0f172a] text-xs">
            ${escapeHtml(item.location || coordSummary)}
          </div>
          <div class="text-[10px] text-[#64748b] font-mono">
            ${isPart2 ? ('Part 2 • ' + escapeHtml(item.brand || 'Wholesale')) : 'Part 1 • Allbirds'}
          </div>
        </td>

        <td class="py-2.5 px-3 font-mono text-xs text-[#334155] font-medium">
          ${escapeHtml(item.color || "STANDARD")}
        </td>

        <td class="py-2.5 px-3 text-center font-mono font-bold text-xs text-[#0f172a]">
          ${escapeHtml(item.size || "OS")}
        </td>

        <td class="py-2.5 px-3 text-center font-mono text-xs text-[#475569]">
          <div>${item.box_num ? `Box #${escapeHtml(item.box_num)}` : "-"}</div>
          <div class="text-[10px] text-[#94a3b8]">${item.pcs_per_box ? `${item.pcs_per_box} pcs/box` : ""}</div>
        </td>

        <td class="py-2.5 px-3 text-center">
          <span class="inline-block px-3 py-1 rounded-md text-xs font-bold font-mono bg-[#e8f1fa] text-[#0d4771] border border-[#b8d4ee]">
            ${item.quantity.toLocaleString()} pcs
          </span>
        </td>

        <td class="admin-only-control py-2.5 px-3 text-center ${isAdmin ? '' : 'hidden'}">
          <div class="inline-flex items-center space-x-1 bg-slate-100 border border-slate-300 rounded-lg p-0.5">
            <button onclick="realtimeQuickAdjust(${item.id}, -1)" ${item.quantity <= 0 ? "disabled" : ""} class="w-6 h-6 rounded bg-white hover:bg-slate-200 text-slate-700 font-bold text-xs">-</button>
            <button onclick='openAdjustModal(${JSON.stringify(item)})' class="px-2 py-0.5 text-[11px] font-mono font-semibold text-slate-700 hover:text-blue-600">Adj</button>
            <button onclick="realtimeQuickAdjust(${item.id}, 1)" class="w-6 h-6 rounded bg-white hover:bg-slate-200 text-slate-700 font-bold text-xs">+</button>
          </div>
        </td>

        <td class="admin-only-control py-2.5 px-3 text-right ${isAdmin ? '' : 'hidden'}">
          <button onclick="deleteLocationRecord(${item.id})" class="p-1 text-slate-400 hover:text-red-600 rounded text-xs" title="Delete">🗑️</button>
        </td>
      </tr>
    `;
  }).join("");

  // Update mobile location count badges
  const mLocCount = document.getElementById("mobileLocationCount");
  if (mLocCount) mLocCount.textContent = items.length;
  const mBottomCount = document.getElementById("mobileBottomCount");
  if (mBottomCount) mBottomCount.textContent = items.length;

  // Render Mobile Touch Cards
  const mobileContainer = document.getElementById("styleLocationMobileCards");
  if (mobileContainer) {
    if (items.length === 0) {
      mobileContainer.innerHTML = '<div class="text-center py-8 text-[#64748b] bg-white rounded-xl border border-[#c4d3e2] p-4 text-xs">No locations matching active filter.</div>';
    } else {
      mobileContainer.innerHTML = items.map(item => {
        const isPart2 = item.warehouse_part === "PART_2" || (item.row_pos && !item.line);
        const coordSummary = isPart2
          ? `Row ${escapeHtml(item.row_pos || "-")} • Sec ${escapeHtml(item.section || "-")} • Lvl ${escapeHtml(item.level || "-")}`
          : `Line ${escapeHtml(item.line || "-")} • Sec ${escapeHtml(item.section || "-")} • Lvl ${escapeHtml(item.level || "-")}`;
        const locDisplay = item.location || coordSummary;

        return `
          <div class="bg-white border border-[#c4d3e2] rounded-xl p-3 shadow-xs space-y-2">
            <!-- Header: Style SKU & Quantity Pill -->
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-1.5">
                <span class="w-2.5 h-2.5 rounded-full bg-[#0070ba]"></span>
                <span class="font-mono font-bold text-sm text-[#173456]">${escapeHtml(item.style)}</span>
              </div>
              <span class="inline-block px-2.5 py-0.5 rounded text-xs font-bold font-mono bg-[#e8f1fa] text-[#0d4771] border border-[#b8d4ee]">
                ${item.quantity.toLocaleString()} pcs
              </span>
            </div>

            <!-- Warehouse Location Card Highlight -->
            <div class="bg-[#f0f4f8] border border-[#d3dfea] rounded-lg p-2.5 flex items-center justify-between">
              <div>
                <span class="text-[10px] uppercase font-bold text-[#64748b] block">Shelf Location</span>
                <div class="font-mono font-bold text-xs text-[#0f172a] mt-0.5">${escapeHtml(locDisplay)}</div>
                <div class="text-[10px] text-[#64748b] font-mono mt-0.5">
                  ${isPart2 ? ('Part 2 • ' + escapeHtml(item.brand || 'Wholesale')) : 'Part 1 • Allbirds'}
                </div>
              </div>
              <div class="text-right">
                <span class="text-[10px] uppercase font-bold text-[#64748b] block">Size</span>
                <span class="font-mono font-black text-sm text-[#173456] block mt-0.5">${escapeHtml(item.size || 'OS')}</span>
              </div>
            </div>

            <!-- Details: Color & Box -->
            <div class="flex items-center justify-between text-xs text-[#475569] px-1">
              <div>Color: <strong class="text-[#173456]">${escapeHtml(item.color || 'STANDARD')}</strong></div>
              <div class="font-mono text-[11px] text-[#64748b]">
                ${item.box_num ? `Box #${escapeHtml(item.box_num)}` : ''} ${item.pcs_per_box ? `(${item.pcs_per_box} pcs/box)` : ''}
              </div>
            </div>

            <!-- Admin Action Buttons (Large Touch Targets) -->
            ${isAdmin ? `
              <div class="flex items-center justify-between pt-2 border-t border-[#e2eaf2]">
                <div class="inline-flex items-center space-x-2 bg-[#f0f4f8] border border-[#cbd5e1] rounded-lg p-1">
                  <button onclick="realtimeQuickAdjust(${item.id}, -1)" ${item.quantity <= 0 ? 'disabled' : ''} class="w-9 h-9 rounded bg-white text-base font-bold text-[#173456] shadow-xs active:bg-slate-200 flex items-center justify-center">-</button>
                  <button onclick='openAdjustModal(${JSON.stringify(item)})' class="px-3 py-1.5 text-xs font-mono font-bold text-[#173456]">Adj</button>
                  <button onclick="realtimeQuickAdjust(${item.id}, 1)" class="w-9 h-9 rounded bg-white text-base font-bold text-[#173456] shadow-xs active:bg-slate-200 flex items-center justify-center">+</button>
                </div>
                <button onclick="deleteLocationRecord(${item.id})" class="p-2 text-slate-400 hover:text-red-600 text-sm" title="Delete">🗑️</button>
              </div>
            ` : ''}
          </div>
        `;
      }).join("");
    }
  }

}

function triggerPrintPickSheet() {
  if (!batchData) {
    showToast("Please select styles first", "error");
    return;
  }

  const rawItems = getActiveFilteredItems();
  if (rawItems.length === 0) {
    showToast("No locations found to print", "error");
    return;
  }

  // 1. Consolidate items by (style, location, color, size) so no address or size is printed multiple times
  const grouped = new Map();
  rawItems.forEach(item => {
    const locKey = (item.location || `${item.line || ''}-${item.row_pos || ''}-${item.section || ''}-${item.level || ''}`).trim();
    const key = `${item.style}|${locKey}|${item.color || 'STANDARD'}|${item.size || 'OS'}`.toUpperCase();

    if (!grouped.has(key)) {
      grouped.set(key, {
        style: item.style,
        location: item.location || 'Unassigned',
        line: item.line,
        row_pos: item.row_pos,
        section: item.section,
        level: item.level,
        color: item.color || 'STANDARD',
        size: item.size || 'OS',
        warehouse_part: item.warehouse_part,
        brand: item.brand,
        total_quantity: 0,
        box_count: 0,
        boxes: [],
        pcs_per_box: item.pcs_per_box
      });
    }

    const g = grouped.get(key);
    g.total_quantity += (item.quantity || 0);
    g.box_count += 1;
    if (item.box_num) g.boxes.push(item.box_num);
  });

  const consolidatedItems = Array.from(grouped.values()).map(g => {
    let boxDetails = "-";
    if (g.boxes.length > 0) {
      boxDetails = `Box #${g.boxes.join(", #")}`;
      if (g.pcs_per_box) boxDetails += ` (${g.pcs_per_box} pcs/box)`;
    } else if (g.box_count > 1) {
      boxDetails = `${g.box_count} Boxes${g.pcs_per_box ? ` (${g.pcs_per_box} pcs/box)` : ''}`;
    } else if (g.pcs_per_box) {
      boxDetails = `${g.pcs_per_box} pcs/box`;
    }

    return {
      style: g.style,
      location: g.location,
      line: g.line,
      row_pos: g.row_pos,
      section: g.section,
      level: g.level,
      color: g.color,
      size: g.size,
      warehouse_part: g.warehouse_part,
      brand: g.brand,
      quantity: g.total_quantity,
      box_details: boxDetails
    };
  });

  // 2. Strict physical walking order sort: Line/Row -> Section -> Level -> Color -> Size
  const sortedItems = sortItemsByLocationColorSize(consolidatedItems);

  document.getElementById("printStyleCode").textContent = batchData.found_styles.join(", ");
  const now = new Date();
  document.getElementById("printTimestamp").textContent = now.toLocaleDateString() + " " + now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  document.getElementById("printTotalLocations").textContent = `${sortedItems.length} locations`;
  
  const totalUnits = sortedItems.reduce((sum, i) => sum + i.quantity, 0);
  document.getElementById("printTotalUnits").textContent = `${totalUnits.toLocaleString()} units`;

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
      </td>
      <td class="p-2 border-r border-black font-semibold">
        ${escapeHtml(item.color || 'STANDARD')}
      </td>
      <td class="p-2 border-r border-black text-center font-bold font-mono text-sm">
        ${escapeHtml(item.size || 'OS')}
      </td>
      <td class="p-2 border-r border-black text-center font-mono text-xs">
        ${escapeHtml(item.box_details || '-')}
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
    
    loadBatchStylesDetails(); autoSwitchToMobileLocations();
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

    loadBatchStylesDetails(); autoSwitchToMobileLocations();
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
    loadBatchStylesDetails(); autoSwitchToMobileLocations();
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
  const rowEl = document.getElementById("newLocRow");
  const row_pos = rowEl ? rowEl.value.trim() : "";
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
        row_pos: row_pos || null,
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
    loadBatchStylesDetails(); autoSwitchToMobileLocations();
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


// ================= 50,000+ SQ FT 2-PART WAREHOUSE MAP FUNCTIONS (CLEAN LIGHT THEME) =================
let warehouseOverviewData = null;
let activeWarehousePart = "PART_1";
let activeAisleData = null;

async function loadWarehouseOverview() {
  try {
    const res = await fetch("/api/warehouse-overview");
    if (!res.ok) return;
    warehouseOverviewData = await res.json();
    renderWarehouseMapOverview();
  } catch (err) {
    console.error("Warehouse overview error:", err);
  }
}

function switchWarehousePart(part) {
  activeWarehousePart = part;
  const p1Panel = document.getElementById("warehousePart1Panel");
  const p2Panel = document.getElementById("warehousePart2Panel");
  const btn1 = document.getElementById("tabPart1Btn");
  const btn2 = document.getElementById("tabPart2Btn");

  if (part === "PART_1") {
    if (p1Panel) p1Panel.classList.remove("hidden");
    if (p2Panel) p2Panel.classList.add("hidden");
    if (btn1) btn1.className = "px-2.5 py-1.5 rounded-md text-xs font-bold transition bg-[#173456] text-white shadow-sm";
    if (btn2) btn2.className = "px-2.5 py-1.5 rounded-md text-xs font-bold transition text-[#2d4b68] hover:text-[#173456]";
  } else {
    if (p1Panel) p1Panel.classList.add("hidden");
    if (p2Panel) p2Panel.classList.remove("hidden");
    if (btn2) btn2.className = "px-2.5 py-1.5 rounded-md text-xs font-bold transition bg-[#173456] text-white shadow-sm";
    if (btn1) btn1.className = "px-2.5 py-1.5 rounded-md text-xs font-bold transition text-[#2d4b68] hover:text-[#173456]";
  }
}

function renderWarehouseMapOverview() {
  if (!warehouseOverviewData) return;
  const p1 = warehouseOverviewData.part_1_allbirds;
  const p2 = warehouseOverviewData.part_2_vd_valentino;

  const p1Pill = document.getElementById("part1StatsPill");
  if (p1Pill && p1) {
    p1Pill.innerHTML = `<strong>${p1.total_styles}</strong> Styles &bull; <strong>${p1.total_records.toLocaleString()}</strong> Locations &bull; <strong>${p1.total_units.toLocaleString()}</strong> Pcs`;
  }

  const p2Pill = document.getElementById("part2StatsPill");
  if (p2Pill && p2) {
    const pl = warehouseOverviewData.placement_totals || {};
    p2Pill.innerHTML = `<strong>${p2.total_styles}</strong> Styles &bull; Front: <strong>${(pl.GROUND_FRONT || 0).toLocaleString()}</strong> &bull; Back: <strong>${(pl.GROUND_BACK || 0).toLocaleString()}</strong> &bull; Wall: <strong>${(pl.WALL || 0).toLocaleString()}</strong>`;
  }

  const p1Grid = document.getElementById("part1LinesGrid");
  if (p1Grid && p1 && p1.lines) {
    p1Grid.innerHTML = p1.lines.map(ln => {
      const isSelected = activeAisleData && activeAisleData.part === "PART_1" && activeAisleData.aisle === String(ln.line);
      return `
        <button onclick="inspectWarehouseAisle('PART_1', '${ln.line}')"
          class="text-left p-2.5 rounded-lg border transition ${isSelected ? 'bg-[#e6f1fa] border-[#0070ba] ring-1 ring-[#0070ba]' : 'bg-[#f8fafc] border-[#cbd5e1] hover:border-[#0070ba] hover:bg-white'}">
          <div class="flex items-center justify-between">
            <span class="font-mono font-bold text-xs text-[#173456]">LINE ${escapeHtml(ln.line)}</span>
            <span class="text-[10px] font-mono text-slate-500">${ln.occupied_sections} sec</span>
          </div>
          <div class="mt-1 text-xs font-bold text-[#0070ba] font-mono">${ln.total_units.toLocaleString()} pcs</div>
          <div class="text-[10px] text-slate-500 font-mono">${ln.total_styles} styles</div>
        </button>
      `;
    }).join("");
  }

  const p2Grid = document.getElementById("part2RowsGrid");
  if (p2Grid && p2 && p2.rows) {
    p2Grid.innerHTML = p2.rows.map(rw => {
      const isWall = rw.row === "WALL";
      const isSelected = activeAisleData && activeAisleData.part === "PART_2" && activeAisleData.aisle === String(rw.row);
      const label = isWall ? "WALL" : `ROW ${escapeHtml(rw.row)}`;
      return `
        <button onclick="inspectWarehouseAisle('PART_2', '${rw.row}')"
          class="text-left p-2.5 rounded-lg border transition ${isSelected ? 'bg-[#e6f1fa] border-[#0070ba] ring-1 ring-[#0070ba]' : 'bg-[#f8fafc] border-[#cbd5e1] hover:border-[#0070ba] hover:bg-white'}">
          <div class="flex items-center justify-between">
            <span class="font-mono font-bold text-xs text-[#173456]">${label}</span>
            <span class="text-[10px] font-mono text-slate-500">${isWall ? 'Wall' : rw.occupied_sections + ' sec'}</span>
          </div>
          <div class="mt-1 text-xs font-bold text-[#0070ba] font-mono">${rw.total_units.toLocaleString()} pcs</div>
          <div class="text-[10px] text-slate-500 font-mono">${rw.total_styles} styles</div>
        </button>
      `;
    }).join("");
  }
}

async function inspectWarehouseAisle(part, aisle) {
  const token = part === "PART_1" ? `LINE ${aisle}` : (aisle === "WALL" ? "WALL" : `ROW ${aisle}`);
  selectedStyles = [token];
  renderSelectedStylesChips();
  loadBatchStylesDetails(); autoSwitchToMobileLocations();

  const container = document.getElementById("aisleInspectorContainer");
  const grid = document.getElementById("aisleSectionsGrid");
  const title = document.getElementById("aisleInspectorTitle");
  const sub = document.getElementById("aisleInspectorSubtitle");
  if (!container || !grid) return;

  container.classList.remove("hidden");
  grid.innerHTML = `<div class="text-center py-4 text-xs text-slate-500 font-mono">Loading sections...</div>`;

  try {
    const res = await fetch(`/api/warehouse-map/aisle?part=${encodeURIComponent(part)}&aisle=${encodeURIComponent(aisle)}`);
    if (!res.ok) return;
    activeAisleData = await res.json();
    renderWarehouseMapOverview();

    if (title) title.textContent = activeAisleData.aisle_label;
    if (sub) {
      sub.innerHTML = `<strong>${activeAisleData.total_sections_occupied}</strong> Sections &bull; <strong>${activeAisleData.total_units.toLocaleString()} pcs</strong>`;
    }
    renderAisleSectionsGrid();
  } catch (err) {
    console.error("Aisle detail error:", err);
  }
}

function closeAisleInspector() {
  activeAisleData = null;
  const container = document.getElementById("aisleInspectorContainer");
  if (container) container.classList.add("hidden");
  renderWarehouseMapOverview();
}

function filterAisleSections() {
  renderAisleSectionsGrid();
}

function renderAisleSectionsGrid() {
  const grid = document.getElementById("aisleSectionsGrid");
  if (!grid || !activeAisleData) return;

  const q = ((document.getElementById("aisleSectionFilterInput") && document.getElementById("aisleSectionFilterInput").value) || "").trim().toUpperCase();
  let sections = activeAisleData.sections || [];
  if (q) {
    sections = sections.filter(sec => {
      if (sec.section.toUpperCase().includes(q)) return true;
      for (const lvl of ["1", "2", "3", "4", "OTHER"]) {
        if ((sec.levels[lvl] || []).some(it => it.style.toUpperCase().includes(q))) return true;
      }
      return false;
    });
  }

  grid.innerHTML = sections.map(sec => {
    const levelsHtml = ["1", "2", "3", "4"].map(lvl => {
      const cellItems = sec.levels[lvl] || [];
      if (cellItems.length === 0) {
        return `<div class="bg-slate-50 border border-slate-200 rounded p-1.5 text-[10px] text-slate-400 font-mono">Lvl ${lvl}: Empty</div>`;
      }
      const lvlUnits = cellItems.reduce((s, i) => s + (i.quantity || 0), 0);
      return `<div class="bg-white border border-slate-200 rounded p-1.5 text-[10px] font-mono"><strong class="text-slate-800">Lvl ${lvl}:</strong> <span class="text-blue-700 font-bold">${lvlUnits} pcs</span></div>`;
    }).join("");

    return `
      <div class="bg-slate-50 border border-slate-200 rounded-lg p-2 space-y-1.5">
        <div class="flex items-center justify-between text-xs font-mono">
          <strong class="text-[#173456]">Section ${escapeHtml(sec.section)}</strong>
          <span class="font-bold text-blue-700">${sec.total_units.toLocaleString()} pcs</span>
        </div>
        <div class="grid grid-cols-2 gap-1">${levelsHtml}</div>
      </div>
    `;
  }).join("");
}

function loadActiveAisleIntoLookup() {
  if (!activeAisleData) return;
  const token = activeAisleData.part === "PART_1"
    ? `LINE ${activeAisleData.aisle}`
    : (activeAisleData.aisle === "WALL" ? "WALL" : `ROW ${activeAisleData.aisle}`);
  selectedStyles = [token];
  renderSelectedStylesChips();
  loadBatchStylesDetails(); autoSwitchToMobileLocations();
}
