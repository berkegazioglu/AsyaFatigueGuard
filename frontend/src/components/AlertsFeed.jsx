import { authedUrl } from "../api";

export default function AlertsFeed({ alerts }) {
  return (
    <div className="alerts">
      <h2>⚠️ Canlı Uyarılar</h2>
      <div className="alert-list">
        {alerts.length === 0 && <div className="empty">Henüz uyarı yok.</div>}
        {alerts.map((a, i) => (
          <div key={`${a.timestamp}-${i}`} className={`alert ${a.severity}`}>
            <div className="t">
              {a.title} — {a.camera_name}
            </div>
            <div className="m">
              {a.time_str}
              {typeof a.risk === "number" && ` · risk %${a.risk}`} · {a.message}{" "}
              {a.snapshot && (
                <a href={authedUrl(a.snapshot)} target="_blank" rel="noreferrer">
                  görüntü
                </a>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
