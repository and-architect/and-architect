"""Tests der Klimarandbedingungen."""

from __future__ import annotations

import numpy as np
import pytest

from wufi2d.climate import (ConstantClimate, InteriorClimateFromExterior, SineClimate,
                            TabularClimate, climate_from_dict, driving_rain,
                            read_climate_csv)

DAY = 86400.0
YEAR = 365.0 * DAY


def test_constant_climate():
    climate = ConstantClimate(21.0, 0.55)
    state = climate.state(12345.0)
    assert state.temperature == 21.0
    assert state.rh == 0.55
    series = climate.series([0.0, DAY, YEAR])
    assert np.all(series["temperature"] == 21.0)
    assert series["rh"].shape == (3,)


def test_sine_climate_annual_cycle():
    climate = SineClimate(mean_temperature=10.0, amplitude_temperature=10.0,
                          mean_rh=0.75, amplitude_rh=0.1)
    winter = climate.state(0.0)             # Jahresbeginn = Minimum
    summer = climate.state(YEAR / 2.0)
    assert winter.temperature == pytest.approx(0.0, abs=0.1)
    assert summer.temperature == pytest.approx(20.0, abs=0.1)
    # Feuchte laeuft gegenphasig
    assert winter.rh > summer.rh
    # Periodizitaet
    assert climate.state(YEAR).temperature == pytest.approx(winter.temperature, abs=1e-6)


def test_sine_climate_daily_cycle_and_solar():
    climate = SineClimate(mean_temperature=15.0, amplitude_temperature=0.0,
                          daily_temperature_amplitude=5.0, solar_peak=800.0)
    midnight = climate.state(0.0)
    noon = climate.state(DAY / 2.0)
    assert midnight.temperature == pytest.approx(10.0, abs=1e-6)
    assert noon.temperature == pytest.approx(20.0, abs=1e-6)
    assert noon.solar == pytest.approx(800.0, rel=1e-6)
    assert midnight.solar == pytest.approx(0.0)


def test_tabular_climate_interpolation_and_period():
    climate = TabularClimate(hours=[0.0, 1.0, 2.0, 3.0],
                             temperature=[0.0, 10.0, 20.0, 30.0],
                             rh=[50.0, 60.0, 70.0, 80.0])  # Prozentangaben
    assert climate.rh.max() <= 1.0  # automatisch erkannt
    assert climate.state(1800.0).temperature == pytest.approx(5.0)
    assert climate.state(3600.0).rh == pytest.approx(0.6)
    # zyklische Fortsetzung nach 4 h
    assert climate.state(4 * 3600.0).temperature == pytest.approx(0.0, abs=1e-9)


def test_tabular_climate_rain_unit_conversion():
    climate = TabularClimate(hours=[0.0, 1.0], temperature=[5.0, 5.0], rh=[0.9, 0.9],
                             rain=[3.6, 3.6], rain_unit="mm/h")
    assert climate.state(0.0).rain == pytest.approx(1e-3)  # 3.6 mm/h = 1e-3 kg/m2s


def test_tabular_climate_rejects_inconsistent_length():
    with pytest.raises(ValueError):
        TabularClimate(hours=[0.0, 1.0, 2.0], temperature=[1.0, 2.0], rh=[0.5, 0.5])


def test_interior_climate_from_exterior_en15026_shape():
    interior = InteriorClimateFromExterior(ConstantClimate(-10.0, 0.9),
                                           averaging_days=0.0)
    state = interior.state(0.0)
    assert state.temperature == pytest.approx(20.0)
    assert state.rh == pytest.approx(0.30, abs=1e-9)

    warm = InteriorClimateFromExterior(ConstantClimate(25.0, 0.6), averaging_days=0.0)
    assert warm.state(0.0).temperature == pytest.approx(25.0)
    assert warm.state(0.0).rh == pytest.approx(0.60, abs=1e-9)

    mid = InteriorClimateFromExterior(ConstantClimate(15.0, 0.7), averaging_days=0.0)
    assert mid.state(0.0).temperature == pytest.approx(22.5)
    assert mid.state(0.0).rh == pytest.approx(0.30 + 25.0 / 30.0 * 0.30, abs=1e-6)


def test_interior_climate_high_moisture_load():
    normal = InteriorClimateFromExterior(ConstantClimate(20.0, 0.6), averaging_days=0.0)
    high = InteriorClimateFromExterior(ConstantClimate(20.0, 0.6),
                                       moisture_load="hoch", averaging_days=0.0)
    assert high.state(0.0).rh == pytest.approx(normal.state(0.0).rh + 0.10, abs=1e-9)


def test_interior_climate_uses_running_daily_mean():
    exterior = SineClimate(mean_temperature=5.0, amplitude_temperature=0.0,
                           daily_temperature_amplitude=15.0)
    interior = InteriorClimateFromExterior(exterior, averaging_days=1.0)
    # Das Tagesmittel ist konstant -> Innenklima schwankt kaum
    values = [interior.state(t).temperature for t in np.linspace(0.0, DAY, 12)]
    assert max(values) - min(values) < 0.5


def test_driving_rain_model():
    # (R1 + R2*v) * R_h, hier 0.07 s/m * 4 m/s * 1 mm/h
    load = driving_rain(1.0, 4.0, r1=0.0, r2=0.07, unit="mm/h")
    assert float(load) == pytest.approx(0.07 * 4.0 * 1.0 / 3600.0)
    assert float(driving_rain(0.0, 10.0)) == 0.0


def test_read_climate_csv_german_headers(tmp_path):
    path = tmp_path / "klima.csv"
    path.write_text(
        "Zeit;Temperatur;rF;Strahlung;Regen\n"
        "0;-2,5;85;0;0\n"
        "1;-1,5;83;120;0,5\n"
        "2;0,5;80;350;0\n",
        encoding="utf-8")
    climate = read_climate_csv(path, rain_unit="mm/h")
    assert len(climate.hours) == 3
    assert climate.temperature[0] == pytest.approx(-2.5)
    assert climate.rh[0] == pytest.approx(0.85)
    assert climate.solar[2] == pytest.approx(350.0)
    assert climate.rain[1] == pytest.approx(0.5 / 3600.0)


def test_read_climate_csv_english_headers(tmp_path):
    path = tmp_path / "weather.csv"
    path.write_text("hour,temperature,rh,solar\n0,10,0.6,0\n1,12,0.55,200\n",
                    encoding="utf-8")
    climate = read_climate_csv(path)
    assert climate.temperature[1] == pytest.approx(12.0)
    assert climate.rh[1] == pytest.approx(0.55)


def test_read_climate_csv_requires_known_columns(tmp_path):
    path = tmp_path / "unklar.csv"
    path.write_text("a;b\n1;2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_climate_csv(path)


def test_read_climate_csv_with_column_map(tmp_path):
    path = tmp_path / "custom.csv"
    path.write_text("t_e;phi_e\n5;0.7\n6;0.72\n", encoding="utf-8")
    climate = read_climate_csv(path, column_map={"temperature": "t_e", "rh": "phi_e"})
    assert climate.temperature[0] == pytest.approx(5.0)


def test_climate_from_dict_roundtrip():
    climate = climate_from_dict({"type": "sine", "mean_temperature": 8.0,
                                 "amplitude_temperature": 9.0})
    assert isinstance(climate, SineClimate)
    interior = climate_from_dict({"type": "interior",
                                  "exterior": {"type": "constant",
                                               "temperature": 0.0, "rh": 0.9},
                                  "averaging_days": 0.0})
    assert interior.state(0.0).temperature == pytest.approx(20.0)
    with pytest.raises(ValueError):
        climate_from_dict({"type": "unbekannt"})


def test_daily_mean_temperature():
    hours = list(range(48))
    temperature = [0.0] * 24 + [10.0] * 24
    climate = TabularClimate(hours=hours, temperature=temperature, rh=[0.5] * 48)
    means = climate.daily_mean_temperature()
    assert means.tolist() == pytest.approx([0.0, 10.0])


def test_synthetic_year_totals_and_shape():
    from wufi2d.climate import synthetic_year

    climate = synthetic_year(mean_temperature=9.0, amplitude_temperature=9.5,
                             annual_rain=350.0, rain_interval_days=5.0,
                             rain_duration_hours=6.0)
    assert len(climate.hours) == 8760
    assert climate.period == pytest.approx(8760 * 3600.0)
    assert climate.temperature.mean() == pytest.approx(9.0, abs=0.2)
    # Jahressumme des Schlagregens trifft die Vorgabe
    assert float(climate.rain.sum() * 3600.0) == pytest.approx(350.0, rel=1e-9)
    # Regen faellt in Ereignissen, nicht dauernd
    regenstunden = int((climate.rain > 0).sum())
    assert 0 < regenstunden < 1000
    # Waehrend Regen ist es feuchter
    assert climate.rh[climate.rain > 0].mean() > climate.rh[climate.rain == 0].mean()


def test_synthetic_year_without_rain():
    from wufi2d.climate import synthetic_year

    climate = synthetic_year(annual_rain=0.0)
    assert float(climate.rain.max()) == 0.0


def test_synthetic_year_is_periodic():
    from wufi2d.climate import synthetic_year

    climate = synthetic_year()
    assert climate.state(0.0).temperature == pytest.approx(
        climate.state(8760 * 3600.0).temperature, abs=1e-9)
