// Location lookup: /loc/<code> (from a label QR) or a scanner gun / typed code. Read only.
// Accepts a plain code or a link ending with the code. All values are shown with textContent.

function codeFrom(raw) {
  const v = String(raw || "").trim().replace(/\/+$/, "");
  return v.split("/").pop().trim().toUpperCase();
}

function cell(tag, cls, txt) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  e.textContent = txt === null || txt === undefined ? "" : String(txt);
  return e;
}

async function lookup(raw) {
  const code = codeFrom(raw);
  const msg = document.getElementById("message");
  const result = document.getElementById("result");
  msg.hidden = true;
  if (!code) return;
  if (window.location.pathname !== `/loc/${code}`) history.replaceState(null, "", `/loc/${encodeURIComponent(code)}`);
  try {
    const res = await fetch(`/api/locations/lookup?q=${encodeURIComponent(code)}`);
    const data = await res.json();
    if (!res.ok) {
      result.hidden = true;
      msg.textContent = data.detail || "Lookup failed";
      msg.hidden = false;
      return;
    }
    document.getElementById("locCode").textContent = data.code;
    const state = document.getElementById("locState");
    state.textContent = data.active ? "Active" : "Deactivated";
    state.className = "text-xs font-bold uppercase " + (data.active ? "text-emerald-400" : "text-red-400");
    document.getElementById("locDesc").textContent = data.description;
    document.getElementById("locTotals").textContent = data.rows
      ? `${data.pieces} pcs in ${data.rows} row(s)` : "No active stock rows at this location.";
    const tbody = document.getElementById("locItems");
    tbody.textContent = "";
    data.items.forEach(i => {
      const tr = cell("tr", "border-t border-slate-800" + (i.quantity === 0 ? " text-slate-500" : ""));
      tr.appendChild(cell("td", "py-1 pr-3 font-mono", i.style));
      tr.appendChild(cell("td", "pr-3", i.color));
      tr.appendChild(cell("td", "pr-3", i.size));
      tr.appendChild(cell("td", "text-right pr-3", i.pcs_per_box));
      tr.appendChild(cell("td", "text-right font-bold", i.quantity));
      tbody.appendChild(tr);
    });
    result.hidden = false;
  } catch (e) {
    msg.textContent = "Lookup failed";
    msg.hidden = false;
  }
}

document.getElementById("scanForm").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const input = document.getElementById("scanInput");
  lookup(input.value);
  input.value = "";
  input.focus();
});

const fromPath = window.location.pathname.replace(/^\/loc\/?/, "");
if (fromPath) lookup(decodeURIComponent(fromPath));
