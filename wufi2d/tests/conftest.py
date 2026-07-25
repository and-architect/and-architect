"""Test-Konfiguration: Paketpfad und gemeinsame Hilfsmaterialien."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wufi2d.material import Material, MaterialLibrary  # noqa: E402


@pytest.fixture
def linear_material() -> Material:
    """Material mit konstanten Kennwerten (fuer analytische Vergleiche).

    Lineare Sorptionsisotherme -> dw/dphi = const, kein Fluessigtransport,
    kein Feuchtezuschlag der Waermeleitfaehigkeit.
    """
    return Material(
        name="Testmaterial linear",
        rho=1000.0,
        cp=1000.0,
        lambda_dry=1.0,
        mu=10.0,
        w_f=100.0,
        w_80=1.0,
        a_w=0.0,
        lambda_moisture_supplement=0.0,
        sorption_table=[[0.0, 0.0], [1.0, 100.0]],
    )


@pytest.fixture
def linear_library(linear_material) -> MaterialLibrary:
    return MaterialLibrary([linear_material])
