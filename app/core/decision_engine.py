"""Karar mekanizması: EAR/MAR/baş pozu + YOLO çıktısından alarm olayları üretir.

Görseldeki mantığın endüstriyel hâli:
  "Eğer EAR < 0.21 ve süre > 1.5 sn ise -> MİKRO UYKU alarmı"
Ek olarak PERCLOS (yorgunluk), esneme sayacı, baş düşmesi, dikkat dağınıklığı,
telefon/sigara kalıcılık süzgeci ve davranışsal bozulma (alkol ŞÜPHESİ) kuralları.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from app.core.face_analyzer import FaceMetrics
from app.core.object_detector import Detection

# Alarm tipleri ve Türkçe açıklamaları
EVENT_INFO = {
    "MICROSLEEP":  ("Mikro Uyku",           "critical", "Sürücünün gözleri uzun süre kapalı!"),
    "DROWSINESS":  ("Yorgunluk (PERCLOS)",  "critical", "Göz kapanma oranı kritik seviyede."),
    "YAWN":        ("Esneme",               "warning",  "Sürücü esniyor."),
    "FATIGUE":     ("Aşırı Yorgunluk",      "critical", "Kısa sürede çok sayıda esneme tespit edildi."),
    "HEAD_DOWN":   ("Baş Öne Düştü",        "critical", "Sürücünün başı öne düşük."),
    "DISTRACTION": ("Dikkat Dağınıklığı",   "warning",  "Sürücü yola bakmıyor."),
    "PHONE_USE":   ("Telefon Kullanımı",    "critical", "Sürücü telefon kullanıyor."),
    "SMOKING":     ("Sigara Kullanımı",     "warning",  "Sürücü sigara içiyor."),
    "DRINKING":    ("İçecek İçme",          "warning",  "Sürücü içecek içiyor (çay/kahve vb.)."),
    "NO_FACE":     ("Sürücü Görünmüyor",    "warning",  "Yüz algılanamıyor (kamera engellenmiş olabilir)."),
    "IMPAIRMENT":  ("Bozulmuş Sürüş Şüphesi", "critical",
                    "Yoğun uyku belirtileri: alkol/ilaç/aşırı yorgunluk ŞÜPHESİ. "
                    "(Kamera alkolü ölçemez; bu davranışsal bir göstergedir.)"),
}

# Risk puanı ağırlıkları: her alarm, sürücünün risk skoruna bu kadar puan ekler.
# Puanlar zamanla üstel olarak söner (bkz. AlertManager.risk).
RISK_POINTS = {
    "MICROSLEEP": 25, "DROWSINESS": 22, "IMPAIRMENT": 35, "HEAD_DOWN": 22,
    "FATIGUE": 18, "PHONE_USE": 20, "DISTRACTION": 12, "SMOKING": 10,
    "YAWN": 8, "NO_FACE": 8, "DRINKING": 6,
}


@dataclass
class Event:
    type: str
    camera_id: str
    camera_name: str
    timestamp: float
    title: str
    severity: str      # "warning" | "critical"
    message: str
    value: Optional[float] = None   # tetikleyen metrik (EAR, MAR, açı, conf...)


@dataclass
class _Timer:
    """Bir koşulun kesintisiz ne kadar sürdüğünü ölçer."""
    since: Optional[float] = None

    def update(self, active: bool, now: float) -> float:
        if not active:
            self.since = None
            return 0.0
        if self.since is None:
            self.since = now
        return now - self.since

    def reset(self) -> None:
        self.since = None


@dataclass
class _StickyTimer:
    """Kısa kesintileri tolere eden süre ölçer.

    YOLO tespitleri kareden kareye titreyebilir (özellikle şeffaf nesneler);
    'tolerance' saniyeden kısa boşluklar sayacı sıfırlamaz.
    """
    tolerance: float = 0.8
    since: Optional[float] = None
    _last_true: Optional[float] = None

    def update(self, active: bool, now: float) -> float:
        if active:
            if self.since is None:
                self.since = now
            self._last_true = now
        elif self.since is not None and now - (self._last_true or 0.0) > self.tolerance:
            self.reset()
        return (now - self.since) if self.since is not None else 0.0

    def reset(self) -> None:
        self.since = None
        self._last_true = None


@dataclass
class DriverState:
    """Panele gönderilen anlık durum özeti."""
    ear: float = 0.0
    mar: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    perclos: float = 0.0
    face_visible: bool = False
    phone: bool = False
    cigarette: bool = False
    drinking: bool = False
    active_events: list = field(default_factory=list)


class DecisionEngine:
    def __init__(self, camera_id: str, camera_name: str, det_cfg: dict):
        self.camera_id = camera_id
        self.camera_name = camera_name
        c = det_cfg
        self.ear_thr = c.get("ear_threshold", 0.21)
        self.microsleep_sec = c.get("microsleep_sec", 1.5)
        self.perclos_window = c.get("perclos_window_sec", 60)
        self.perclos_thr = c.get("perclos_threshold", 0.30)
        self.mar_thr = c.get("mar_threshold", 0.65)
        self.yawn_min_sec = c.get("yawn_min_sec", 1.2)
        self.yawns_for_fatigue = c.get("yawns_for_fatigue", 3)
        self.yawn_window = c.get("yawn_window_sec", 300)
        self.head_down_pitch = c.get("head_down_pitch_deg", -18)
        self.head_down_sec = c.get("head_down_sec", 2.0)
        self.distraction_yaw = c.get("distraction_yaw_deg", 32)
        self.distraction_sec = c.get("distraction_sec", 2.5)
        self.phone_persist = c.get("phone_persist_sec", 1.5)
        self.cig_persist = c.get("cigarette_persist_sec", 1.5)
        self.drink_persist = c.get("drink_persist_sec", 2.0)
        self.no_face_sec = c.get("no_face_sec", 6.0)
        self.impair_thr = c.get("impairment_events_threshold", 4)
        self.impair_window = c.get("impairment_window_sec", 300)

        self._t_eye = _Timer()
        self._t_yawn = _Timer()
        self._t_head = _Timer()
        self._t_yaw = _Timer()
        self._t_phone = _StickyTimer()
        self._t_cig = _StickyTimer()
        self._t_drink = _StickyTimer()
        self._t_noface = _Timer()

        self._eye_samples: deque[tuple[float, bool]] = deque()   # (zaman, kapalı mı)
        self._yawn_times: deque[float] = deque()
        self._severe_times: deque[float] = deque()               # bozulma penceresi
        self._yawn_fired = False   # aynı esneme için tek olay

        self.state = DriverState()

    def update(
        self,
        face: Optional[FaceMetrics],
        detections: list[Detection],
        now: Optional[float] = None,
    ) -> list[Event]:
        now = now if now is not None else time.time()
        events: list[Event] = []
        s = self.state
        s.active_events = []

        # --- yüz yokluğu ---------------------------------------------------
        s.face_visible = face is not None
        if self._t_noface.update(face is None, now) >= self.no_face_sec:
            events.append(self._ev("NO_FACE", now))
            self._t_noface.reset()

        if face is not None:
            s.ear, s.mar = round(face.ear, 3), round(face.mar, 3)
            s.pitch, s.yaw = round(face.pitch, 1), round(face.yaw, 1)

            # --- mikro uyku (EAR) -------------------------------------------
            eyes_closed = face.ear < self.ear_thr
            if self._t_eye.update(eyes_closed, now) >= self.microsleep_sec:
                events.append(self._ev("MICROSLEEP", now, value=face.ear))
                self._severe_times.append(now)
                self._t_eye.reset()

            # --- PERCLOS ----------------------------------------------------
            self._eye_samples.append((now, eyes_closed))
            cutoff = now - self.perclos_window
            while self._eye_samples and self._eye_samples[0][0] < cutoff:
                self._eye_samples.popleft()
            if len(self._eye_samples) >= 30:
                closed = sum(1 for _, c in self._eye_samples if c)
                s.perclos = round(closed / len(self._eye_samples), 3)
                if s.perclos >= self.perclos_thr:
                    events.append(self._ev("DROWSINESS", now, value=s.perclos))
                    self._severe_times.append(now)
                    self._eye_samples.clear()   # aynı pencere için tek alarm

            # --- esneme (MAR) -----------------------------------------------
            yawning = face.mar > self.mar_thr
            dur = self._t_yawn.update(yawning, now)
            if dur >= self.yawn_min_sec and not self._yawn_fired:
                self._yawn_fired = True
                self._yawn_times.append(now)
                events.append(self._ev("YAWN", now, value=face.mar))
                while self._yawn_times and self._yawn_times[0] < now - self.yawn_window:
                    self._yawn_times.popleft()
                if len(self._yawn_times) >= self.yawns_for_fatigue:
                    events.append(self._ev("FATIGUE", now, value=float(len(self._yawn_times))))
                    self._severe_times.append(now)
                    self._yawn_times.clear()
            if not yawning:
                self._yawn_fired = False

            # --- baş öne düşmesi --------------------------------------------
            head_down = face.pitch < self.head_down_pitch
            if self._t_head.update(head_down, now) >= self.head_down_sec:
                events.append(self._ev("HEAD_DOWN", now, value=face.pitch))
                self._severe_times.append(now)
                self._t_head.reset()

            # --- dikkat dağınıklığı (yaw) -------------------------------------
            looking_away = abs(face.yaw) > self.distraction_yaw
            if self._t_yaw.update(looking_away, now) >= self.distraction_sec:
                events.append(self._ev("DISTRACTION", now, value=face.yaw))
                self._t_yaw.reset()
        else:
            s.ear = s.mar = s.perclos = 0.0
            self._t_eye.reset()
            self._t_yawn.reset()
            self._t_head.reset()
            self._t_yaw.reset()

        # --- içecek içme (bardak/şişe AĞIZ HİZASINDA ise) ---------------------
        # Bardak torpidoda/elde alçakta dururken alarm üretmemek için yüz
        # görünür olmalı ve kap ağza yakın olmalı.
        drink_det = next(
            (d for d in detections
             if d.label == "drink" and self._near_mouth(face, d.box)),
            None,
        )
        s.drinking = drink_det is not None
        if self._t_drink.update(drink_det is not None, now) >= self.drink_persist:
            events.append(self._ev("DRINKING", now, value=drink_det.confidence if drink_det else None))
            self._t_drink.reset()

        # --- telefon / sigara (yüzden bağımsız) -------------------------------
        phone_det = next((d for d in detections if d.label == "phone"), None)
        cig_det = next((d for d in detections if d.label == "cigarette"), None)
        # Çay/kahve bardağı sigara modeliyle karışabiliyor: içecek ağız
        # hizasındayken sigara tespiti yok sayılır (bardak daha güvenilir sinyal).
        if drink_det is not None:
            cig_det = None
            self._t_cig.reset()
        s.phone, s.cigarette = phone_det is not None, cig_det is not None

        if self._t_phone.update(phone_det is not None, now) >= self.phone_persist:
            events.append(self._ev("PHONE_USE", now, value=phone_det.confidence if phone_det else None))
            self._t_phone.reset()
        if self._t_cig.update(cig_det is not None, now) >= self.cig_persist:
            events.append(self._ev("SMOKING", now, value=cig_det.confidence if cig_det else None))
            self._t_cig.reset()

        # --- davranışsal bozulma (alkol ŞÜPHESİ - dolaylı) --------------------
        while self._severe_times and self._severe_times[0] < now - self.impair_window:
            self._severe_times.popleft()
        if len(self._severe_times) >= self.impair_thr:
            events.append(self._ev("IMPAIRMENT", now, value=float(len(self._severe_times))))
            self._severe_times.clear()

        s.active_events = [e.type for e in events]
        return events

    @staticmethod
    def _near_mouth(face: Optional[FaceMetrics], box: tuple) -> bool:
        """Kutunun sürücünün ağzına yakın olup olmadığını kontrol eder.

        Ağız noktası, %60 büyütülmüş tespit kutusunun içindeyse 'yakın' sayılır.
        Yüz yoksa False döner (içecek alarmı yüz doğrulaması ister).
        """
        if face is None or len(face.landmarks) < 14:
            return False
        mx, my = face.landmarks[13]  # üst dudak orta noktası
        x1, y1, x2, y2 = box
        ex, ey = (x2 - x1) * 0.6, (y2 - y1) * 0.6
        return (x1 - ex) <= mx <= (x2 + ex) and (y1 - ey) <= my <= (y2 + ey)

    def _ev(self, etype: str, now: float, value: Optional[float] = None) -> Event:
        title, severity, message = EVENT_INFO[etype]
        return Event(
            type=etype,
            camera_id=self.camera_id,
            camera_name=self.camera_name,
            timestamp=now,
            title=title,
            severity=severity,
            message=message,
            value=round(value, 3) if value is not None else None,
        )
