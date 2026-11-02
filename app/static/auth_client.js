// Shared Authentication & Admin User Access Control Bar for Warehouse OS
window.currentWarehouseUser = null;

async function initWarehouseAuth() {
  try {
    const res = await fetch("/api/auth/me");
    if (res.status === 401 || res.status === 403) {
      window.location.href = "/login";
      return;
    }
    if (!res.ok) return;
    const data = await res.json();
    window.currentWarehouseUser = data.user;
    const userRole = (data.user && data.user.role) ? data.user.role.toUpperCase() : "";
    const isAdmin = userRole === "ADMIN";
    const isManager = userRole === "MANAGER" || isAdmin;

    document.querySelectorAll(".admin-only-control").forEach(el => {
      if (isAdmin) {
        el.classList.remove("hidden");
      } else {
        el.classList.add("hidden");
      }
    });

    document.querySelectorAll(".manager-control").forEach(el => {
      if (isManager || !data.user) {
        el.classList.remove("hidden");
      } else {
        el.classList.add("hidden");
      }
    });

    // Auto-fill staff name on Inbound Receiving modal if present
    const rcvStaff = document.getElementById("rcvStaffInput");
    if (rcvStaff && data.user && data.user.full_name) {
      rcvStaff.value = data.user.full_name;
    }

    // Auto-fill staff name input on /manage if present
    const staffInput = document.getElementById("sheetStaffInput");
    if (staffInput && data.user && data.user.full_name) {
      staffInput.value = data.user.full_name;
    }

    if (typeof renderFilteredRows === 'function') renderFilteredRows();
    renderAuthHeaderControls(data);
    injectAccessControlModal();
  } catch (err) {
    console.error("Auth check error:", err);
  }
}

function renderAuthHeaderControls(data) {
  const user = data.user;
  if (!user) return;

  let bar = document.getElementById("warehouseAuthUserBar");
  if (!bar) {
    const header = document.querySelector("header");
    if (!header) return;
    bar = document.createElement("div");
    bar.id = "warehouseAuthUserBar";
    bar.className = "flex items-center gap-2 text-xs";
    header.appendChild(bar);
  }

  const onlineCount = data.online_users_count || 1;

  bar.innerHTML = `
    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#0e233b] border border-[#23456e] text-blue-100 font-mono text-xs">
      <span>👤</span>
      <strong class="text-white">${escapeAuthHtml(user.full_name)}</strong>
      <span class="text-[10px] px-1.5 py-0.5 rounded bg-[#1d4370] text-blue-200 font-bold">${escapeAuthHtml(user.role)}</span>
    </span>
    <button onclick="logoutWarehouseUser()" class="bg-[#1a385c] hover:bg-red-800 text-blue-100 hover:text-white border border-[#2b4d75] hover:border-red-600 px-2.5 py-1.5 rounded-lg text-xs font-semibold transition">
      Logout
    </button>
  `;
}

async function logoutWarehouseUser() {
  await fetch("/api/auth/logout", { method: "POST" });
  window.location.href = "/login";
}

function injectAccessControlModal() {
  if (document.getElementById("userAccessModal")) return;
  const div = document.createElement("div");
  div.id = "userAccessModal";
  div.className = "hidden fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4";
  div.innerHTML = `
    <div class="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-4xl p-6 shadow-2xl space-y-5 max-h-[90vh] flex flex-col">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <div>
          <h3 class="text-lg font-black text-white flex items-center gap-2">
            <span>👥</span> User Access Control &amp; Team Accounts (Admin Only)
          </h3>
          <p class="text-xs text-slate-400 mt-0.5">
            Approve sign-up requests, create accounts for your Manager or Floor Leads, assign Part 1 / Part 2 zones, and see who is online right now.
          </p>
        </div>
        <button onclick="closeUserAccessModal()" class="text-slate-400 hover:text-white text-lg">✕</button>
      </div>

      <!-- Create / Give Access directly form -->
      <form onsubmit="handleAdminCreateUser(event)" class="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-3">
        <div class="text-xs font-black text-emerald-400 uppercase tracking-wider">➕ Give Direct Access (Create Approved User Account)</div>
        <div class="grid grid-cols-1 sm:grid-cols-6 gap-2.5 items-end">
          <div>
            <label class="block text-[10px] text-slate-400 uppercase mb-1">Full Name *</label>
            <input type="text" id="admNewName" required placeholder="e.g. Lead 1 - Allbirds"
              class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white" />
          </div>
          <div>
            <label class="block text-[10px] text-slate-400 uppercase mb-1">Username / Email *</label>
            <input type="text" id="admNewUser" required placeholder="e.g. lead1"
              class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white font-mono" />
          </div>
          <div>
            <label class="block text-[10px] text-slate-400 uppercase mb-1">Password *</label>
            <input type="text" id="admNewPass" required placeholder="e.g. Allbirds123"
              class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-amber-300 font-mono" />
          </div>
          <div>
            <label class="block text-[10px] text-slate-400 uppercase mb-1">Role</label>
            <select id="admNewRole" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white">
              <option value="MANAGER">Manager</option>
              <option value="PART_1_LEAD">Part 1 Lead (Allbirds)</option>
              <option value="PART_2_LEAD">Part 2 Lead (VD/Valentino)</option>
              <option value="STAFF">Warehouse Staff</option>
              <option value="ADMIN">Admin</option>
            </select>
          </div>
          <div>
            <label class="block text-[10px] text-slate-400 uppercase mb-1">Assigned Zone</label>
            <select id="admNewZone" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white">
              <option value="ALL_ZONES">All Zones</option>
              <option value="PART_1_ALLBIRDS">Part 1: Allbirds (Lines 1–14)</option>
              <option value="PART_2_VD_VALENTINO">Part 2: VD &amp; Valentino (Rows 1–14)</option>
            </select>
          </div>
          <div>
            <button type="submit" class="w-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-black px-3 py-1.5 rounded-lg text-xs transition shadow">
              + Create &amp; Grant Access
            </button>
          </div>
        </div>
      </form>

      <!-- Existing & Pending Users Table -->
      <div class="flex-1 overflow-y-auto border border-slate-800 rounded-xl">
        <table class="w-full text-left border-collapse text-xs">
          <thead class="bg-slate-950 sticky top-0 border-b border-slate-800 text-[10px] font-bold uppercase text-slate-400">
            <tr>
              <th class="py-2.5 px-3">User / Login</th>
              <th class="py-2.5 px-3">Role &amp; Assigned Warehouse Zone</th>
              <th class="py-2.5 px-3 text-center">Access Status</th>
              <th class="py-2.5 px-3 text-center">Online / Last Seen</th>
              <th class="py-2.5 px-3 text-right">Admin Actions</th>
            </tr>
          </thead>
          <tbody id="adminUsersTableBody" class="divide-y divide-slate-800/60"></tbody>
        </table>
      </div>
    </div>
  `;
  document.body.appendChild(div);
}

function openUserAccessModal() {
  const modal = document.getElementById("userAccessModal");
  if (modal) {
    modal.classList.remove("hidden");
    loadAdminUsersList();
  }
}

function closeUserAccessModal() {
  const modal = document.getElementById("userAccessModal");
  if (modal) modal.classList.add("hidden");
  initWarehouseAuth();
}

async function loadAdminUsersList() {
  const tbody = document.getElementById("adminUsersTableBody");
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="5" class="text-center py-6 text-slate-400">Loading users...</td></tr>';

  try {
    const res = await fetch("/api/admin/users");
    const users = await res.json();
    tbody.innerHTML = users.map(u => {
      let statusBadge = "";
      if (u.is_approved === 1) {
        statusBadge = '<span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold text-[10px]">✅ ACTIVE ACCESS</span>';
      } else if (u.is_approved === 0) {
        statusBadge = '<span class="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-black text-[10px] animate-pulse">⏳ PENDING APPROVAL</span>';
      } else {
        statusBadge = '<span class="px-2 py-0.5 rounded bg-red-500/20 text-red-300 border border-red-500/40 font-bold text-[10px]">🚫 REVOKED</span>';
      }

      const onlineBadge = u.is_online
        ? '<span class="inline-flex items-center gap-1 text-emerald-400 font-bold"><span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>Online Now</span>'
        : `<span class="text-slate-500 font-mono text-[11px]">${escapeAuthHtml(u.last_seen_at || 'Never')}</span>`;

      const isPrimaryAdmin = u.username === "nandu";
      const actionBtns = isPrimaryAdmin
        ? '<span class="text-[10px] text-slate-500 font-mono">Primary Owner</span>'
        : `
          <div class="inline-flex items-center gap-1.5">
            ${u.is_approved !== 1 ? `<button onclick="updateUserAccessStatus(${u.id}, 1)" class="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-black px-2.5 py-1 rounded text-[11px]">✅ Grant Access</button>` : ''}
            ${u.is_approved === 1 ? `<button onclick="updateUserAccessStatus(${u.id}, -1)" class="bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 font-bold px-2.5 py-1 rounded text-[11px]">Revoke</button>` : ''}
            <button onclick="deleteUserAccount(${u.id})" class="bg-red-500/15 hover:bg-red-500/30 text-red-300 border border-red-500/30 font-bold px-2 py-1 rounded text-[11px]">Delete</button>
          </div>
        `;

      return `
        <tr class="hover:bg-slate-800/40">
          <td class="py-2.5 px-3">
            <div class="font-bold text-white">${escapeAuthHtml(u.full_name)}</div>
            <div class="text-[11px] font-mono text-amber-400">@${escapeAuthHtml(u.username)} ${u.email ? '• ' + escapeAuthHtml(u.email) : ''}</div>
          </td>
          <td class="py-2.5 px-3 font-mono">
            <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-200 font-bold text-[10px]">${escapeAuthHtml(u.role)}</span>
            <span class="text-[11px] text-slate-400 ml-1">${escapeAuthHtml(u.assigned_zone)}</span>
          </td>
          <td class="py-2.5 px-3 text-center">${statusBadge}</td>
          <td class="py-2.5 px-3 text-center">${onlineBadge}</td>
          <td class="py-2.5 px-3 text-right">${actionBtns}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center py-6 text-red-400">Failed to load users.</td></tr>';
  }
}

async function handleAdminCreateUser(e) {
  e.preventDefault();
  const full_name = document.getElementById("admNewName").value.trim();
  const username = document.getElementById("admNewUser").value.trim();
  const password = document.getElementById("admNewPass").value;
  const role = document.getElementById("admNewRole").value;
  const assigned_zone = document.getElementById("admNewZone").value;

  const res = await fetch("/api/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ full_name, username, password, role, assigned_zone })
  });
  const data = await res.json();
  if (!res.ok) {
    alert(data.detail || "Failed to create user");
    return;
  }
  document.getElementById("admNewName").value = "";
  document.getElementById("admNewUser").value = "";
  document.getElementById("admNewPass").value = "";
  loadAdminUsersList();
}

async function updateUserAccessStatus(userId, is_approved) {
  await fetch(`/api/admin/users/${userId}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_approved })
  });
  loadAdminUsersList();
}

async function deleteUserAccount(userId) {
  if (!confirm("Delete this user account?")) return;
  await fetch(`/api/admin/users/${userId}`, { method: "DELETE" });
  loadAdminUsersList();
}

function escapeAuthHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initWarehouseAuth);
} else {
  initWarehouseAuth();
}
