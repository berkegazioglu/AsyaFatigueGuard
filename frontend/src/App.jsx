import { useEffect, useState } from "react";
import { api, getToken } from "./api";
import Login from "./Login";
import Dashboard from "./Dashboard";

export default function App() {
  // null = kontrol ediliyor, false = giriş gerekli, true = girişli
  const [authed, setAuthed] = useState(null);

  useEffect(() => {
    const onLogout = () => setAuthed(false);
    window.addEventListener("afg-logout", onLogout);

    if (!getToken()) {
      setAuthed(false);
    } else {
      api("/api/me")
        .then(() => setAuthed(true))
        .catch(() => setAuthed(false));
    }
    return () => window.removeEventListener("afg-logout", onLogout);
  }, []);

  if (authed === null) {
    return <div className="boot">Yükleniyor…</div>;
  }
  return authed ? (
    <Dashboard onLogout={() => setAuthed(false)} />
  ) : (
    <Login onLogin={() => setAuthed(true)} />
  );
}
