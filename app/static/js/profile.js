// app/static/js/profile.js
// role detection, load percent, open modal, save profile
async function whoAmI() {
  const res = await fetch('/me', { credentials: 'include' });
  if (!res.ok) return null;
  return res.json();
}

async function loadProfilePercent() {
  const res = await fetch('/me/profile', { credentials: 'include' });
  if (!res.ok) return;
  const d = await res.json();
  const pct = d.completion_percent ?? 0;
  const dashBar = document.getElementById('dashBar');
  const dashPercent = document.getElementById('dashPercent');
  if (dashBar) { dashBar.style.width = pct + '%'; dashBar.textContent = pct + '%'; }
  if (dashPercent) dashPercent.textContent = pct + '%';
  return d;
}

document.addEventListener('DOMContentLoaded', async () => {
  const me = await whoAmI();
  if (!me) return;
  // show employee or admin UI
  if (me.role === 'employee') {
    const btn = document.getElementById('profileBtn');
    if (btn) btn.classList.remove('d-none');
    btn && btn.addEventListener('click', openProfileModal);
  } else if (me.role === 'admin') {
    const aBtn = document.getElementById('adminBtn');
    if (aBtn) aBtn.classList.remove('d-none');
  }
  await loadProfilePercent();
});

// Open modal, populate fields
async function openProfileModal() {
  const data = await loadProfilePercent();
  // fill fields if present
  const form = document.getElementById('profileForm');
  if (!form) return;
  const fields = ['first_name','last_name','email','personal_phone','birthday','present_address','permanent_address','bank_account_no'];
  fields.forEach(key => {
    const el = form.elements.namedItem(key);
    if (el) {
      if (key === 'birthday' && data && data[key]) {
        // convert date to YYYY-MM-DD
        el.value = data[key].split('T')[0];
      } else {
        el.value = (data && data[key]) ? data[key] : '';
      }
    }
  });
  const modalEl = document.getElementById('profileModal');
  const bsModal = new bootstrap.Modal(modalEl);
  bsModal.show();
}

// Save profile
document.addEventListener('submit', async (e) => {
  if (e.target && e.target.id === 'profileForm') {
    e.preventDefault();
    const form = e.target;
    const payload = Object.fromEntries(new FormData(form).entries());
    // normalize empty -> null
    Object.keys(payload).forEach(k => { if (payload[k] === '') payload[k] = null; });
    const res = await fetch('/me/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload)
    });
    const saveMessage = document.getElementById('saveMessage');
    if (res.ok) {
      const updated = await res.json();
      const pct = updated.completion_percent ?? 0;
      const dashBar = document.getElementById('dashBar');
      const dashPercent = document.getElementById('dashPercent');
      if (dashBar) { dashBar.style.width = pct + '%'; dashBar.textContent = pct + '%'; }
      if (dashPercent) dashPercent.textContent = pct + '%';
      if (saveMessage) saveMessage.textContent = pct === 100 ? 'You completed 100% of your profile 🎉' : `Saved — ${pct}% complete`;
      if (pct === 100) {
        // close modal after short delay
        setTimeout(()=> { const modalEl = document.getElementById('profileModal'); bootstrap.Modal.getInstance(modalEl).hide(); }, 800);
      }
    } else {
      if (saveMessage) saveMessage.textContent = 'Error saving profile';
    }
  }
});
