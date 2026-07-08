import { useState } from "react";
import { api, authedUrl } from "../api";

function Chip({ label, bad }) {
  return <span className={`chip ${bad ? "bad" : ""}`}>{label}</span>;
}

export default function CameraCard({ camera, identity, drivers, onDriversChanged }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const s = camera.state;
  const alarm = s.active_events.length > 0;
  const capturing = drivers.find((d) => d.status === "capturing");

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
        {camera.driver && <span className="driver-tag">👤 {camera.driver}</span>}
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
          {identity === undefined && (
            <span className="muted">Kimlik algılanıyor…</span>
          )}
          {identity?.error && <span className="muted">Kimlik alınamadı</span>}
          {identity && !identity.error && (
            <span className="muted">
              {identity.kind === "ip"
                ? `MAC: ${identity.mac || "bulunamadı"} (${identity.ip})`
                : `Donanım ID: ${identity.hardware_id || identity.identifier}`}
              {identity.pairing && (
                <span className="paired"> · 🔗 {identity.pairing.equipment}</span>
              )}
            </span>
          )}
        </div>

        <div className="enroll">
          {capturing ? (
            <span className="capturing">
              📸 Sürücü fotoğrafları yakalanıyor: {capturing.photos.length}/10
            </span>
          ) : (
            <button className="btn-primary" onClick={enroll} disabled={busy}>
              👤 Yeni Sürücü Tanımla
            </button>
          )}
          <span className="muted">
            (vardiya başında yüz görülünce otomatik başlar)
          </span>
        </div>

        {message && <div className="cam-msg">{message}</div>}
      </div>
    </div>
  );
}
