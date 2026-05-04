from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CINTASModel:
    """CINTAS/CIAS parameter bundle + scoring functions.

    This is the same scoring core used in EXACT.ipynb:

      * Normalize telemetry using BENIGN mean/std
      * Compute:
          E2(t) = Σ_f w_f * z_f(t)^2
          E1(t) = Σ_f w_f * |z_f(t)|
          score(t) = (1 - λ)E2(t) + λE1(t)

    In the draft paper, CINTAS runs in fixed-point on-chip. This class is a
    *software reference* implementation; see FixedPointCINTAS for a small
    Q-format prototype.

    Attributes
    ----------
    feature_cols:
        Feature names (and order) used by this model.
    mu:
        BENIGN mean per feature.
    sigma:
        BENIGN std per feature.
    w:
        Non-negative weights per feature (sum to 1).
    lambda_res:
        Mixing coefficient λ in [0, 1].
    """
    feature_cols: list[str]
    mu: np.ndarray
    sigma: np.ndarray
    w: np.ndarray
    lambda_res: float = 0.5

    def _sigma_safe(self) -> np.ndarray:
        return np.where(self.sigma <= 1e-6, 1.0, self.sigma)

    def score_array(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Compute (score, E1, E2) for X with shape (n_samples, n_features)."""
        s = self._sigma_safe()
        Z = (X - self.mu) / s

        E2 = np.sum(self.w * (Z ** 2), axis=1)
        E1 = np.sum(self.w * np.abs(Z), axis=1)

        score = (1.0 - self.lambda_res) * E2 + self.lambda_res * E1
        return score.astype(float), E1.astype(float), E2.astype(float)

    def score_dataframe(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        X = df[self.feature_cols].to_numpy(dtype=float)
        return self.score_array(X)


def fit_cintas_from_benign(
    df: pd.DataFrame,
    feature_cols: list[str],
    lambda_res: float = 0.5,
    *,
    scenario_col: str = "scenario",
    benign_name: str = "BENIGN",
    weight_mode: Literal["inv_var", "uniform"] = "inv_var",
) -> CINTASModel:
    """Fit CINTAS parameters from BENIGN rows only (unsupervised).

    The draft notebooks use inverse variance as a lightweight unsupervised
    weighting scheme (stable features get larger weight). Use uniform weights
    to match the unweighted form shown in the paper text.
    """
    if scenario_col not in df.columns:
        raise KeyError(f"Expected '{scenario_col}' column to fit from benign.")

    ben = df[df[scenario_col].astype(str).str.upper() == benign_name.upper()].copy()
    if ben.empty:
        raise ValueError("No BENIGN rows found; cannot fit CINTAS.")

    X_ben = ben[feature_cols].to_numpy(dtype=float)
    mu = X_ben.mean(axis=0)
    sigma = X_ben.std(axis=0, ddof=1)

    if weight_mode == "uniform":
        w = np.ones_like(mu, dtype=float) / max(len(mu), 1)
    elif weight_mode == "inv_var":
        inv_var = 1.0 / np.maximum(sigma ** 2, 1e-8)
        w_raw = np.maximum(inv_var, 0.0)
        w = (w_raw / w_raw.sum()) if np.any(w_raw) else (np.ones_like(w_raw) / len(w_raw))
    else:
        raise ValueError(f"Unknown weight_mode: {weight_mode}")

    return CINTASModel(
        feature_cols=list(feature_cols),
        mu=mu,
        sigma=sigma,
        w=w,
        lambda_res=float(lambda_res),
    )


# -------------------------------------------------------------------------
# Fixed-point reference (Q-format) — optional helper for edge-style scoring.
# -------------------------------------------------------------------------

@dataclass(frozen=True)
class FixedPointConfig:
    q: int = 15  # Q15 default

    @property
    def scale(self) -> int:
        return 1 << self.q


@dataclass(frozen=True)
class FixedPointCINTAS:
    """A small fixed-point prototype.

    This is not meant to be bit-exact to any RTL; it is a *reference* that
    keeps the core arithmetic in integers.
    """
    feature_cols: list[str]
    mu_q: np.ndarray        # int
    gamma_q: np.ndarray     # int, approx 1/sigma in Qq
    w_q: np.ndarray         # int, weights in Qq (sum ~= 1.0)
    lambda_q: int           # int, lambda in Qq
    cfg: FixedPointConfig = FixedPointConfig()

    @classmethod
    def from_float_model(cls, model: CINTASModel, cfg: FixedPointConfig = FixedPointConfig()) -> "FixedPointCINTAS":
        q = cfg.q
        scale = cfg.scale
        mu_q = np.round(model.mu * scale).astype(np.int64)
        sigma_safe = np.where(model.sigma <= 1e-6, 1.0, model.sigma)
        gamma = 1.0 / sigma_safe
        gamma_q = np.round(gamma * scale).astype(np.int64)

        w_q = np.round(model.w * scale).astype(np.int64)
        lambda_q = int(round(float(model.lambda_res) * scale))

        return cls(
            feature_cols=list(model.feature_cols),
            mu_q=mu_q,
            gamma_q=gamma_q,
            w_q=w_q,
            lambda_q=lambda_q,
            cfg=cfg,
        )

    def score_sample_int(self, x: np.ndarray) -> int:
        """Score one sample; returns Qq value as int."""
        q = self.cfg.q
        scale = self.cfg.scale

        # x is float → quantize to Qq
        x_q = np.round(np.asarray(x, dtype=float) * scale).astype(np.int64)

        # z_q = (x - mu) * gamma  (all Qq)
        # (x_q - mu_q) is Qq; multiply by gamma_q (Qq) → Q2q; shift back to Qq.
        z_q = ((x_q - self.mu_q) * self.gamma_q) >> q  # Qq

        abs_z = np.abs(z_q)  # Qq

        # E1 = Σ w * |z|  (Qq*Qq→Q2q >>q →Qq)
        e1_q = int(np.sum((self.w_q * abs_z) >> q))

        # E2 = Σ w * z^2
        # z^2: Qq^2 → Q2q; multiply by w_q(Qq) → Q3q; >>2q → Qq
        z2_q2 = (z_q * z_q)  # Q2q
        e2_q = int(np.sum((self.w_q * z2_q2) >> (2 * q)))

        # score = (1-λ)E2 + λE1
        one_q = scale
        score_q = ((one_q - self.lambda_q) * e2_q + self.lambda_q * e1_q) >> q
        return int(score_q)

    def score_dataframe(self, df: pd.DataFrame) -> np.ndarray:
        X = df[self.feature_cols].to_numpy(dtype=float)
        scores = np.zeros(X.shape[0], dtype=np.int64)
        for i in range(X.shape[0]):
            scores[i] = self.score_sample_int(X[i])
        return scores
