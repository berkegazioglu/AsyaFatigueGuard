// API istemcisi: token yönetimi + hata çevirisi
let token = localStorage.getItem("afg_token") || null;

export function getToken() {
  return token;
}

export function setToken(t) {
  token = t;
  if (t) localStorage.setItem("afg_token", t);
  else localStorage.removeItem("afg_token");
}

export async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
  });
  if (res.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event("afg-logout"));
    throw new Error("Oturum süresi doldu");
  }
  if (!res.ok) {
    const detail = await res.json().then((d) => d.detail).catch(() => null);
    throw new Error(detail || `Hata: ${res.status}`);
  }
  return res.json();
}

// <img> etiketleri header gönderemez; token'ı sorgu parametresiyle ekle
export function authedUrl(path) {
  return `${path}${path.includes("?") ? "&" : "?"}t=${token}`;
}
