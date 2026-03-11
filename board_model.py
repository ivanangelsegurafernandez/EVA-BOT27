# -*- coding: utf-8 -*-
"""BoardGate-V1: carga de modelo e inferencia segura."""

from __future__ import annotations

import json
import os

try:
    import joblib
except Exception:
    joblib = None


class BoardGateModel:
    def __init__(self, model_path: str, scaler_path: str | None = None, features_path: str | None = None, meta_path: str | None = None):
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.features_path = features_path
        self.meta_path = meta_path
        self.model = None
        self.scaler = None
        self.feature_order = None
        self.meta = {}
        self._ready = False
        self._reason = "init"
        self._load_assets()

    def _load_assets(self):
        if joblib is None:
            self._ready = False
            self._reason = "joblib_missing"
            return
        if not os.path.exists(self.model_path):
            self._ready = False
            self._reason = "no_model"
            return
        try:
            self.model = joblib.load(self.model_path)
            if self.scaler_path and os.path.exists(self.scaler_path):
                self.scaler = joblib.load(self.scaler_path)
            if self.features_path and os.path.exists(self.features_path):
                self.feature_order = list(joblib.load(self.features_path))
            if self.meta_path and os.path.exists(self.meta_path):
                with open(self.meta_path, "r", encoding="utf-8") as f:
                    self.meta = json.load(f) or {}
            self._ready = True
            self._reason = "ok"
        except Exception as e:
            self._ready = False
            self._reason = f"load_err:{type(e).__name__}"

    def _regime_from_features(self, feats: dict) -> str:
        if feats.get("mine_risk_red_wall", 0) > 0.65:
            return "RED_WALL"
        if feats.get("mine_risk_zebra", 0) > 0.65:
            return "ZEBRA_NOISE"
        if feats.get("mine_risk_false_rebound", 0) > 0.60:
            return "FALSE_REBOUND"
        if feats.get("mine_risk_late_green", 0) > 0.65:
            return "LATE_GREEN"
        if feats.get("board_right4_green", 0) > 0.68:
            return "GREEN_WAVE"
        if feats.get("board_right4_green", 0) > 0.52 and feats.get("board_right6_red", 0) > 0.45:
            return "CLEAN_REBOUND"
        return "UNKNOWN"

    def predict(self, features: dict) -> dict:
        features = features if isinstance(features, dict) else {}
        try:
            risks = [
                float(features.get("mine_risk_red_wall", 0.0) or 0.0),
                float(features.get("mine_risk_zebra", 0.0) or 0.0),
                float(features.get("mine_risk_late_green", 0.0) or 0.0),
                float(features.get("mine_risk_false_rebound", 0.0) or 0.0),
            ]
            risk = float(sum(risks) / max(1, len(risks)))
        except Exception:
            risk = 0.0

        if not self._ready or self.model is None:
            return {
                "p_pattern_win": float(max(0.0, min(1.0, 0.5 - (risk - 0.5) * 0.3))),
                "mine_risk": float(max(0.0, min(1.0, risk))),
                "regime_tag": self._regime_from_features(features),
                "confidence_pattern": 0.0,
                "model_ready": False,
                "reason": self._reason,
            }

        try:
            f_order = self.feature_order or sorted(features.keys())
            x = [[float(features.get(k, 0.0) or 0.0) for k in f_order]]
            if self.scaler is not None:
                x = self.scaler.transform(x)
            proba = self.model.predict_proba(x)
            row0 = proba[0] if hasattr(proba, "__getitem__") else [0.5, 0.5]
            p = float(row0[-1])
            p = max(0.0, min(1.0, p))
            conf = abs(p - 0.5) * 2.0
            return {
                "p_pattern_win": float(p),
                "mine_risk": float(max(0.0, min(1.0, risk))),
                "regime_tag": self._regime_from_features(features),
                "confidence_pattern": float(max(0.0, min(1.0, conf))),
                "model_ready": True,
                "reason": "ok",
            }
        except Exception as e:
            return {
                "p_pattern_win": 0.5,
                "mine_risk": float(max(0.0, min(1.0, risk))),
                "regime_tag": "UNKNOWN",
                "confidence_pattern": 0.0,
                "model_ready": False,
                "reason": f"predict_err:{type(e).__name__}",
            }
