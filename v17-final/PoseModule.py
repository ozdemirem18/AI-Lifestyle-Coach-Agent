import cv2
import math
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# ---------------------------------------------------------------------------
# Model auto-download
# ---------------------------------------------------------------------------
_MODEL_DIR = Path(__file__).resolve().parent / ".mediapipe_models"
_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "pose_landmarker/pose_landmarker_lite/float16/latest/"
    "pose_landmarker_lite.task"
)
_MODEL_PATH = _MODEL_DIR / "pose_landmarker_lite.task"


def _ensure_model() -> str:
    """Download the PoseLandmarker model if it's not already on disk."""
    if _MODEL_PATH.exists():
        return str(_MODEL_PATH)
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading pose landmarker model ...")
    urllib.request.urlretrieve(_MODEL_URL, str(_MODEL_PATH))
    print("Download complete.")
    return str(_MODEL_PATH)


# ---------------------------------------------------------------------------
# Landmark connections (MediaPipe Pose standard topology, 33 landmarks)
# ---------------------------------------------------------------------------
POSE_CONNECTIONS = frozenset([
    (0, 1), (1, 2), (2, 3), (3, 7),        # face
    (0, 4), (4, 5), (5, 6), (6, 8),        # face
    (9, 10),                                # mouth
    (11, 12),                               # shoulders
    (11, 13), (13, 15),                     # left arm
    (12, 14), (14, 16),                     # right arm
    (11, 23), (12, 24),                     # torso sides
    (23, 24),                               # hips
    (23, 25), (25, 27),                     # left leg
    (24, 26), (26, 28),                     # right leg
    (27, 29), (29, 31),                     # left foot
    (28, 30), (30, 32),                     # right foot
])


class poseDetector:
    """
    Replaces the legacy mp.solutions.pose API with the modern
    mp.tasks.vision.PoseLandmarker API while keeping the same
    interface used by camera4.py (findPose / findPosition / findAngle).
    """

    def __init__(
        self,
        mode: bool = False,
        smooth: bool = True,
        model_complexity: int = 1,
        enable_segmentation: bool = False,
        smooth_segementaion: bool = True,
        detectionCon: float = 0.5,
        trackCon: float = 0.5,
    ):
        # Keep params for reference; the new API handles them internally.
        self.mode = mode
        self.detectionCon = detectionCon
        self.trackCon = trackCon
        self.model_complexity = model_complexity

        # Build the PoseLandmarker.
        model_path = _ensure_model()
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            min_pose_detection_confidence=detectionCon,
            min_tracking_confidence=trackCon,
            min_pose_presence_confidence=detectionCon,
            output_segmentation_masks=enable_segmentation,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)

        # Per-frame result cache (populated by findPose).
        self.results: Any = None
        self.lmlist: list[list[int]] = []

    # ------------------------------------------------------------------
    # Public API  (used by camera4.py)
    # ------------------------------------------------------------------

    def findPose(self, img, draw: bool = True):
        """Detect pose, optionally draw landmarks, return the image."""
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        detection_result = self._landmarker.detect(mp_image)

        self.results = detection_result

        if draw and detection_result.pose_landmarks:
            h, w = img.shape[:2]
            for landmarks in detection_result.pose_landmarks:
                # Draw connections
                for start_idx, end_idx in POSE_CONNECTIONS:
                    if start_idx < len(landmarks) and end_idx < len(landmarks):
                        x1 = int(landmarks[start_idx].x * w)
                        y1 = int(landmarks[start_idx].y * h)
                        x2 = int(landmarks[end_idx].x * w)
                        y2 = int(landmarks[end_idx].y * h)
                        cv2.line(img, (x1, y1), (x2, y2), (255, 255, 255), 2)

                # Draw landmark dots
                for lm in landmarks:
                    cx = int(lm.x * w)
                    cy = int(lm.y * h)
                    cv2.circle(img, (cx, cy), 4, (0, 255, 0), cv2.FILLED)

        return img

    def findPosition(self, img, draw: bool = True):
        """
        Return landmark list in the format camera4.py expects:
            [[id, cx, cy], ...]
        """
        self.lmlist = []
        if not self.results or not self.results.pose_landmarks:
            return self.lmlist

        h, w = img.shape[:2]
        for landmarks in self.results.pose_landmarks:
            for lm_id, lm in enumerate(landmarks):
                cx = int(lm.x * w)
                cy = int(lm.y * h)
                self.lmlist.append([lm_id, cx, cy])
                if draw:
                    cv2.circle(img, (cx, cy), 5, (255, 0, 0), cv2.FILLED)

        return self.lmlist

    def finfAngle(self, img, p1: int, p2: int, p3: int, draw: bool = True):
        """
        Calculate the angle (in degrees) at landmark p2 formed by
        landmarks p1-p2-p3.
        """
        if not self.lmlist or p1 >= len(self.lmlist) or p2 >= len(self.lmlist) or p3 >= len(self.lmlist):
            return 0

        x1, y1 = self.lmlist[p1][1:]
        x2, y2 = self.lmlist[p2][1:]
        x3, y3 = self.lmlist[p3][1:]

        angle = math.degrees(
            math.atan2(y3 - y2, x3 - x2) - math.atan2(y1 - y2, x1 - x2)
        )
        if angle < 0:
            angle += 360

        if draw:
            cv2.line(img, (x1, y1), (x2, y2), (255, 255, 255), 3)
            cv2.line(img, (x3, y3), (x2, y2), (255, 255, 255), 3)
            cv2.circle(img, (x1, y1), 10, (0, 0, 255), cv2.FILLED)
            cv2.circle(img, (x1, y1), 15, (0, 0, 255), 2)
            cv2.circle(img, (x2, y2), 10, (0, 0, 255), cv2.FILLED)
            cv2.circle(img, (x2, y2), 15, (0, 0, 255), 2)
            cv2.circle(img, (x3, y3), 10, (0, 0, 255), cv2.FILLED)
            cv2.circle(img, (x3, y3), 15, (0, 0, 255), 2)
            cv2.putText(
                img, str(int(angle)), (x2 - 50, y2 + 50),
                cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 255), 2
            )

        return angle


# ---------------------------------------------------------------------------
# Standalone test (mirrors the original main())
# ---------------------------------------------------------------------------
def main():
    cap = cv2.VideoCapture(0)
    p_time = 0
    detector = poseDetector()

    while True:
        success, img = cap.read()
        if not success:
            break
        img = detector.findPose(img)
        lmlist = detector.findPosition(img, draw=False)
        if lmlist:
            cv2.circle(img, (lmlist[14][1], lmlist[14][2]), 15, (0, 0, 255), cv2.FILLED)

        c_time = time.time()
        fps = 1 / (c_time - p_time) if (c_time - p_time) > 0 else 0
        p_time = c_time
        cv2.putText(img, str(int(fps)), (70, 58), cv2.FONT_HERSHEY_PLAIN, 3, (255, 0, 0), 3)
        cv2.imshow("Image", img)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
