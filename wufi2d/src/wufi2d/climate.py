"""Klimarandbedingungen (Aussen- und Innenklima).

Ein Klima liefert fuer eine Zeit ``t`` [s] den Zustand der angrenzenden Luft:
Temperatur, relative Feuchte, kurzwellige Einstrahlung auf die betrachtete
Oberflaeche, Schlagregenlast, Windgeschwindigkeit und optional die
Himmelstemperatur fuer den langwelligen Strahlungsaustausch.

Alle Klimaklassen sind zyklisch: Zeiten jenseits der hinterlegten Datenreihe
werden modulo der Periodenlaenge ausgewertet, sodass Mehrjahresrechnungen mit
einem Referenzjahr moeglich sind.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

SECONDS_PER_HOUR = 3600.0
SECONDS_PER_DAY = 86400.0
SECONDS_PER_YEAR = 365.0 * SECONDS_PER_DAY


@dataclass
class ClimateState:
    """Momentaner Luftzustand an einer Oberflaeche."""

    temperature: float = 20.0
    """Lufttemperatur [degC]."""

    rh: float = 0.5
    """Relative Luftfeuchte [-] (0..1)."""

    solar: float = 0.0
    """Kurzwellige Einstrahlung auf die Oberflaeche [W/m2]."""

    rain: float = 0.0
    """Schlagregenlast auf die Oberflaeche [kg/(m2 s)]."""

    wind: float = 0.0
    """Windgeschwindigkeit [m/s]."""

    sky_temperature: Optional[float] = None
    """Wirksame Himmelstemperatur [degC] fuer langwellige Abstrahlung."""


class Climate:
    """Basisklasse. Unterklassen implementieren :meth:`arrays`."""

    period: float = SECONDS_PER_YEAR

    def arrays(self, t: np.ndarray) -> Dict[str, np.ndarray]:
        raise NotImplementedError

    # -- Komfortzugriffe -------------------------------------------------
    def state(self, t: float) -> ClimateState:
        data = self.arrays(np.asarray([float(t)]))
        sky = data.get("sky_temperature")
        return ClimateState(
            temperature=float(data["temperature"][0]),
            rh=float(data["rh"][0]),
            solar=float(data.get("solar", np.zeros(1))[0]),
            rain=float(data.get("rain", np.zeros(1))[0]),
            wind=float(data.get("wind", np.zeros(1))[0]),
            sky_temperature=None if sky is None else float(sky[0]),
        )

    def series(self, times: Sequence[float]) -> Dict[str, np.ndarray]:
        """Alle Groessen fuer ein Zeitarray [s]."""
        t = np.asarray(times, dtype=float)
        data = self.arrays(t)
        result = {
            "temperature": np.asarray(data["temperature"], dtype=float),
            "rh": np.clip(np.asarray(data["rh"], dtype=float), 1e-4, 1.0),
            "solar": np.asarray(data.get("solar", np.zeros_like(t)), dtype=float),
            "rain": np.asarray(data.get("rain", np.zeros_like(t)), dtype=float),
            "wind": np.asarray(data.get("wind", np.zeros_like(t)), dtype=float),
        }
        if data.get("sky_temperature") is not None:
            result["sky_temperature"] = np.asarray(data["sky_temperature"], dtype=float)
        return result

    def describe(self) -> str:
        return self.__class__.__name__


class ConstantClimate(Climate):
    """Konstantes Klima (z.B. fuer Norm-Testfaelle und stationaere Rechnungen)."""

    def __init__(self, temperature: float, rh: float, solar: float = 0.0,
                 rain: float = 0.0, wind: float = 0.0,
                 sky_temperature: Optional[float] = None) -> None:
        self.temperature = float(temperature)
        self.rh = float(rh)
        self.solar = float(solar)
        self.rain = float(rain)
        self.wind = float(wind)
        self.sky_temperature = sky_temperature

    def arrays(self, t: np.ndarray) -> Dict[str, np.ndarray]:
        ones = np.ones_like(np.asarray(t, dtype=float))
        data = {
            "temperature": self.temperature * ones,
            "rh": self.rh * ones,
            "solar": self.solar * ones,
            "rain": self.rain * ones,
            "wind": self.wind * ones,
        }
        if self.sky_temperature is not None:
            data["sky_temperature"] = self.sky_temperature * ones
        return data

    def describe(self) -> str:
        return f"konstant {self.temperature:.1f} degC / {self.rh * 100:.0f} % rF"


class SineClimate(Climate):
    """Sinusfoermiges Klima mit Jahres- und Tagesgang.

    ``phase_days`` verschiebt den Jahresgang; mit dem Standardwert 0 liegt das
    Minimum der Temperatur am 1. Januar (Zeit ``t = 0``).
    """

    def __init__(self,
                 mean_temperature: float = 10.0,
                 amplitude_temperature: float = 10.0,
                 mean_rh: float = 0.75,
                 amplitude_rh: float = 0.1,
                 daily_temperature_amplitude: float = 0.0,
                 daily_rh_amplitude: float = 0.0,
                 phase_days: float = 0.0,
                 solar_peak: float = 0.0,
                 rain: float = 0.0,
                 wind: float = 0.0) -> None:
        self.mean_temperature = float(mean_temperature)
        self.amplitude_temperature = float(amplitude_temperature)
        self.mean_rh = float(mean_rh)
        self.amplitude_rh = float(amplitude_rh)
        self.daily_temperature_amplitude = float(daily_temperature_amplitude)
        self.daily_rh_amplitude = float(daily_rh_amplitude)
        self.phase_days = float(phase_days)
        self.solar_peak = float(solar_peak)
        self.rain = float(rain)
        self.wind = float(wind)

    def arrays(self, t: np.ndarray) -> Dict[str, np.ndarray]:
        t = np.asarray(t, dtype=float)
        annual = 2.0 * math.pi * (t / SECONDS_PER_YEAR) - math.pi / 2.0
        annual = annual - 2.0 * math.pi * self.phase_days / 365.0
        daily = 2.0 * math.pi * (t / SECONDS_PER_DAY) - math.pi / 2.0
        temperature = (self.mean_temperature
                       + self.amplitude_temperature * np.sin(annual)
                       + self.daily_temperature_amplitude * np.sin(daily))
        # Feuchte laeuft gegenphasig zur Temperatur (feuchter Winter).
        rh = (self.mean_rh
              - self.amplitude_rh * np.sin(annual)
              - self.daily_rh_amplitude * np.sin(daily))
        solar = self.solar_peak * np.clip(np.sin(2.0 * math.pi * t / SECONDS_PER_DAY
                                                 - math.pi / 2.0), 0.0, None)
        return {
            "temperature": temperature,
            "rh": np.clip(rh, 0.01, 1.0),
            "solar": solar,
            "rain": self.rain * np.ones_like(t),
            "wind": self.wind * np.ones_like(t),
        }

    def describe(self) -> str:
        return (f"Sinus {self.mean_temperature:.1f} +/- {self.amplitude_temperature:.1f} degC, "
                f"{self.mean_rh * 100:.0f} +/- {self.amplitude_rh * 100:.0f} % rF")


class TabularClimate(Climate):
    """Klima aus einer Zeitreihe (z.B. Testreferenzjahr, Messdaten).

    Parameter
    ---------
    hours:
        Zeitstuetzstellen [h], monoton steigend.
    temperature, rh:
        Lufttemperatur [degC] und relative Feuchte (0..1 oder 0..100).
    solar:
        Kurzwellige Einstrahlung auf die betrachtete Oberflaeche [W/m2].
    rain:
        Schlagregen auf die Oberflaeche. Einheit ueber ``rain_unit``:
        ``"kg/m2s"`` oder ``"mm/h"`` (= kg/(m2 h)).
    period_hours:
        Periodenlaenge fuer die zyklische Fortsetzung; ohne Angabe wird die
        letzte Stuetzstelle plus ein Zeitschritt verwendet.
    """

    def __init__(self,
                 hours: Sequence[float],
                 temperature: Sequence[float],
                 rh: Sequence[float],
                 solar: Optional[Sequence[float]] = None,
                 rain: Optional[Sequence[float]] = None,
                 wind: Optional[Sequence[float]] = None,
                 sky_temperature: Optional[Sequence[float]] = None,
                 rain_unit: str = "kg/m2s",
                 period_hours: Optional[float] = None,
                 name: str = "") -> None:
        self.hours = np.asarray(hours, dtype=float)
        if self.hours.ndim != 1 or len(self.hours) < 2:
            raise ValueError("Klimadatei braucht mindestens zwei Zeitstuetzstellen")
        if np.any(np.diff(self.hours) <= 0):
            raise ValueError("Zeitstuetzstellen muessen streng monoton steigen")
        self.temperature = np.asarray(temperature, dtype=float)
        rh_array = np.asarray(rh, dtype=float)
        if rh_array.max() > 1.5:  # Prozentangaben erkennen
            rh_array = rh_array / 100.0
        self.rh = np.clip(rh_array, 1e-4, 1.0)
        n = len(self.hours)
        for label, values in (("temperature", self.temperature), ("rh", self.rh)):
            if len(values) != n:
                raise ValueError(f"'{label}' hat {len(values)} Werte, erwartet {n}")
        self.solar = self._optional(solar, n)
        rain_values = self._optional(rain, n)
        if rain_unit in ("mm/h", "kg/m2h", "l/m2h"):
            rain_values = rain_values / SECONDS_PER_HOUR
        elif rain_unit not in ("kg/m2s", "kg/(m2 s)"):
            raise ValueError(f"Unbekannte Regen-Einheit: {rain_unit}")
        self.rain = rain_values
        self.wind = self._optional(wind, n)
        self.sky_temperature = (None if sky_temperature is None
                                else self._optional(sky_temperature, n))
        self.name = name
        step = float(self.hours[1] - self.hours[0])
        period_h = (float(period_hours) if period_hours
                    else float(self.hours[-1] - self.hours[0] + step))
        self.period = period_h * SECONDS_PER_HOUR

        # Stuetzstellen um den Periodenschluss ergaenzen: damit genuegt ein
        # einfaches np.interp (die Variante mit ``period=`` sortiert intern neu
        # und ist in der Zeitschleife deutlich langsamer).
        self._xp = np.append(self.hours, self.hours[0] + period_h)
        self._fp = {
            "temperature": np.append(self.temperature, self.temperature[0]),
            "rh": np.append(self.rh, self.rh[0]),
            "solar": np.append(self.solar, self.solar[0]),
            "rain": np.append(self.rain, self.rain[0]),
            "wind": np.append(self.wind, self.wind[0]),
        }
        if self.sky_temperature is not None:
            self._fp["sky_temperature"] = np.append(self.sky_temperature,
                                                    self.sky_temperature[0])

    @staticmethod
    def _optional(values: Optional[Sequence[float]], n: int) -> np.ndarray:
        if values is None:
            return np.zeros(n, dtype=float)
        array = np.asarray(values, dtype=float)
        if len(array) != n:
            raise ValueError(f"Zeitreihe hat {len(array)} Werte, erwartet {n}")
        return array

    def arrays(self, t: np.ndarray) -> Dict[str, np.ndarray]:
        t = np.asarray(t, dtype=float)
        h = self.hours[0] + np.mod(t, self.period) / SECONDS_PER_HOUR
        return {key: np.interp(h, self._xp, values) for key, values in self._fp.items()}

    def describe(self) -> str:
        label = self.name or "Zeitreihe"
        return (f"{label}: {len(self.hours)} Werte, Periode "
                f"{self.period / SECONDS_PER_DAY:.0f} d, "
                f"T {self.temperature.min():.1f}..{self.temperature.max():.1f} degC")

    # -- Auswertung ------------------------------------------------------
    def daily_mean_temperature(self) -> np.ndarray:
        """Tagesmittelwerte der Temperatur [degC]."""
        per_day = max(int(round(24.0 / (self.hours[1] - self.hours[0]))), 1)
        usable = (len(self.temperature) // per_day) * per_day
        return self.temperature[:usable].reshape(-1, per_day).mean(axis=1)


def synthetic_year(mean_temperature: float = 9.0,
                   amplitude_temperature: float = 9.5,
                   mean_rh: float = 0.78,
                   amplitude_rh: float = 0.09,
                   daily_temperature_amplitude: float = 3.0,
                   solar_peak: float = 350.0,
                   annual_rain: float = 350.0,
                   rain_interval_days: float = 5.0,
                   rain_duration_hours: float = 6.0,
                   wind: float = 3.0,
                   name: str = "synthetisches Jahr") -> TabularClimate:
    """Stundenwerte eines Referenzjahres ohne Klimadatei erzeugen.

    Gedacht fuer erste Abschaetzungen und Beispiele -- fuer Nachweise ist ein
    gemessenes Testreferenzjahr (TRY, WAC, Messdaten) einzulesen, siehe
    :func:`read_climate_csv`.

    Im Gegensatz zu :class:`SineClimate` faellt der Regen nicht dauernd,
    sondern in Ereignissen: alle ``rain_interval_days`` Tage fuer
    ``rain_duration_hours`` Stunden. Die Intensitaet wird so skaliert, dass die
    Jahressumme ``annual_rain`` [mm/a] als Schlagregenlast *auf die betrachtete
    Flaeche* erreicht wird. Typische Schlagregenlasten auf Fassaden liegen je
    nach Exposition bei etwa 100-600 mm/a -- deutlich unter dem
    Horizontalniederschlag.
    """
    hours = np.arange(8760.0)
    annual = 2.0 * np.pi * hours / 8760.0 - np.pi / 2.0
    daily = 2.0 * np.pi * hours / 24.0 - np.pi / 2.0

    temperature = (mean_temperature + amplitude_temperature * np.sin(annual)
                   + daily_temperature_amplitude * np.sin(daily))
    rh = np.clip(mean_rh - amplitude_rh * np.sin(annual)
                 - 0.05 * np.sin(daily), 0.2, 0.99)

    # Einstrahlung: Tagesgang, im Sommer hoeher
    season = 0.55 + 0.45 * np.sin(annual)
    solar = solar_peak * season * np.clip(np.sin(daily), 0.0, None)

    # Regenereignisse
    rain = np.zeros_like(hours)
    interval = max(int(round(rain_interval_days * 24.0)), 1)
    duration = max(int(round(rain_duration_hours)), 1)
    starts = np.arange(0, len(hours), interval)
    for index, start in enumerate(starts):
        offset = (start + 7 * index) % 24  # Ereignisse zu wechselnden Tageszeiten
        begin = int(start + offset)
        rain[begin:begin + duration] = 1.0
    event_hours = float(rain.sum())
    if event_hours > 0.0 and annual_rain > 0.0:
        rain *= annual_rain / event_hours  # mm/h waehrend der Ereignisse
    else:
        rain[:] = 0.0

    # Waehrend Regen ist es feuchter und weniger sonnig
    rh = np.where(rain > 0.0, np.minimum(rh + 0.15, 0.99), rh)
    solar = np.where(rain > 0.0, 0.25 * solar, solar)

    return TabularClimate(hours=hours, temperature=temperature, rh=rh, solar=solar,
                          rain=rain, wind=np.full_like(hours, float(wind)),
                          rain_unit="mm/h", period_hours=8760.0, name=name)


class InteriorClimateFromExterior(Climate):
    """Innenklima als Funktion des Aussenklimas.

    Umsetzung des in EN 15026 / DIN 4108-3 gebraeuchlichen Ansatzes: die
    Innentemperatur und die Innenluftfeuchte werden aus dem gleitenden
    Tagesmittel der Aussentemperatur abgeleitet.

    Standardparameter (normale Feuchtelast)::

        T_i  = 20 degC              fuer T_e <= 10 degC
        T_i  = 20 + (T_e - 10)/2    fuer 10 degC < T_e < 20 degC
        T_i  = 25 degC              fuer T_e >= 20 degC

        rF_i = 30 %                 fuer T_e <= -10 degC
        rF_i linear                 zwischen -10 degC und +20 degC
        rF_i = 60 %                 fuer T_e >= 20 degC

    Mit ``moisture_load="hoch"`` werden die Feuchtewerte um 10 Prozentpunkte
    angehoben (40 % bis 70 %).

    Hinweis: Die Zahlenwerte sind gegen die jeweils gueltige Normfassung bzw.
    den nationalen Anhang zu pruefen; alle Grenzwerte sind als Parameter
    zugaenglich.
    """

    def __init__(self,
                 exterior: Climate,
                 moisture_load: str = "normal",
                 temperature_range: Sequence[float] = (10.0, 20.0),
                 interior_temperature_range: Sequence[float] = (20.0, 25.0),
                 rh_reference_range: Sequence[float] = (-10.0, 20.0),
                 rh_range: Optional[Sequence[float]] = None,
                 averaging_days: float = 1.0) -> None:
        self.exterior = exterior
        self.moisture_load = moisture_load
        self.temperature_range = tuple(float(v) for v in temperature_range)
        self.interior_temperature_range = tuple(float(v) for v in interior_temperature_range)
        self.rh_reference_range = tuple(float(v) for v in rh_reference_range)
        if rh_range is None:
            offset = 0.10 if moisture_load.lower() in ("hoch", "high") else 0.0
            rh_range = (0.30 + offset, 0.60 + offset)
        self.rh_range = tuple(float(v) for v in rh_range)
        self.averaging_days = float(averaging_days)
        self.period = getattr(exterior, "period", SECONDS_PER_YEAR)
        self._mean_table = None

    def _build_mean_table(self):
        """Gleitendes Tagesmittel einmalig ueber eine Periode vorberechnen.

        Ohne diese Tabelle muesste je Zeitschritt das Aussenklima 24-mal
        ausgewertet werden -- in der Zeitschleife der teuerste Posten.
        """
        hours = max(int(round(self.period / SECONDS_PER_HOUR)), 2)
        times = np.arange(hours, dtype=float) * SECONDS_PER_HOUR
        temperature = np.asarray(self.exterior.arrays(times)["temperature"], dtype=float)
        window = max(int(round(self.averaging_days * 24.0)), 1)
        if window > 1:
            # zyklisch nachlaufendes Mittel
            padded = np.concatenate([temperature[-(window - 1):], temperature])
            kernel = np.ones(window) / window
            mean = np.convolve(padded, kernel, mode="valid")
        else:
            mean = temperature
        self._mean_table = (np.append(times, self.period),
                            np.append(mean, mean[0]))
        return self._mean_table

    def _mean_exterior_temperature(self, t: np.ndarray) -> np.ndarray:
        """Gleitendes Tagesmittel der Aussentemperatur."""
        if self.averaging_days <= 0:
            return self.exterior.arrays(t)["temperature"]
        table = self._mean_table or self._build_mean_table()
        return np.interp(np.mod(np.asarray(t, dtype=float), self.period), *table)

    def arrays(self, t: np.ndarray) -> Dict[str, np.ndarray]:
        t = np.asarray(t, dtype=float)
        t_e = self._mean_exterior_temperature(t)
        t_lo, t_hi = self.temperature_range
        ti_lo, ti_hi = self.interior_temperature_range
        temperature = np.interp(t_e, [t_lo, t_hi], [ti_lo, ti_hi])
        rh = np.interp(t_e, list(self.rh_reference_range), list(self.rh_range))
        zeros = np.zeros_like(t)
        return {"temperature": temperature, "rh": np.clip(rh, 0.01, 1.0),
                "solar": zeros, "rain": zeros, "wind": zeros}

    def describe(self) -> str:
        return (f"Innenklima aus Aussenklima ({self.moisture_load}e Feuchtelast, "
                f"{self.rh_range[0] * 100:.0f}-{self.rh_range[1] * 100:.0f} % rF)")


# ---------------------------------------------------------------------------
# Schlagregen
# ---------------------------------------------------------------------------

def driving_rain(horizontal_rain, wind_speed, r1: float = 0.0, r2: float = 0.07,
                 unit: str = "mm/h"):
    """Schlagregenlast auf eine vertikale Flaeche.

    Ueblicher Ansatz (vgl. EN ISO 15927-3, WUFI-Regenlastmodell)::

        R_wdr = (R1 + R2 * v) * R_h

    ``r1`` beruecksichtigt frei fallenden Regen (fuer geneigte Flaechen),
    ``r2`` [s/m] die Windabhaengigkeit. Rueckgabe in [kg/(m2 s)].
    """
    rain = np.asarray(horizontal_rain, dtype=float)
    if unit in ("mm/h", "kg/m2h", "l/m2h"):
        rain = rain / SECONDS_PER_HOUR
    elif unit not in ("kg/m2s", "kg/(m2 s)"):
        raise ValueError(f"Unbekannte Regen-Einheit: {unit}")
    return np.maximum((r1 + r2 * np.asarray(wind_speed, dtype=float)) * rain, 0.0)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

_ALIASES = {
    "temperature": ("temperature", "temp", "t", "te", "ta", "tluft", "lufttemperatur",
                    "temperatur", "t_air", "airtemp", "drybulb"),
    "rh": ("rh", "relhum", "relativehumidity", "feuchte", "rf", "phi",
           "relativefeuchte", "humidity"),
    "solar": ("solar", "radiation", "globalradiation", "strahlung", "isol",
              "irradiance", "globalstrahlung"),
    "rain": ("rain", "regen", "precipitation", "niederschlag", "rainfall"),
    "wind": ("wind", "windspeed", "windgeschwindigkeit", "v"),
    "hours": ("hours", "hour", "time", "zeit", "stunde", "h"),
    "sky_temperature": ("skytemperature", "tsky", "himmelstemperatur"),
}


def _normalise(key: str) -> str:
    cleaned = "".join(ch for ch in key.lower() if ch.isalnum())
    for field_name, aliases in _ALIASES.items():
        if cleaned in aliases:
            return field_name
    return cleaned


def read_climate_csv(path, delimiter: Optional[str] = None,
                     rain_unit: str = "mm/h", period_hours: Optional[float] = None,
                     column_map: Optional[Dict[str, str]] = None) -> TabularClimate:
    """Klimadatei (CSV/TSV mit Kopfzeile) einlesen.

    Erkannt werden gaengige deutsche und englische Spaltennamen
    (Temperatur/Temperature, rF/RH, Strahlung/Solar, Regen/Rain, Wind).
    Fehlt eine Zeitspalte, wird ein Stundenraster angenommen.
    ``column_map`` erlaubt eine explizite Zuordnung ``{"temperature": "T_e"}``.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t ").delimiter
        except csv.Error:
            delimiter = ","
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter,
                            skipinitialspace=True)
    if not reader.fieldnames:
        raise ValueError(f"{path}: keine Kopfzeile gefunden")

    inverse = {v: k for k, v in (column_map or {}).items()}
    columns: Dict[str, List[float]] = {}
    for name in reader.fieldnames:
        if name is None:
            continue
        key = inverse.get(name.strip(), _normalise(name))
        columns[key] = []
    for row in reader:
        for name in reader.fieldnames:
            if name is None:
                continue
            key = inverse.get(name.strip(), _normalise(name))
            raw = (row.get(name) or "").strip().replace(",", ".")
            try:
                columns[key].append(float(raw))
            except ValueError:
                columns[key].append(math.nan)

    if "temperature" not in columns or "rh" not in columns:
        raise ValueError(
            f"{path}: Spalten fuer Temperatur und relative Feuchte nicht erkannt "
            f"(gefunden: {sorted(columns)}). column_map verwenden."
        )
    n = len(columns["temperature"])
    hours = columns.get("hours") or list(range(n))
    return TabularClimate(
        hours=hours,
        temperature=columns["temperature"],
        rh=columns["rh"],
        solar=columns.get("solar"),
        rain=columns.get("rain"),
        wind=columns.get("wind"),
        sky_temperature=columns.get("sky_temperature"),
        rain_unit=rain_unit,
        period_hours=period_hours,
        name=path.name,
    )


def climate_from_dict(data: Dict) -> Climate:
    """Klima aus einem JSON-Dictionary erzeugen (siehe :mod:`wufi2d.model`)."""
    kind = str(data.get("type", "constant")).lower()
    if kind in ("constant", "konstant"):
        return ConstantClimate(**{k: v for k, v in data.items() if k != "type"})
    if kind in ("sine", "sinus"):
        return SineClimate(**{k: v for k, v in data.items() if k != "type"})
    if kind in ("csv", "file", "datei"):
        options = {k: v for k, v in data.items() if k not in ("type", "path")}
        return read_climate_csv(data["path"], **options)
    if kind in ("table", "tabelle"):
        return TabularClimate(**{k: v for k, v in data.items() if k != "type"})
    if kind in ("interior", "innen", "en15026"):
        exterior = climate_from_dict(data["exterior"])
        options = {k: v for k, v in data.items() if k not in ("type", "exterior")}
        return InteriorClimateFromExterior(exterior, **options)
    raise ValueError(f"Unbekannter Klimatyp: {kind}")
