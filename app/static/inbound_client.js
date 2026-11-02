// =========================================================================
// Oracle NetSuite ERP - Multi-Pallet Inbound Stock Receiving & AI Workflow Client
// Compatible with both Main Dashboard (index.html) and Manager Section (manage.html)
// =========================================================================

// Global Helper Functions (safe fallback if not present)
if (typeof window.openModal !== "function") {
  window.openModal = function(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove("hidden");
    if (id === "movementModal" && typeof window.loadMovements === "function") {
      window.loadMovements();
    }
  };
}

if (typeof window.closeModal !== "function") {
  window.closeModal = function(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add("hidden");
  };
}

if (typeof window.showToast !== "function") {
  window.showToast = function(message, type = "info") {
    let container = document.getElementById("toastContainer");
    if (!container) {
      container = document.createElement("div");
      container.id = "toastContainer";
      container.className = "fixed bottom-5 right-5 z-50 flex flex-col space-y-2 pointer-events-none";
      document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    const bg = type === "error" ? "bg-red-600 text-white" : "bg-[#0070ba] text-white";
    toast.className = `${bg} px-4 py-2.5 rounded-xl shadow-2xl text-xs font-semibold flex items-center space-x-2 transition transform duration-200`;
    toast.innerHTML = `<span>${window.escapeHtml ? window.escapeHtml(message) : message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 200);
    }, 3200);
  };
}

if (typeof window.escapeHtml !== "function") {
  window.escapeHtml = function(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  };
}

// Global Inbound State
window.currentDocUploadMode = "CAMERA"; // "CAMERA" or "UPLOAD"
window.currentInboundDraft = {
  shipment_number: "",
  po_number: "",
  carrier_vendor: "",
  pallets_count: 1,
  total_boxes: 0,
  total_units: 0,
  packing_list_filename: "",
  packing_list_data: null,
  commercial_invoice_filename: "",
  commercial_invoice_data: null,
  notes: "",
  created_by: "Warehouse Manager",
  items: []
};

window.activeAdminShipmentsTab = "PENDING_APPROVAL";
window.activeAdminSelectedShipment = null;

// ================= 1. OPEN RECEIVING INTAKE SELECTOR (3 OPTIONS) =================
function openReceivingIntakeModal() {
  openModal("receivingIntakeModal");
}

function selectIntakeOption(option) {
  closeModal("receivingIntakeModal");

  if (option === "CAMERA") {
    window.currentDocUploadMode = "CAMERA";
    const title = document.getElementById("ingestModalTitle");
    const pIcon = document.getElementById("packingListBtnIcon");
    const pTxt = document.getElementById("packingListBtnText");
    const iIcon = document.getElementById("invoiceBtnIcon");
    const iTxt = document.getElementById("invoiceBtnText");
    if (title) title.textContent = "📸 Mobile Camera Scan — Packing List & Invoice";
    if (pIcon) pIcon.textContent = "📸";
    if (pTxt) pTxt.textContent = "Take Photo (Camera)";
    if (iIcon) iIcon.textContent = "📸";
    if (iTxt) iTxt.textContent = "Take Photo (Camera)";
    openModal("documentIngestModal");
  } else if (option === "UPLOAD") {
    window.currentDocUploadMode = "UPLOAD";
    const title = document.getElementById("ingestModalTitle");
    const pIcon = document.getElementById("packingListBtnIcon");
    const pTxt = document.getElementById("packingListBtnText");
    const iIcon = document.getElementById("invoiceBtnIcon");
    const iTxt = document.getElementById("invoiceBtnText");
    if (title) title.textContent = "📁 Upload Documents (PDF / Image)";
    if (pIcon) pIcon.textContent = "📁";
    if (pTxt) pTxt.textContent = "Select File";
    if (iIcon) iIcon.textContent = "📁";
    if (iTxt) iTxt.textContent = "Select File";
    openModal("documentIngestModal");
  } else {
    // Option 3: Manual Direct Entry
    openReceivingModal();
  }
}

// ================= 2. DOCUMENT INGEST & FILE HANDLING =================
function triggerDocInput(docType) {
  if (docType === "PACKING_LIST") {
    const inputId = window.currentDocUploadMode === "CAMERA" ? "cameraPackingListInput" : "filePackingListInput";
    const el = document.getElementById(inputId);
    if (el) el.click();
  } else {
    const inputId = window.currentDocUploadMode === "CAMERA" ? "cameraInvoiceInput" : "fileInvoiceInput";
    const el = document.getElementById(inputId);
    if (el) el.click();
  }
}

function handleDocFileChange(e, docType) {
  const file = e.target.files && e.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = function(evt) {
    const dataUri = evt.target.result;
    if (docType === "PACKING_LIST") {
      window.currentInboundDraft.packing_list_filename = file.name;
      window.currentInboundDraft.packing_list_data = dataUri;

      const thumb = document.getElementById("packingListThumb");
      if (thumb) thumb.src = dataUri;
      document.getElementById("packingListPlaceholder")?.classList.add("hidden");
      document.getElementById("packingListPreviewContainer")?.classList.remove("hidden");
      const nameLbl = document.getElementById("packingListFileNameLabel");
      if (nameLbl) nameLbl.textContent = file.name;
    } else {
      window.currentInboundDraft.commercial_invoice_filename = file.name;
      window.currentInboundDraft.commercial_invoice_data = dataUri;

      const thumb = document.getElementById("invoiceThumb");
      if (thumb) thumb.src = dataUri;
      document.getElementById("invoicePlaceholder")?.classList.add("hidden");
      document.getElementById("invoicePreviewContainer")?.classList.remove("hidden");
      const nameLbl = document.getElementById("invoiceFileNameLabel");
      if (nameLbl) nameLbl.textContent = file.name;
    }
  };
  reader.readAsDataURL(file);
}

// ================= 3. MULTIMODAL DOCUMENT AI EXTRACTION =================
async function runAiDocumentExtraction() {
  const btn = document.getElementById("startAiExtractBtn");
  const bar = document.getElementById("aiProcessingBar");

  if (bar) bar.classList.remove("hidden");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span>⚙️</span><span>AI Extracting Line Items...</span>`;
  }

  const payload = {
    packing_list_data: window.currentInboundDraft.packing_list_data,
    commercial_invoice_data: window.currentInboundDraft.commercial_invoice_data,
    packing_list_filename: window.currentInboundDraft.packing_list_filename || "Packing_List.jpg",
    commercial_invoice_filename: window.currentInboundDraft.commercial_invoice_filename || "Commercial_Invoice.jpg"
  };

  try {
    const res = await fetch("/api/inbound/parse-docs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "AI extraction failed");
    }

    const resJson = await res.json();
    const data = resJson.data || {};

    const palletsInput = parseInt(document.getElementById("ingestPalletCount")?.value, 10) || data.pallets_count || 1;
    const poInput = document.getElementById("ingestPoNumber")?.value.trim() || data.po_number || "";
    const vendorInput = document.getElementById("ingestVendor")?.value.trim() || data.carrier_vendor || "";

    window.currentInboundDraft.pallets_count = palletsInput;
    window.currentInboundDraft.po_number = poInput;
    window.currentInboundDraft.carrier_vendor = vendorInput;
    window.currentInboundDraft.notes = data.notes || "";

    // Generate random shipment identifier
    const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    const randHex = Math.random().toString(16).substring(2, 6).toUpperCase();
    window.currentInboundDraft.shipment_number = `SHP-${dateStr}-${randHex}`;

    // Map extracted items with initial staged locations
    window.currentInboundDraft.items = (data.items || []).map((it, idx) => {
      const isPart2 = (it.warehouse_part === "PART_2") || (it.style && (it.style.startsWith("VD") || it.style.startsWith("VO")));
      const defaultLine = isPart2 ? "" : String((idx % 14) + 1);
      const defaultRow = isPart2 ? String((idx % 14) + 1) : "";
      const defaultSec = String((idx * 3 % 32) + 1);
      const defaultLvl = String((idx % 4) + 1);
      const defaultBox = String((idx % 8) + 1);

      const locStr = isPart2
        ? `Row ${defaultRow} • Sec ${defaultSec} • Lvl ${defaultLvl} • Box ${defaultBox}`
        : `Line ${defaultLine} • Sec ${defaultSec} • Lvl ${defaultLvl} • Box ${defaultBox}`;

      return {
        style: it.style || "A12501",
        brand: it.brand || (isPart2 ? "VON DUTCH" : "ALLBIRDS"),
        warehouse_part: isPart2 ? "PART_2" : "PART_1",
        color: it.color || "STANDARD",
        size: it.size || "OS",
        box_count: it.box_count || 10,
        pcs_per_box: it.pcs_per_box || 12,
        quantity: it.quantity || ((it.box_count || 10) * (it.pcs_per_box || 12)),
        line: defaultLine,
        row_pos: defaultRow,
        section: defaultSec,
        level: defaultLvl,
        box_num: defaultBox,
        location: locStr
      };
    });

    closeModal("documentIngestModal");
    showToast(`✨ AI extracted ${window.currentInboundDraft.items.length} product lines from documents!`, "success");

    // Open Staging workspace
    openStagingWorkspace();
  } catch (err) {
    console.error("AI extract error:", err);
    showToast("Error extracting documents: " + err.message, "error");
  } finally {
    if (bar) bar.classList.add("hidden");
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<span>✨</span><span>Extract Shipment with AI & Stage Locations</span>`;
    }
  }
}

// ================= 4. INBOUND STAGING WORKSPACE =================
function openStagingWorkspace() {
  const numEl = document.getElementById("stgShipmentNumber");
  const poEl = document.getElementById("stgPoNumber");
  const palEl = document.getElementById("stgPalletsCount");
  const notesEl = document.getElementById("stagingShipmentNotes");

  if (numEl) numEl.textContent = window.currentInboundDraft.shipment_number || "SHP-PENDING";
  if (poEl) poEl.textContent = window.currentInboundDraft.po_number || "N/A";
  if (palEl) palEl.textContent = `${window.currentInboundDraft.pallets_count} Pallet${window.currentInboundDraft.pallets_count === 1 ? '' : 's'}`;
  if (notesEl) notesEl.value = window.currentInboundDraft.notes || "";

  renderStagingItemsTable();
  openModal("inboundStagingModal");
}

function renderStagingItemsTable() {
  const tbody = document.getElementById("stagingItemsTableBody");
  if (!tbody) return;

  const items = window.currentInboundDraft.items || [];
  const totBoxes = items.reduce((sum, i) => sum + (parseInt(i.box_count, 10) || 0), 0);
  const totUnits = items.reduce((sum, i) => sum + (parseInt(i.quantity, 10) || 0), 0);

  const tBoxesEl = document.getElementById("stgTotalBoxes");
  const tUnitsEl = document.getElementById("stgTotalUnits");
  const countEl = document.getElementById("stgItemsCount");

  if (tBoxesEl) tBoxesEl.textContent = `${totBoxes} Boxes`;
  if (tUnitsEl) tUnitsEl.textContent = `${totUnits.toLocaleString()} Units`;
  if (countEl) countEl.textContent = items.length;

  if (items.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="text-center py-8 text-slate-400">
          No items staged yet. Click "+ Add Item Line" above.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = items.map((it, idx) => `
    <tr class="${idx % 2 === 1 ? 'bg-slate-50/70' : 'bg-white'} hover:bg-blue-50/40 transition">
      <td class="p-2">
        <input type="text" value="${escapeHtml(it.style)}" onchange="updateStagingItemField(${idx}, 'style', this.value)"
          class="w-full bg-white border border-slate-300 rounded px-1.5 py-1 text-xs font-bold font-mono uppercase text-[#173456]" />
      </td>
      <td class="p-2 text-center">
        <input type="text" value="${escapeHtml(it.color)}" onchange="updateStagingItemField(${idx}, 'color', this.value)"
          class="w-20 bg-white border border-slate-300 rounded px-1 py-1 text-[11px] text-center uppercase" />
      </td>
      <td class="p-2 text-center">
        <input type="text" value="${escapeHtml(it.size)}" onchange="updateStagingItemField(${idx}, 'size', this.value)"
          class="w-14 bg-white border border-slate-300 rounded px-1 py-1 text-xs font-bold text-center uppercase text-slate-900" />
      </td>
      <td class="p-2 text-center">
        <input type="number" min="1" value="${it.box_count || 1}" onchange="updateStagingItemBoxes(${idx}, this.value)"
          class="w-14 bg-white border border-slate-300 rounded px-1 py-1 text-xs text-center font-bold text-slate-700" />
      </td>
      <td class="p-2 text-center">
        <input type="number" min="1" value="${it.pcs_per_box || 12}" onchange="updateStagingItemPcsBox(${idx}, this.value)"
          class="w-14 bg-white border border-slate-300 rounded px-1 py-1 text-xs text-center text-slate-600" />
      </td>
      <td class="p-2 text-center">
        <input type="number" min="1" value="${it.quantity || 0}" onchange="updateStagingItemField(${idx}, 'quantity', parseInt(this.value, 10))"
          class="w-16 bg-white border border-slate-300 rounded px-1 py-1 text-xs font-black text-center text-[#0070ba]" />
      </td>
      <td class="p-2">
        <div class="flex items-center gap-1">
          <input type="text" placeholder="Line/Row" value="${it.warehouse_part === 'PART_2' ? (it.row_pos || '') : (it.line || '')}"
            onchange="updateStagingItemLocation(${idx}, '${it.warehouse_part === 'PART_2' ? 'row_pos' : 'line'}', this.value)"
            class="w-14 bg-white border border-slate-300 rounded px-1 py-1 text-[11px] text-center font-mono" title="Line or Row" />
          <input type="text" placeholder="Sec" value="${it.section || ''}"
            onchange="updateStagingItemLocation(${idx}, 'section', this.value)"
            class="w-12 bg-white border border-slate-300 rounded px-1 py-1 text-[11px] text-center font-mono" title="Section" />
          <input type="text" placeholder="Lvl" value="${it.level || ''}"
            onchange="updateStagingItemLocation(${idx}, 'level', this.value)"
            class="w-10 bg-white border border-slate-300 rounded px-1 py-1 text-[11px] text-center font-mono" title="Level" />
          <input type="text" placeholder="Box" value="${it.box_num || ''}"
            onchange="updateStagingItemLocation(${idx}, 'box_num', this.value)"
            class="w-12 bg-white border border-slate-300 rounded px-1 py-1 text-[11px] text-center font-mono" title="Box #" />
        </div>
        <div class="text-[10px] text-slate-500 font-mono mt-0.5 truncate">
          📍 ${escapeHtml(it.location || 'Unassigned')}
        </div>
      </td>
      <td class="p-2 text-center">
        <button type="button" onclick="removeStagingRow(${idx})" class="p-1 text-slate-400 hover:text-red-600 transition" title="Remove line">
          🗑️
        </button>
      </td>
    </tr>
  `).join("");
}

function updateStagingItemField(idx, field, val) {
  if (window.currentInboundDraft.items[idx]) {
    window.currentInboundDraft.items[idx][field] = val;
  }
}

function updateStagingItemBoxes(idx, val) {
  const item = window.currentInboundDraft.items[idx];
  if (!item) return;
  item.box_count = parseInt(val, 10) || 1;
  if (item.pcs_per_box) {
    item.quantity = item.box_count * item.pcs_per_box;
  }
  renderStagingItemsTable();
}

function updateStagingItemPcsBox(idx, val) {
  const item = window.currentInboundDraft.items[idx];
  if (!item) return;
  item.pcs_per_box = parseInt(val, 10) || 1;
  item.quantity = (item.box_count || 1) * item.pcs_per_box;
  renderStagingItemsTable();
}

function updateStagingItemLocation(idx, field, val) {
  const item = window.currentInboundDraft.items[idx];
  if (!item) return;
  item[field] = val.trim();

  // Rebuild location string
  const isPart2 = item.warehouse_part === "PART_2" || item.row_pos;
  const parts = [];
  if (isPart2) {
    if (item.row_pos) parts.push(`Row ${item.row_pos}`);
  } else {
    if (item.line) parts.push(`Line ${item.line}`);
  }
  if (item.section) parts.push(`Sec ${item.section}`);
  if (item.level) parts.push(`Lvl ${item.level}`);
  if (item.box_num) parts.push(`Box ${item.box_num}`);

  item.location = parts.length > 0 ? parts.join(" • ") : "Unassigned";
  renderStagingItemsTable();
}

function addEmptyStagingRow() {
  window.currentInboundDraft.items.push({
    style: "A12501",
    brand: "ALLBIRDS",
    warehouse_part: "PART_1",
    color: "STANDARD",
    size: "OS",
    box_count: 5,
    pcs_per_box: 12,
    quantity: 60,
    line: "1",
    row_pos: "",
    section: "1",
    level: "1",
    box_num: "1",
    location: "Line 1 • Sec 1 • Lvl 1 • Box 1"
  });
  renderStagingItemsTable();
}

function removeStagingRow(idx) {
  window.currentInboundDraft.items.splice(idx, 1);
  renderStagingItemsTable();
}

// ================= 5. SUBMIT STAGED SHIPMENT FOR ADMIN APPROVAL =================
async function submitInboundShipmentForApproval() {
  const btn = document.getElementById("submitStagedShipmentBtn");
  if (window.currentInboundDraft.items.length === 0) {
    showToast("Please add at least 1 verified product line before submitting.", "error");
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span>⏳</span><span>Submitting to Admin...</span>`;
  }

  const staffName = (window.currentWarehouseUser && window.currentWarehouseUser.full_name) || "Warehouse Manager";
  const notes = (document.getElementById("stagingShipmentNotes")?.value || "").trim();

  const payload = {
    shipment_number: window.currentInboundDraft.shipment_number,
    po_number: window.currentInboundDraft.po_number || null,
    carrier_vendor: window.currentInboundDraft.carrier_vendor || null,
    pallets_count: window.currentInboundDraft.pallets_count || 1,
    total_boxes: window.currentInboundDraft.items.reduce((s, i) => s + (parseInt(i.box_count, 10) || 0), 0),
    total_units: window.currentInboundDraft.items.reduce((s, i) => s + (parseInt(i.quantity, 10) || 0), 0),
    packing_list_filename: window.currentInboundDraft.packing_list_filename || null,
    packing_list_data: window.currentInboundDraft.packing_list_data || null,
    commercial_invoice_filename: window.currentInboundDraft.commercial_invoice_filename || null,
    commercial_invoice_data: window.currentInboundDraft.commercial_invoice_data || null,
    notes: notes || null,
    created_by: staffName,
    items: window.currentInboundDraft.items
  };

  try {
    const res = await fetch("/api/inbound/shipments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Submission failed");
    }

    const created = await res.json();
    closeModal("inboundStagingModal");
    showToast(`🚀 Shipment ${created.shipment_number} submitted! Waiting for Admin confirmation.`, "success");

    // Refresh Admin pending badge
    checkAdminInboundPendingCount();
  } catch (err) {
    console.error("Submit shipment error:", err);
    showToast("Error submitting shipment: " + err.message, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<span>🚀</span><span>Submit Shipment for Admin Approval</span>`;
    }
  }
}

// ================= 6. ADMIN APPROVAL QUEUE =================
async function checkAdminInboundPendingCount() {
  try {
    const res = await fetch("/api/inbound/shipments?limit=1");
    if (!res.ok) return;
    const data = await res.json();
    const count = data.pending_count || 0;

    const badge = document.getElementById("adminPendingBadgeCount");
    const btn = document.getElementById("adminInboundPendingBtn");
    if (badge) badge.textContent = count;
    if (btn) {
      const isAdmin = window.currentWarehouseUser && window.currentWarehouseUser.role === "ADMIN";
      if (isAdmin && count > 0) {
        btn.classList.remove("hidden");
      }
    }
  } catch (err) {
    console.error("Check pending count error:", err);
  }
}

function openAdminShipmentsModal() {
  loadAdminShipmentsList(window.activeAdminShipmentsTab);
  openModal("adminShipmentsModal");
}

function switchAdminShipmentsTab(tab) {
  window.activeAdminShipmentsTab = tab;
  const pBtn = document.getElementById("adminTabPendingBtn");
  const aBtn = document.getElementById("adminTabApprovedBtn");

  if (tab === "PENDING_APPROVAL") {
    if (pBtn) pBtn.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold transition bg-[#173456] text-white shadow-xs";
    if (aBtn) aBtn.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold transition text-[#2d4b68] hover:text-[#173456]";
  } else {
    if (aBtn) aBtn.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold transition bg-[#173456] text-white shadow-xs";
    if (pBtn) pBtn.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold transition text-[#2d4b68] hover:text-[#173456]";
  }
  loadAdminShipmentsList(tab);
}

async function loadAdminShipmentsList(status) {
  const container = document.getElementById("adminShipmentsListContainer");
  if (!container) return;
  container.innerHTML = `<div class="p-4 text-center text-xs text-slate-400 font-mono">Loading shipments...</div>`;

  try {
    const res = await fetch(`/api/inbound/shipments?status_filter=${status}&limit=50`);
    if (!res.ok) return;
    const data = await res.json();

    const pHead = document.getElementById("adminPendingCountHeader");
    const aHead = document.getElementById("adminApprovedCountHeader");
    if (pHead) pHead.textContent = data.pending_count || 0;
    if (aHead) aHead.textContent = data.approved_count || 0;

    const list = data.shipments || [];
    if (list.length === 0) {
      container.innerHTML = `<div class="p-4 text-center text-xs text-slate-400">No ${status === 'PENDING_APPROVAL' ? 'pending' : 'approved'} shipments found.</div>`;
      return;
    }

    container.innerHTML = list.map(s => `
      <div onclick="selectAdminShipmentDetail(${s.id})"
        class="p-3 bg-white hover:bg-blue-50/50 rounded-xl border border-slate-200 cursor-pointer transition shadow-2xs space-y-1">
        <div class="flex items-center justify-between">
          <span class="font-mono font-bold text-xs text-[#173456]">${escapeHtml(s.shipment_number)}</span>
          <span class="text-[9px] font-bold px-1.5 py-0.5 rounded ${s.status === 'APPROVED' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}">
            ${s.status}
          </span>
        </div>
        <div class="text-[11px] text-slate-600 flex items-center justify-between font-mono">
          <span>PO: ${escapeHtml(s.po_number || 'N/A')}</span>
          <span class="font-bold text-blue-700">${s.total_units.toLocaleString()} pcs</span>
        </div>
        <div class="text-[10px] text-slate-400 flex items-center justify-between">
          <span>${s.pallets_count} Pallet(s) &bull; ${s.total_boxes} Boxes</span>
          <span>${s.items_count} items</span>
        </div>
      </div>
    `).join("");

    if (list.length > 0) {
      selectAdminShipmentDetail(list[0].id);
    }
  } catch (err) {
    console.error("Load shipments error:", err);
  }
}

async function selectAdminShipmentDetail(shipmentId) {
  try {
    const res = await fetch(`/api/inbound/shipments/${shipmentId}`);
    if (!res.ok) return;
    const s = await res.json();
    window.activeAdminSelectedShipment = s;

    document.getElementById("adminDetailEmptyPlaceholder")?.classList.add("hidden");
    document.getElementById("adminDetailActiveContent")?.classList.remove("hidden");

    const numEl = document.getElementById("admDetShipmentNum");
    const stEl = document.getElementById("admDetStatusBadge");
    const poEl = document.getElementById("admDetPo");
    const venEl = document.getElementById("admDetVendor");
    const palEl = document.getElementById("admDetPallets");
    const subEl = document.getElementById("admDetSubmittedBy");

    if (numEl) numEl.textContent = s.shipment_number;
    if (stEl) {
      stEl.textContent = s.status;
      stEl.className = `text-[10px] font-mono font-bold px-2 py-0.5 rounded ${s.status === 'APPROVED' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`;
    }
    if (poEl) poEl.textContent = s.po_number || "N/A";
    if (venEl) venEl.textContent = s.carrier_vendor || "N/A";
    if (palEl) palEl.textContent = `${s.pallets_count} (${s.total_boxes} boxes, ${s.total_units.toLocaleString()} pcs)`;
    if (subEl) subEl.textContent = `${s.created_by} on ${new Date(s.created_at).toLocaleString()}`;

    // Document view buttons
    const pBtn = document.getElementById("admViewPackingListBtn");
    const iBtn = document.getElementById("admViewInvoiceBtn");
    if (pBtn) pBtn.style.display = s.packing_list_data ? "flex" : "none";
    if (iBtn) iBtn.style.display = s.commercial_invoice_data ? "flex" : "none";

    // Decision bar: hide approve button if already approved
    const decBar = document.getElementById("admDecisionBar");
    if (decBar) {
      decBar.style.display = s.status === "APPROVED" ? "none" : "flex";
    }

    // Render items
    const tbody = document.getElementById("admDetItemsTableBody");
    if (tbody) {
      tbody.innerHTML = (s.items || []).map(it => `
        <tr class="hover:bg-slate-50 transition">
          <td class="p-2 font-bold text-[#173456]">${escapeHtml(it.style)}</td>
          <td class="p-2 text-center text-slate-700">${escapeHtml(it.color)}</td>
          <td class="p-2 text-center font-bold text-slate-900">${escapeHtml(it.size)}</td>
          <td class="p-2 text-center">${it.box_count || 1}</td>
          <td class="p-2 text-center font-bold text-blue-700">${it.quantity.toLocaleString()}</td>
          <td class="p-2">
            <span class="inline-block px-2 py-0.5 rounded bg-blue-50 text-[#0070ba] font-bold border border-blue-200">
              📍 ${escapeHtml(it.location || 'Unassigned')}
            </span>
          </td>
        </tr>
      `).join("");
    }
  } catch (err) {
    console.error("Select shipment error:", err);
  }
}

// Admin Confirm & Commit to Live PostgreSQL Inventory
async function adminApproveActiveShipment() {
  if (!window.activeAdminSelectedShipment) return;
  const s = window.activeAdminSelectedShipment;

  if (!confirm(`Confirm and commit Shipment ${s.shipment_number} (${s.total_units.toLocaleString()} units) into live inventory?`)) {
    return;
  }

  const btn = document.getElementById("admConfirmApproveBtn");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span>⚙️</span><span>Committing to Inventory...</span>`;
  }

  try {
    const adminName = (window.currentWarehouseUser && window.currentWarehouseUser.full_name) || "Nandu (Admin)";
    const res = await fetch(`/api/inbound/shipments/${s.id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved_by: adminName })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Approval failed");
    }

    const resJson = await res.json();
    showToast(`🎉 ${resJson.message}`, "success");

    closeModal("adminShipmentsModal");

    // Live refresh dashboard or manager views if present
    if (typeof loadStats === "function") loadStats();
    if (typeof loadStylesList === "function") loadStylesList();
    if (typeof loadBatchStylesDetails === "function" && window.selectedStyles && window.selectedStyles.length > 0) {
      loadBatchStylesDetails();
    }
    if (typeof searchExistingLocations === "function") searchExistingLocations();
    if (typeof loadManagerExistingStylesList === "function") loadManagerExistingStylesList();

    checkAdminInboundPendingCount();
  } catch (err) {
    console.error("Approve error:", err);
    showToast("Error approving shipment: " + err.message, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<span>✅</span><span>Confirm & Commit to Live Inventory</span>`;
    }
  }
}

async function adminRejectActiveShipment() {
  if (!window.activeAdminSelectedShipment) return;
  const s = window.activeAdminSelectedShipment;
  const reason = prompt(`Enter revision notes / reason for rejecting ${s.shipment_number}:`, "Box count does not match commercial invoice");
  if (!reason) return;

  try {
    const res = await fetch(`/api/inbound/shipments/${s.id}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rejected_by: (window.currentWarehouseUser && window.currentWarehouseUser.full_name) || "Nandu (Admin)",
        reason: reason
      })
    });

    if (!res.ok) throw new Error("Rejection failed");
    showToast(`Shipment ${s.shipment_number} rejected. Notes sent to floor manager.`, "error");
    loadAdminShipmentsList(window.activeAdminShipmentsTab);
    checkAdminInboundPendingCount();
  } catch (err) {
    showToast("Error rejecting shipment: " + err.message, "error");
  }
}

// ================= 7. DOCUMENT PREVIEW LIGHTBOX =================
function openDocPreviewLightbox() {
  if (window.currentInboundDraft.packing_list_data) {
    previewDocInLightbox("PACKING_LIST");
  } else if (window.currentInboundDraft.commercial_invoice_data) {
    previewDocInLightbox("INVOICE");
  } else {
    showToast("No documents currently attached to this shipment.", "error");
  }
}

function previewDocInLightbox(docType) {
  const img = document.getElementById("lightboxImg");
  const title = document.getElementById("lightboxDocTitle");
  const noImg = document.getElementById("lightboxNoImgMsg");

  let dataUri = "";
  let docName = "";

  if (window.activeAdminSelectedShipment) {
    dataUri = docType === "PACKING_LIST" ? window.activeAdminSelectedShipment.packing_list_data : window.activeAdminSelectedShipment.commercial_invoice_data;
    docName = docType === "PACKING_LIST" ? (window.activeAdminSelectedShipment.packing_list_filename || "Packing List") : (window.activeAdminSelectedShipment.commercial_invoice_filename || "Commercial Invoice");
  } else {
    dataUri = docType === "PACKING_LIST" ? window.currentInboundDraft.packing_list_data : window.currentInboundDraft.commercial_invoice_data;
    docName = docType === "PACKING_LIST" ? (window.currentInboundDraft.packing_list_filename || "Packing List") : (window.currentInboundDraft.commercial_invoice_filename || "Commercial Invoice");
  }

  if (title) title.textContent = `Attached ${docName}`;

  if (dataUri && dataUri.startsWith("data:image")) {
    if (img) {
      img.src = dataUri;
      img.classList.remove("hidden");
    }
    if (noImg) noImg.classList.add("hidden");
  } else {
    if (img) img.classList.add("hidden");
    if (noImg) noImg.classList.remove("hidden");
  }

  openModal("documentPreviewLightbox");
}

// ================= 8. MANUAL DIRECT RECEIVING MODAL WORKFLOW =================
function openReceivingModal() {
  const current = (window.selectedStyles && window.selectedStyles.length > 0) ? window.selectedStyles[0] : "";
  const styleInput = document.getElementById("rcvStyleInput");
  if (styleInput && !styleInput.value && current) {
    styleInput.value = current;
  }

  const staffInput = document.getElementById("rcvStaffInput");
  if (staffInput && window.currentWarehouseUser && window.currentWarehouseUser.full_name) {
    staffInput.value = window.currentWarehouseUser.full_name;
  }

  updateReceivingLocationPreview();
  openModal("receivingModal");
}

function switchReceivingZone(part) {
  const partInput = document.getElementById("rcvWarehousePart");
  const p1Btn = document.getElementById("rcvPart1Btn");
  const p2Btn = document.getElementById("rcvPart2Btn");
  const lineCol = document.getElementById("rcvLineCol");
  const rowCol = document.getElementById("rcvRowCol");
  const zoneTitle = document.getElementById("rcvLocZoneTitle");
  const brandSelect = document.getElementById("rcvBrandSelect");

  if (!partInput) return;
  partInput.value = part;

  if (part === "PART_1") {
    if (p1Btn) p1Btn.className = "py-2 px-3 rounded-lg bg-[#173456] text-white shadow-xs flex items-center justify-center gap-1.5 transition";
    if (p2Btn) p2Btn.className = "py-2 px-3 rounded-lg text-[#2d4b68] hover:text-[#173456] flex items-center justify-center gap-1.5 transition";
    if (lineCol) lineCol.classList.remove("hidden");
    if (rowCol) rowCol.classList.add("hidden");
    if (zoneTitle) zoneTitle.textContent = "Part 1 Shelf Location Coordinates (Allbirds Lines 1–14)";
    if (brandSelect && brandSelect.value !== "ALLBIRDS") brandSelect.value = "ALLBIRDS";
  } else {
    if (p2Btn) p2Btn.className = "py-2 px-3 rounded-lg bg-[#173456] text-white shadow-xs flex items-center justify-center gap-1.5 transition";
    if (p1Btn) p1Btn.className = "py-2 px-3 rounded-lg text-[#2d4b68] hover:text-[#173456] flex items-center justify-center gap-1.5 transition";
    if (lineCol) lineCol.classList.add("hidden");
    if (rowCol) rowCol.classList.remove("hidden");
    if (zoneTitle) zoneTitle.textContent = "Part 2 Shelf Location Coordinates (Rows 1–15 / Wall)";
    if (brandSelect && brandSelect.value === "ALLBIRDS") brandSelect.value = "VON DUTCH";
  }
  updateReceivingLocationPreview();
}

function updateReceivingLocationPreview() {
  const partInput = document.getElementById("rcvWarehousePart");
  const part = partInput ? partInput.value : "PART_1";
  const line = (document.getElementById("rcvLineInput")?.value || "").trim();
  const row = (document.getElementById("rcvRowInput")?.value || "").trim();
  const sec = (document.getElementById("rcvSectionInput")?.value || "").trim();
  const lvl = (document.getElementById("rcvLevelInput")?.value || "").trim();
  const box = (document.getElementById("rcvBoxInput")?.value || "").trim();
  const preview = document.getElementById("rcvLocationPreview");

  const parts = [];
  if (part === "PART_1") {
    if (line) parts.push(`Line ${line}`);
  } else {
    if (row) parts.push(`Row ${row}`);
  }
  if (sec) parts.push(`Sec ${sec}`);
  if (lvl) parts.push(`Lvl ${lvl}`);
  if (box) parts.push(`Box ${box}`);

  if (preview) {
    preview.textContent = parts.length > 0 ? parts.join(" • ") : "📍 Unassigned";
  }
}

function handleReceivingStyleInput(val) {
  const query = (val || "").trim().toUpperCase();
  const dropdown = document.getElementById("rcvStyleSuggestions");
  if (!dropdown) return;

  const styles = (typeof window.allStylesList !== "undefined" && window.allStylesList) ? window.allStylesList : [];
  if (!query || styles.length === 0) {
    dropdown.innerHTML = "";
    dropdown.classList.add("hidden");
    return;
  }

  const qNorm = query.replace(/\s+/g, "");
  const matches = styles.filter(s => {
    const stUpper = (s.style || "").toUpperCase();
    return stUpper.includes(query) || stUpper.replace(/\s+/g, "").includes(qNorm);
  }).slice(0, 8);

  if (matches.length === 0) {
    dropdown.innerHTML = `<div class="p-2.5 text-xs text-slate-500 font-mono">New Style SKU "${escapeHtml(query)}" (Will be created)</div>`;
    dropdown.classList.remove("hidden");
    return;
  }

  dropdown.innerHTML = matches.map(s => `
    <div onclick="selectReceivingStyle('${escapeHtml(s.style)}')"
      class="p-2.5 hover:bg-[#f0f7ff] cursor-pointer flex items-center justify-between text-xs transition">
      <span class="font-mono font-bold text-[#173456]">${escapeHtml(s.style)}</span>
      <span class="text-slate-500 font-mono">${s.total_quantity.toLocaleString()} pcs • ${s.location_count} locs</span>
    </div>
  `).join("");
  dropdown.classList.remove("hidden");
}

function selectReceivingStyle(sku) {
  const input = document.getElementById("rcvStyleInput");
  if (input) input.value = sku;
  const dropdown = document.getElementById("rcvStyleSuggestions");
  if (dropdown) dropdown.classList.add("hidden");

  // Auto-detect brand & warehouse part from SKU prefix
  const upper = sku.toUpperCase();
  if (upper.startsWith("VD") || upper.startsWith("VO") || upper.startsWith("ED") || upper.startsWith("ROW")) {
    switchReceivingZone("PART_2");
    const brandSel = document.getElementById("rcvBrandSelect");
    if (brandSel) {
      if (upper.startsWith("VD")) brandSel.value = "VON DUTCH";
      else if (upper.startsWith("VO")) brandSel.value = "VALENTINO";
      else if (upper.startsWith("ED")) brandSel.value = "ED HARDY";
    }
  } else {
    switchReceivingZone("PART_1");
  }
}

async function handleReceivingSubmit(e) {
  e.preventDefault();
  const submitBtn = document.getElementById("rcvSubmitBtn");
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<span>⏳</span><span>Processing Inbound...</span>`;
  }

  const style = (document.getElementById("rcvStyleInput")?.value || "").trim().toUpperCase();
  const color = (document.getElementById("rcvColorInput")?.value || "STANDARD").trim().toUpperCase();
  const size = (document.getElementById("rcvSizeInput")?.value || "OS").trim().toUpperCase();
  const brand = document.getElementById("rcvBrandSelect")?.value || "ALLBIRDS";
  const part = document.getElementById("rcvWarehousePart")?.value || "PART_1";
  const line = (document.getElementById("rcvLineInput")?.value || "").trim();
  const row_pos = (document.getElementById("rcvRowInput")?.value || "").trim();
  const section = (document.getElementById("rcvSectionInput")?.value || "").trim();
  const level = (document.getElementById("rcvLevelInput")?.value || "").trim();
  const box_num = (document.getElementById("rcvBoxInput")?.value || "").trim();
  const pcs_per_box = parseInt(document.getElementById("rcvPcsBoxInput")?.value, 10) || null;
  const qty = parseInt(document.getElementById("rcvQuantityInput")?.value, 10);
  const po_number = (document.getElementById("rcvPoInput")?.value || "").trim();
  const staff_name = (document.getElementById("rcvStaffInput")?.value || "Warehouse Manager").trim();

  if (!style) {
    showToast("Style code is required", "error");
    if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = `<span>📥</span><span>Check In & Receive Stock</span>`; }
    return;
  }
  if (isNaN(qty) || qty <= 0) {
    showToast("Received quantity must be greater than 0", "error");
    if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = `<span>📥</span><span>Check In & Receive Stock</span>`; }
    return;
  }

  const payload = {
    style: style,
    brand: brand,
    warehouse_part: part,
    color: color,
    size: size,
    line: part === "PART_1" ? (line || null) : null,
    row_pos: part === "PART_2" ? (row_pos || null) : null,
    section: section || null,
    level: level || null,
    box_num: box_num || null,
    pcs_per_box: pcs_per_box,
    quantity: qty,
    po_number: po_number || null,
    notes: po_number ? `Inbound PO: ${po_number}` : "Manager Inbound Receiving",
    staff_name: staff_name
  };

  try {
    const res = await fetch("/api/receiving", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail || "Receiving failed", "error");
      if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = `<span>📥</span><span>Check In & Receive Stock</span>`; }
      return;
    }

    closeModal("receivingModal");
    showToast(`📥 Successfully received ${qty} pcs of ${style}!`, "success");

    // Reset form fields
    document.getElementById("receivingForm")?.reset();
    const cInput = document.getElementById("rcvColorInput");
    const qInput = document.getElementById("rcvQuantityInput");
    if (cInput) cInput.value = "STANDARD";
    if (qInput) qInput.value = "15";

    // Auto-select or refresh if functions exist
    if (typeof addStyleToSelection === "function") addStyleToSelection(style);
    if (typeof loadStats === "function") loadStats();
    if (typeof loadStylesList === "function") loadStylesList();
    if (typeof searchExistingLocations === "function") searchExistingLocations();
    if (typeof loadManagerExistingStylesList === "function") loadManagerExistingStylesList();
  } catch (err) {
    console.error("Receiving error:", err);
    showToast("Network error submitting receiving", "error");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<span>📥</span><span>Check In & Receive Stock</span>`;
    }
  }
}

// Auto-check pending count on initial load
document.addEventListener("DOMContentLoaded", () => {
  checkAdminInboundPendingCount();
});
