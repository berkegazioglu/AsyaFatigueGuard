import { useState } from "react";
import { api, authedUrl } from "../api";

/**
 * Zorunlu sürücü isimlendirme penceresi.
 * Kapatma düğmesi yoktur; isim verilmeden panel kullanılamaz.
 */
export default function DriverNameModal({ driver, onNamed }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(`/api/drivers/${driver.id}/name`, {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      onNamed();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h2>👤 Sürücüyü İsimlendirin</h2>
        <p className="muted">
          {driver.equipment ? `${driver.equipment} ekipmanındaki ` : ""}
          kameradan {driver.photos.length} fotoğraf yakalandı. Devam etmek için
          bu sürücüye bir isim vermeniz <b>zorunludur</b>.
        </p>

        <div className="photo-grid">
          {driver.photos.map((p) => (
            <img key={p} src={authedUrl(p)} alt="sürücü" />
          ))}
        </div>

        <form onSubmit={submit} className="name-form">
          <input
            placeholder="Sürücü adı soyadı"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            required
            minLength={3}
          />
          <button disabled={busy || name.trim().length < 3}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </form>
        {error && <div className="login-error">{error}</div>}
      </div>
    </div>
  );
}
