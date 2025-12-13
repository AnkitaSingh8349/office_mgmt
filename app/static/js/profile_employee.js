// app/static/js/profile_employee.js

async function apiGet(path) {
  const res = await fetch(path, { credentials: 'include' });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

async function apiPut(path, body) {
  const res = await fetch(path, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`PUT ${path} ${res.status} ${txt}`);
  }
  return res.json();
}

function setFormDisabled(formEl, disable = true) {
  Array.from(formEl.elements).forEach(el => {
    // don't disable tabs or buttons with data-bs attrs
    if (el.dataset && el.dataset.bsToggle) return;
    el.disabled = disable;
  });
}

function fillForm(formEl, data) {
  for (const key in data) {
    const f = formEl.elements.namedItem(key);
    if (!f) continue;
    // input, textarea, select
    if (f.length && f[0] && f[0].tagName === 'INPUT') {
      // radio/checkbox array ignored for now
      f.value = data[key] ?? '';
    } else {
      f.value = data[key] ?? '';
    }
  }
}

function computeBar(pct) {
  const bar = document.getElementById('dashBar');
  const label = document.getElementById('dashPercent');
  if (!bar || !label) return;
  bar.style.width = `${pct}%`;
  bar.textContent = `${pct}%`;
  label.textContent = `${pct}%`;
}

function showMessage(msg, ok = true) {
  const el = document.getElementById('saveMessage');
  if (!el) return;
  el.textContent = msg;
  el.className = ok ? 'text-success mb-3' : 'text-danger mb-3';
}

document.addEventListener('DOMContentLoaded', async () => {
  const profileBtn = document.getElementById('profileBtn');
  const form = document.getElementById('profileForm');
  const saveBtn = document.getElementById('saveProfileBtn');
  const completionInfo = document.getElementById('completionInfo');

  // load user & profile
  let me = null, profile = null;
  try {
    me = await apiGet('/me');            // returns {id, role, name...} — adjust if your endpoint is different
  } catch (e) {
    console.warn('Could not fetch /me', e);
  }

  try {
    profile = await apiGet('/me/profile'); // { completion_percent, ... }
  } catch (e) {
    console.warn('Could not fetch /me/profile', e);
  }

  // show button only if logged-in
  if (profileBtn && me) {
    profileBtn.classList.remove('d-none');
    profileBtn.addEventListener('click', () => {
      const modal = new bootstrap.Modal(document.getElementById('profileModal'));
      modal.show();
    });
  }

  // fill form & set read/write based on role
  if (form && profile) {
    fillForm(form, profile);
    computeBar(profile.completion_percent ?? 0);
    if (completionInfo) completionInfo.textContent = `Completion: ${profile.completion_percent ?? 0}%`;

    // Admin: read-only
    const isAdmin = (me && me.role === 'admin');
    if (isAdmin) {
      setFormDisabled(form, true);
      if (saveBtn) saveBtn.style.display = 'none';
      showMessage('You are viewing this profile as admin (read-only).', true);
    } else {
      // employee can edit
      setFormDisabled(form, false);
      if (saveBtn) saveBtn.style.display = '';
      showMessage('');
    }
  }

  // submit handler (employee)
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    showMessage('Saving...', true);
    // prepare partial payload: include only form fields that exist and non-empty
    const fd = new FormData(form);
    const payload = {};
    for (const [k, v] of fd.entries()) {
      // only send non-empty values (you can change this)
      if (v !== null && v !== undefined && String(v).trim() !== '') payload[k] = v;
    }

    try {
      const res = await apiPut('/me/profile', payload);
      computeBar(res.completion_percent ?? 0);
      if (completionInfo) completionInfo.textContent = `Completion: ${res.completion_percent ?? 0}%`;
      showMessage(res.completion_percent === 100 ? '🎉 Profile 100% completed!' : 'Saved successfully.', true);
    } catch (err) {
      console.error(err);
      showMessage('Error saving profile — see console', false);
    }
  });
});
