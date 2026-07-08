import { useState } from "react";
import { api } from "../api";

/**
 * Zorunlu ekipman eşleştirme penceresi.
 * Kamera bir ekipmana (ör. TTC59) eşlenmeden panel kullanılamaz.
 */
export default function EquipmentModal({ camera, identity, onPaired }) {
  const [equipment, setEquipment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/equipment", {
        method: "POST",
        body: JSON.stringify({
          identifier: identity.identifier,
          equipment,
          camera_id: camera.id,
        }),
      });
      onPaired();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h2>🔗 Ekipman Eşleştirmesi Gerekli</h2>
        <p className="muted">
          <b>{camera.name}</b> kamerası henüz bir ekipmana eşlenmedi. Devam
          etmek için kameranın monteli olduğu ekipmanı girmeniz{" "}
          <b>zorunludur</b>.
        </p>

        <div className="id-box">
          {identity.kind === "ip" ? (
            <>
              <div>
                <span className="muted">MAC adresi:</span>{" "}
                <code>{identity.mac || "algılanamadı"}</code>
              </div>
              <div>
                <span className="muted">IP:</span> <code>{identity.ip}</code>
              </div>
            </>
          ) : (
            <>
              <div>
                <span className="muted">Donanım kimliği:</span>{" "}
                <code>{identity.hardware_id || identity.identifier}</code>
              </div>
              <div className="muted">
                (USB kameralarda MAC bulunmaz; seri numarası kalıcı kimlik
                olarak kullanılır)
              </div>
            </>
          )}
        </div>

        <form onSubmit={submit} className="name-form">
          <input
            placeholder="Ekipman adı (ör. TTC59)"
            value={equipment}
            onChange={(e) => setEquipment(e.target.value)}
            autoFocus
            required
            minLength={2}
          />
          <button disabled={busy || equipment.trim().length < 2}>
            {busy ? "Kaydediliyor…" : "Eşleştir"}
          </button>
        </form>
        {error && <div className="login-error">{error}</div>}
      </div>
    </div>
  );
}
