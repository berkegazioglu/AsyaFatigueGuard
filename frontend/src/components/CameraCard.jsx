import { useEffect, useState } from "react";
import { api, authedUrl } from "../api";

function Chip({ label, bad }) {
  return <span className={`chip ${bad ? "bad" : ""}`}>{label}</span>;
}

export default function CameraCard({ camera, drivers, onDriversChanged }) {
  const [identity, setIdentity] = useState(null);
  const [equipmentName, setEquipmentName] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const s = camera.state;
  const alarm = s.active_events.length > 0;
  const capturing = drivers.find((d) => d.status === "capturing");
  const namedDrivers = drivers.filter((d) => d.status === "named");

  useEffect(() => {
    let alive = true;
    api(`/api/cameras/${camera.id}/identity`)
      .then((res) => alive && setIdentity(res))
      .catch(() => alive && setIdentity({ error: true }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera.id]);

  async function pair(e) {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await api("/api/equipment", {
        method: "POST",
        body: JSON.stringify({
          identifier: identity.identifier,
          equipment: equipmentName,
          camera_id: camera.id,
        }),
      });
      const res = await api(`/api/cameras/${camera.id}/identity`);
      setIdentity(res);
      setEquipmentName("");
      setMessage("Eşleştirme kaydedildi ✓");
    } catch (err) {
      setMessage(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function enroll() {
    setBusy(true);
    setMessage("");
    try {
      await api(`/api/cameras/${camera.id}/enroll`, { method: "POST" });
      setMessage("Yakalama başladı: sürücü kameraya bakmalı");
      onDriversChanged();
    } catch (err) {
      setMessage(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`cam ${alarm ? "alarm" : ""}`}>
      <img src={authedUrl(`/stream/${camera.id}`)} alt={camera.name} />

      <div className="bar">
        <span className={`dot ${camera.online ? "on" : ""}`} />
        <span className="name">
          {camera.equipment ? `${camera.equipment} · ` : ""}
          {camera.name}
        </span>
        <span className="fps">
          {camera.online ? `${camera.fps} FPS` : "çevrimdışı"}
        </span>
      </div>

      <div className="metrics">
        <Chip label={`EAR ${s.ear.toFixed(2)}`} />
        <Chip label={`MAR ${s.mar.toFixed(2)}`} />
        <Chip label={`PERCLOS ${(s.perclos * 100).toFixed(0)}%`} bad={s.perclos > 0.25} />
        <Chip label={s.face_visible ? "Yüz ✓" : "Yüz ✗"} bad={!s.face_visible} />
        {s.phone && <Chip label="📱 TELEFON" bad />}
        {s.cigarette && <Chip label="🚬 SİGARA" bad />}
        {s.drinking && <Chip label="☕ İÇECEK" bad />}
      </div>

      <div className="cam-admin">
        <div className="identity">
          {identity === null && <span className="muted">Kimlik algılanıyor…</span>}
          {identity?.error && <span className="muted">Kimlik alınamadı</span>}
          {identity && !identity.error && (
            <>
              <span className="muted">
                {identity.kind === "ip"
                  ? `MAC: ${identity.mac || "bulunamadı"} (${identity.ip})`
                  : `Kaynak: ${identity.identifier} (MAC yok)`}
              </span>
              {identity.pairing ? (
                <span className="paired">
                  🔗 {identity.pairing.equipment} ekipmanına eşli
                </span>
              ) : (
                <form className="pair-form" onSubmit={pair}>
                  <input
                    placeholder="Ekipman adı (ör. TTC59)"
                    value={equipmentName}
                    onChange={(e) => setEquipmentName(e.target.value)}
                    required
                  />
                  <button disabled={busy}>Eşleştir</button>
                </form>
              )}
            </>
          )}
        </div>

        <div className="enroll">
          {capturing ? (
            <span className="capturing">
              📸 Fotoğraf yakalanıyor: {capturing.photos.length}/10
            </span>
          ) : (
            <button className="btn-primary" onClick={enroll} disabled={busy}>
              👤 Sürücü Tanımla (10 fotoğraf)
            </button>
          )}
          {namedDrivers.length > 0 && (
            <span className="muted">
              Kayıtlı: {namedDrivers.map((d) => d.name).join(", ")}
            </span>
          )}
        </div>

        {message && <div className="cam-msg">{message}</div>}
      </div>
    </div>
  );
}
