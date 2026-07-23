"""Decay-model fits: power-law (weighted LS with empirical variance)
and exponential. AIC-based model selection."""

from __future__ import annotations

import numpy as np
from scipy.optimize import curve_fit


def empirical_variance_per_bin(N: np.ndarray, y: np.ndarray, bin_width: int = 10) -> dict:
    """σ̂² per bin of N. Returns {bin_start: variance}."""
    bins = {}
    for start in range(int(N.min()), int(N.max()) + 1, bin_width):
        mask = (N >= start) & (N < start + bin_width)
        if mask.sum() > 1:
            bins[start] = float(np.var(y[mask], ddof=1))
        else:
            bins[start] = 1.0  # placeholder for sparse bins
    return bins


def _weights_from_bins(N: np.ndarray, bins: dict, bin_width: int) -> np.ndarray:
    w = np.ones_like(N, dtype=float)
    for i, n in enumerate(N):
        start = int(n // bin_width) * bin_width
        sigma2 = bins.get(start, 1.0)
        w[i] = 1.0 / max(sigma2, 1e-9)
    return w


def fit_powerlaw_weighted(N: np.ndarray, y: np.ndarray, bin_width: int = 10) -> dict:
    """info(N) = a · N^(-α) + ε. WLS with empirical per-bin σ̂²."""
    N = np.asarray(N, dtype=float)
    y = np.asarray(y, dtype=float)
    bins = empirical_variance_per_bin(N, y, bin_width)
    w = _weights_from_bins(N, bins, bin_width)

    def model(N, a, alpha):
        return a * N ** (-alpha)

    popt, pcov = curve_fit(
        model,
        N,
        y,
        sigma=1.0 / np.sqrt(w),
        p0=[1.0, 0.5],
        absolute_sigma=True,
        maxfev=5000,
    )
    a, alpha = popt
    resid = y - model(N, *popt)
    rss = float(np.sum(w * resid**2))
    n = len(y)
    k = 2  # a, alpha
    aic = n * np.log(rss / n) + 2 * k
    return {"a": float(a), "alpha": float(alpha), "rss": rss, "aic": float(aic), "n": n}


def fit_exponential(N: np.ndarray, y: np.ndarray) -> dict:
    """info(N) = c + (a − c) · exp(−N/τ) + ε. OLS."""
    N = np.asarray(N, dtype=float)
    y = np.asarray(y, dtype=float)

    def model(N, a, c, tau):
        return c + (a - c) * np.exp(-N / tau)

    popt, _ = curve_fit(model, N, y, p0=[y[0], y[-1], len(N) / 4], maxfev=5000)
    a, c, tau = popt
    resid = y - model(N, *popt)
    rss = float(np.sum(resid**2))
    n = len(y)
    k = 3  # a, c, tau
    aic = n * np.log(rss / n) + 2 * k
    return {
        "a": float(a),
        "c": float(c),
        "tau": float(tau),
        "rss": rss,
        "aic": float(aic),
        "n": n,
    }


def aic_model_selection(pl: dict, ex: dict) -> dict:
    """Akaike weights from two model fits."""
    aic_min = min(pl["aic"], ex["aic"])
    delta_pl = pl["aic"] - aic_min
    delta_ex = ex["aic"] - aic_min
    w_pl = np.exp(-0.5 * delta_pl)
    w_ex = np.exp(-0.5 * delta_ex)
    s = w_pl + w_ex
    return {
        "winner": "powerlaw" if pl["aic"] < ex["aic"] else "exponential",
        "weight_powerlaw": float(w_pl / s),
        "weight_exponential": float(w_ex / s),
        "delta_aic": float(abs(pl["aic"] - ex["aic"])),
    }
