"""MediaPipe Face Mesh tabanlı yüz analizi.

Görseldeki mimariye uygun olarak:
- EAR (Eye Aspect Ratio)  : göz açıklık oranı -> mikro uyku / PERCLOS
- MAR (Mouth Aspect Ratio): ağız açıklık oranı -> esneme
- Head Pose (solvePnP)    : baş öne düşme / yola bakmama
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np

# MediaPipe Face Mesh landmark indeksleri (468 noktalı model)
# EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]

# MAR için: ağız köşeleri (yatay) ve dikey nokta çiftleri
MOUTH_CORNERS = (61, 291)
MOUTH_VERTICAL_PAIRS = [(13, 14), (81, 178), (311, 402)]

# Head pose için 2D-3D eşleşen noktalar
POSE_LANDMARKS = {
    "nose_tip": 1,
    "chin": 152,
    "left_eye_corner": 263,
    "right_eye_corner": 33,
    "left_mouth": 291,
    "right_mouth": 61,
}
# Genel insan yüzü 3D model noktaları (mm cinsinden yaklaşık değerler)
MODEL_POINTS_3D = np.array(
    [
        (0.0, 0.0, 0.0),          # burun ucu
        (0.0, -63.6, -12.5),      # çene
        (-43.3, 32.7, -26.0),     # sol göz dış köşe
        (43.3, 32.7, -26.0),      # sağ göz dış köşe
        (-28.9, -28.9, -24.1),    # sol ağız köşesi
        (28.9, -28.9, -24.1),     # sağ ağız köşesi
    ],
    dtype=np.float64,
)


@dataclass
class FaceMetrics:
    ear: float          # iki gözün ortalama EAR değeri
    mar: float          # ağız açıklık oranı
    pitch: float        # derece; negatif = baş öne eğik
    yaw: float          # derece; 0 = kameraya bakıyor
    roll: float         # derece
    landmarks: np.ndarray  # (468, 2) piksel koordinatları


class FaceAnalyzer:
    def __init__(self) -> None:
        self._mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def analyze(self, frame_bgr: np.ndarray) -> Optional[FaceMetrics]:
        """Karedeki sürücü yüzünü analiz eder; yüz yoksa None döner."""
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._mesh.process(rgb)
        if not result.multi_face_landmarks:
            return None

        lm = result.multi_face_landmarks[0].landmark
        pts = np.array([(p.x * w, p.y * h) for p in lm], dtype=np.float64)

        ear = (self._ear(pts, LEFT_EYE) + self._ear(pts, RIGHT_EYE)) / 2.0
        mar = self._mar(pts)
        pitch, yaw, roll = self._head_pose(pts, w, h)
        return FaceMetrics(ear=ear, mar=mar, pitch=pitch, yaw=yaw, roll=roll, landmarks=pts)

    @staticmethod
    def _ear(pts: np.ndarray, idx: list[int]) -> float:
        p1, p2, p3, p4, p5, p6 = (pts[i] for i in idx)
        v1 = np.linalg.norm(p2 - p6)
        v2 = np.linalg.norm(p3 - p5)
        hdist = np.linalg.norm(p1 - p4)
        if hdist < 1e-6:
            return 0.0
        return float((v1 + v2) / (2.0 * hdist))

    @staticmethod
    def _mar(pts: np.ndarray) -> float:
        left, right = pts[MOUTH_CORNERS[0]], pts[MOUTH_CORNERS[1]]
        hdist = np.linalg.norm(left - right)
        if hdist < 1e-6:
            return 0.0
        vertical = np.mean(
            [np.linalg.norm(pts[a] - pts[b]) for a, b in MOUTH_VERTICAL_PAIRS]
        )
        return float(vertical / hdist)

    @staticmethod
    def _head_pose(pts: np.ndarray, w: int, h: int) -> tuple[float, float, float]:
        image_points = np.array(
            [
                pts[POSE_LANDMARKS["nose_tip"]],
                pts[POSE_LANDMARKS["chin"]],
                pts[POSE_LANDMARKS["left_eye_corner"]],
                pts[POSE_LANDMARKS["right_eye_corner"]],
                pts[POSE_LANDMARKS["left_mouth"]],
                pts[POSE_LANDMARKS["right_mouth"]],
            ],
            dtype=np.float64,
        )
        focal = float(w)
        camera_matrix = np.array(
            [[focal, 0, w / 2.0], [0, focal, h / 2.0], [0, 0, 1]], dtype=np.float64
        )
        dist_coeffs = np.zeros((4, 1))
        ok, rvec, _tvec = cv2.solvePnP(
            MODEL_POINTS_3D, image_points, camera_matrix, dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            return 0.0, 0.0, 0.0
        rmat, _ = cv2.Rodrigues(rvec)
        # Euler açıları (derece)
        sy = float(np.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2))
        if sy > 1e-6:
            pitch = np.degrees(np.arctan2(-rmat[2, 0], sy))
            yaw = np.degrees(np.arctan2(rmat[1, 0], rmat[0, 0]))
            roll = np.degrees(np.arctan2(rmat[2, 1], rmat[2, 2]))
        else:
            pitch = np.degrees(np.arctan2(-rmat[2, 0], sy))
            yaw = 0.0
            roll = np.degrees(np.arctan2(-rmat[1, 2], rmat[1, 1]))
        return float(pitch), float(yaw), float(roll)

    def close(self) -> None:
        self._mesh.close()
