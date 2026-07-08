import { useCallback, useEffect, useRef, useState } from "react";
import { api, authedUrl, setToken } from "./api";
import CameraCard from "./components/CameraCard";
import AlertsFeed from "./components/AlertsFeed";
import DriverNameModal from "./components/DriverNameModal";
import EquipmentModal from "./components/EquipmentModal";

function riskClass(r) {
  return r >= 60 ? "risk-high" : r >= 30 ? "risk-mid" : "risk-low";
}

export default function Dashboard({ onLogout }) {
  const [cameras, setCameras] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [wsOn, setWsOn] = useState(false);
  const [clock, setClock] = useState("");
  const [drivers, setDrivers] = useState([]);
  const [identities, setIdentities] = useState({}); // camera_id -> identity
  const audioRef = useRef(null);

  // --- saat -----------------------------------------------------------------
  useEffect(() => {
    const t = setInterval(
      () => setClock(new Date().toLocaleTimeString("tr-TR")),
      1000
    );
    return () => clearInterval(t);
  }, []);

  // --- durum (1 sn) -----------------------------------------------------------
  useEffect(() => {
    let alive = true;
    async function tick() {
      try {
        const res = await api("/api/status");
        if (alive) setCameras(res.cameras);
      } catch {
        /* geçici hata */
      }
    }
    tick();
    const t = setInterval(tick, 1000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  // --- kamera kimlikleri (MAC / donanım ID + eşleştirme durumu) -----------------
  const loadIdentity = useCallback(async (cameraId) => {
    try {
      const res = await api(`/api/cameras/${cameraId}/identity`);
      setIdentities((prev) => ({ ...prev, [cameraId]: res }));
    } catch {
      setIdentities((prev) => ({ ...prev, [cameraId]: { error: true } }));
    }
  }, []);

  useEffect(() => {
    for (const c of cameras) {
      if (!(c.id in identities)) loadIdentity(c.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameras]);

  // --- sürücü kayıtları (2 sn: yakalama ilerlemesi + isim bekleyenler) ----------
  const refreshDrivers = useCallback(async () => {
    try {
      const res = await api("/api/drivers");
      setDrivers(res.drivers);
    } catch {
      /* geçici hata */
    }
  }, []);

  useEffect(() => {
    refreshDrivers();
    const t = setInterval(refreshDrivers, 2000);
    return () => clearInterval(t);
  }, [refreshDrivers]);

  // --- WebSocket uyarı akışı -----------------------------------------------------
  useEffect(() => {
    let ws;
    let closed = false;

    function beep() {
      try {
        audioRef.current =
          audioRef.current || new (window.AudioContext || window.webkitAudioContext)();
        const ctx = audioRef.current;
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.connect(g);
        g.connect(ctx.destination);
        o.frequency.value = 880;
        g.gain.value = 0.15;
        o.start();
        o.stop(ctx.currentTime + 0.35);
      } catch {
        /* ses desteklenmiyor */
      }
    }

    function connect() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(authedUrl(`${proto}://${location.host}/ws/alerts`));
      ws.onopen = () => setWsOn(true);
      ws.onclose = () => {
        setWsOn(false);
        if (!closed) setTimeout(connect, 3000);
      };
      ws.onmessage = (m) => {
        const msg = JSON.parse(m.data);
        if (msg.kind === "history") setAlerts(msg.data);
        else if (msg.kind === "alert") {
          setAlerts((prev) => [msg.data, ...prev].slice(0, 200));
          beep();
        }
      };
    }
    connect();
    return () => {
      closed = true;
      ws?.close();
    };
  }, []);

  async function logout() {
    try {
      await api("/api/logout", { method: "POST" });
    } catch {
      /* zaten geçersiz */
    }
    setToken(null);
    onLogout();
  }

  const pending = drivers.filter((d) => d.status === "pending");
  // eşlenmemiş ilk kamera: ekipman ataması zorunlu
  const unpaired = cameras.find(
    (c) => identities[c.id] && !identities[c.id].error && !identities[c.id].pairing
  );

  return (
    <div className="dash">
      <header>
        <span className="logo-badge">
          <img src="/static/logo.png" alt="Asyaport" />
        </span>
        <h1>
          <span className="accent">Asyaport</span> Sürücü İzleme Sistemi
        </h1>
        <div className="right">
          <div className="risk-chips">
            {cameras.map((c) => (
              <span
                key={c.id}
                className={`risk-chip ${riskClass(c.risk)}`}
                title="Sürücü risk puanı (0-100)"
              >
                {c.equipment || c.name}
                {c.driver ? ` · ${c.driver}` : ""} — RİSK %{c.risk}
                <span className="bar">
                  <i style={{ width: `${Math.min(100, c.risk)}%` }} />
                </span>
              </span>
            ))}
          </div>
          <span className="clock">{clock}</span>
          <span className={`ws-pill ${wsOn ? "on" : ""}`}>
            <span className="dot" />
            {wsOn ? "Canlı" : "Bağlantı yok"}
          </span>
          <button className="btn-ghost" onClick={logout}>
            Çıkış
          </button>
        </div>
      </header>

      <div className="layout">
        <div className="cams">
          {cameras.map((c) => (
            <CameraCard
              key={c.id}
              camera={c}
              identity={identities[c.id]}
              drivers={drivers.filter((d) => d.camera_id === c.id)}
              onDriversChanged={refreshDrivers}
            />
          ))}
          {cameras.length === 0 && (
            <div className="empty">Kamera durumu yükleniyor…</div>
          )}
        </div>
        <AlertsFeed alerts={alerts} />
      </div>

      {/* önce ekipman eşleştirme, sonra sürücü isimlendirme zorunluluğu */}
      {unpaired ? (
        <EquipmentModal
          camera={unpaired}
          identity={identities[unpaired.id]}
          onPaired={() => loadIdentity(unpaired.id)}
        />
      ) : (
        pending.length > 0 && (
          <DriverNameModal driver={pending[0]} onNamed={refreshDrivers} />
        )
      )}
    </div>
  );
}
