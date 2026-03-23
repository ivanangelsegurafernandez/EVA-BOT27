"""Fallback mínimo de joblib para entornos sin dependencia instalada.
Implementa load/dump compatibles para uso básico del bot.
"""
from __future__ import annotations
import pickle
from typing import Any


def dump(obj: Any, filename: str, compress: int | None = None) -> str:
    with open(filename, "wb") as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
    return filename


def load(filename: str) -> Any:
    with open(filename, "rb") as f:
        return pickle.load(f)
