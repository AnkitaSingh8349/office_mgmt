async function fetchJson(url) {
  const token = localStorage.getItem("token");
  if (!token) { 
    window.location.href = "/auth/login"; 
    return; 
  }

  const res = await fetch(url, { 
    headers: { "Authorization": "Bearer " + token }
  });

  if (res.status === 401) {
    localStorage.removeItem("token");
    window.location.href = "/auth/login";
    return;
  }

  if (!res.ok) {
    let t = {};
    try { t = await res.json(); } catch {}
    throw new Error(t.detail || t.error || "Error");
  }
  
  return res.json();
}
