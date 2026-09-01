#!/usr/bin/env python3
"""
Export a 30-day Garmin report to CSV.

The CSV contains exactly one row per calendar day (30 rows total).
Individual activities are used only to calculate daily running averages;
individual activity rows are not written to the CSV.

Install:
    py -m pip install --upgrade garminconnect curl_cffi

Run:
    py garmin_30_day_report.py
"""

from __future__ import annotations

import csv
import math
import statistics
import time
from datetime import date, datetime, timedelta
from getpass import getpass
from pathlib import Path
from typing import Any, Iterable

from garminconnect import Garmin

TOKEN_FOLDER = Path.home() / ".garminconnect"
REPORT_DAYS = 30


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def parse_end_date() -> date:
    """Ask for the final day in the report."""
    while True:
        text = input(
            "Enter the report end date (YYYY-MM-DD), "
            "or press Enter for today: "
        ).strip()

        if not text:
            return date.today()

        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            print("Please enter a real date in YYYY-MM-DD format.")


def login_to_garmin() -> Garmin:
    """Use saved tokens first, otherwise request credentials and MFA."""
    try:
        garmin = Garmin()
        garmin.login(str(TOKEN_FOLDER))
        print("Logged in using saved Garmin tokens.")
        return garmin
    except Exception:
        print("No valid saved login was found. Please sign in.")

    email = input("Garmin email address: ").strip()
    password = getpass("Garmin password: ")

    garmin = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("Garmin verification code: ").strip(),
    )
    garmin.login(str(TOKEN_FOLDER))
    print("Garmin login successful.")
    return garmin


def as_number(value: Any) -> float | None:
    """Convert a Garmin value to a finite float, or return None."""
    if value is None or isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return number if math.isfinite(number) else None


def first_number(data: Any, paths: Iterable[str]) -> float | None:
    """
    Return the first numeric value found.

    A path such as 'dailySleepDTO.sleepTimeSeconds' searches nested dictionaries.
    """
    if not isinstance(data, dict):
        return None

    for path in paths:
        current: Any = data

        for key in path.split("."):
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current[key]

        number = as_number(current)
        if number is not None:
            return number

    return None


def weighted_average(pairs: Iterable[tuple[float | None, float | None]]) -> float | None:
    """Calculate a weighted average while ignoring missing values."""
    numerator = 0.0
    denominator = 0.0

    for value, weight in pairs:
        if value is None:
            continue

        usable_weight = weight if weight is not None and weight > 0 else 1.0
        numerator += value * usable_weight
        denominator += usable_weight

    return numerator / denominator if denominator else None


def simple_average(values: Iterable[float | None]) -> float | None:
    usable = [value for value in values if value is not None]
    return statistics.fmean(usable) if usable else None


def round_or_blank(value: float | None, digits: int = 2) -> str | float:
    return "" if value is None else round(value, digits)


def seconds_to_hhmm(seconds: float | None) -> str:
    if seconds is None:
        return ""

    total_minutes = int(round(seconds / 60))
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def pace_seconds_to_text(seconds_per_km: float | None) -> str:
    if seconds_per_km is None or seconds_per_km <= 0:
        return ""

    rounded = int(round(seconds_per_km))
    minutes, seconds = divmod(rounded, 60)
    return f"{minutes}:{seconds:02d}"


def safe_call(label: str, function, *args) -> Any:
    """
    Call Garmin without aborting the whole export when one metric is unavailable.
    """
    try:
        return function(*args)
    except Exception as error:
        print(f"  Warning: {label} unavailable: {error}")
        return {}


# ---------------------------------------------------------------------------
# Running-data extraction
# ---------------------------------------------------------------------------

RUNNING_TYPES = {
    "running",
    "street_running",
    "track_running",
    "trail_running",
    "treadmill_running",
    "indoor_running",
    "ultra_run",
    "virtual_run",
}


def activity_type_key(activity: dict[str, Any]) -> str:
    activity_type = activity.get("activityType")

    if isinstance(activity_type, dict):
        return str(
            activity_type.get("typeKey")
            or activity_type.get("key")
            or ""
        ).lower()

    return str(activity_type or "").lower()


def is_running_activity(activity: dict[str, Any]) -> bool:
    key = activity_type_key(activity)
    return key in RUNNING_TYPES or "running" in key or key.endswith("_run")


def activity_day(activity: dict[str, Any]) -> str | None:
    for key in ("startTimeLocal", "startTimeGMT", "calendarDate"):
        value = activity.get(key)
        if isinstance(value, str) and len(value) >= 10:
            return value[:10]
    return None


def obtain_running_activities(
    garmin: Garmin,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """
    Download activity summaries in the requested dates and keep running only.

    Garmin has changed the accepted activity-type argument before, so the
    filtering is also performed locally.
    """
    start_text = start_date.isoformat()
    end_text = end_date.isoformat()

    print("Reading running summaries...")
    activities = safe_call(
        "activities",
        garmin.get_activities_by_date,
        start_text,
        end_text,
    )

    if not isinstance(activities, list):
        return []

    return [
        activity
        for activity in activities
        if isinstance(activity, dict) and is_running_activity(activity)
    ]


def running_values(activity: dict[str, Any]) -> dict[str, float | None]:
    """
    Extract summary values. Multiple aliases are included because Garmin has
    used different field names for different devices/API responses.
    """
    distance_m = first_number(
        activity,
        ("distance", "distanceMeters"),
    )
    elapsed_s = first_number(
        activity,
        ("elapsedDuration", "elapsedTime", "duration"),
    )

    ground_contact_ms = first_number(
        activity,
        (
            "avgGroundContactTime",
            "averageGroundContactTime",
            "avgGroundContactTimeMs",
        ),
    )
    cadence_spm = first_number(
        activity,
        (
            "averageRunningCadenceInStepsPerMinute",
            "averageRunningCadence",
            "avgRunningCadence",
            "averageCadence",
            "avgCadence",
        ),
    )
    heart_rate_bpm = first_number(
        activity,
        ("averageHR", "averageHeartRate", "avgHeartRate"),
    )
    stride_length_m = first_number(
        activity,
        (
            "avgStrideLength",
            "averageStrideLength",
            "avgStrideLengthMeters",
        ),
    )

    # Some Garmin responses store stride length in centimetres.
    if stride_length_m is not None and stride_length_m > 10:
        stride_length_m /= 100.0

    elapsed_pace_s_per_km = None
    if distance_m is not None and distance_m > 0 and elapsed_s is not None:
        elapsed_pace_s_per_km = elapsed_s / (distance_m / 1000.0)

    return {
        "distance_m": distance_m,
        "elapsed_s": elapsed_s,
        "ground_contact_ms": ground_contact_ms,
        "cadence_spm": cadence_spm,
        "heart_rate_bpm": heart_rate_bpm,
        "stride_length_m": stride_length_m,
        "elapsed_pace_s_per_km": elapsed_pace_s_per_km,
    }


def aggregate_running(
    activities: list[dict[str, Any]],
) -> dict[str, float | int | None]:
    values = [running_values(activity) for activity in activities]

    total_distance = sum(
        item["distance_m"] or 0.0
        for item in values
    )
    total_elapsed = sum(
        item["elapsed_s"] or 0.0
        for item in values
    )

    elapsed_pace = (
        total_elapsed / (total_distance / 1000.0)
        if total_distance > 0 and total_elapsed > 0
        else None
    )

    return {
        "run_count": len(activities),
        "running_distance_km": total_distance / 1000.0 if values else None,
        "running_elapsed_seconds": total_elapsed if values else None,
        "avg_ground_contact_ms": weighted_average(
            (item["ground_contact_ms"], item["distance_m"])
            for item in values
        ),
        "avg_cadence_spm": weighted_average(
            (item["cadence_spm"], item["distance_m"])
            for item in values
        ),
        "avg_running_heart_rate_bpm": weighted_average(
            (item["heart_rate_bpm"], item["elapsed_s"])
            for item in values
        ),
        "avg_elapsed_pace_s_per_km": elapsed_pace,
        "avg_stride_length_m": weighted_average(
            (item["stride_length_m"], item["distance_m"])
            for item in values
        ),
    }


# ---------------------------------------------------------------------------
# Daily health-data extraction
# ---------------------------------------------------------------------------

def extract_heart_rate(data: Any) -> tuple[float | None, float | None]:
    resting = first_number(
        data,
        (
            "restingHeartRate",
            "restingHeartRateValue",
            "statistics.restingHeartRate",
        ),
    )
    average = first_number(
        data,
        (
            "averageHeartRate",
            "avgHeartRate",
            "statistics.averageHeartRate",
        ),
    )

    # Fall back to the intraday HR samples when no daily average is supplied.
    if average is None and isinstance(data, dict):
        samples = data.get("heartRateValues")
        if isinstance(samples, list):
            readings: list[float] = []
            for sample in samples:
                if isinstance(sample, (list, tuple)) and len(sample) >= 2:
                    value = as_number(sample[1])
                    if value is not None and value > 0:
                        readings.append(value)
            average = simple_average(readings)

    return resting, average


def extract_stress(data: Any) -> float | None:
    value = first_number(
        data,
        (
            "overallStressLevel",
            "avgStressLevel",
            "averageStressLevel",
            "stressLevel",
        ),
    )
    if value is not None and value >= 0:
        return value

    if isinstance(data, dict):
        samples = data.get("stressValuesArray") or data.get("stressValues")
        if isinstance(samples, list):
            readings: list[float] = []
            for sample in samples:
                candidate = (
                    sample[1]
                    if isinstance(sample, (list, tuple)) and len(sample) >= 2
                    else sample
                )
                number = as_number(candidate)
                # Garmin uses negative values for unmeasurable/rest states.
                if number is not None and number >= 0:
                    readings.append(number)
            return simple_average(readings)

    return None


def extract_hrv(data: Any) -> tuple[float | None, float | None, str]:
    weekly = data.get("hrvSummary") if isinstance(data, dict) else None
    if not isinstance(weekly, dict):
        weekly = data if isinstance(data, dict) else {}

    nightly = first_number(
        weekly,
        (
            "lastNightAvg",
            "lastNightAverage",
            "nightlyAverage",
            "hrvValue",
        ),
    )
    baseline = first_number(
        weekly,
        (
            "weeklyAvg",
            "weeklyAverage",
            "baselineBalancedUpper",
            "baseline",
        ),
    )

    status = ""
    for key in ("status", "statusKey", "hrvStatus"):
        candidate = weekly.get(key)
        if candidate is not None:
            status = str(candidate)
            break

    return nightly, baseline, status


def extract_sleep(data: Any) -> dict[str, float | str | None]:
    dto = data.get("dailySleepDTO") if isinstance(data, dict) else None
    if not isinstance(dto, dict):
        dto = data if isinstance(data, dict) else {}

    sleep_seconds = first_number(
        dto,
        (
            "sleepTimeSeconds",
            "sleepDuration",
            "totalSleepSeconds",
        ),
    )
    deep_seconds = first_number(dto, ("deepSleepSeconds",))
    light_seconds = first_number(dto, ("lightSleepSeconds",))
    rem_seconds = first_number(dto, ("remSleepSeconds",))
    awake_seconds = first_number(dto, ("awakeSleepSeconds", "awakeTimeSeconds"))
    sleep_score = first_number(
        dto,
        (
            "sleepScores.overall.value",
            "sleepScore",
            "overallSleepScore",
        ),
    )

    start = dto.get("sleepStartTimestampLocal") or dto.get("sleepStartTimestampGMT")
    end = dto.get("sleepEndTimestampLocal") or dto.get("sleepEndTimestampGMT")

    return {
        "sleep_seconds": sleep_seconds,
        "deep_sleep_seconds": deep_seconds,
        "light_sleep_seconds": light_seconds,
        "rem_sleep_seconds": rem_seconds,
        "awake_seconds": awake_seconds,
        "sleep_score": sleep_score,
        "sleep_start": str(start or ""),
        "sleep_end": str(end or ""),
    }


def body_battery_readings(data: Any) -> list[float]:
    readings: list[float] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_lower = str(key).lower()
                if key_lower in {
                    "bodybatterylevel",
                    "bodybatteryvalue",
                    "charged",
                    "drained",
                }:
                    # charged/drained are not instantaneous levels.
                    if key_lower in {"charged", "drained"}:
                        continue
                    number = as_number(child)
                    if number is not None and 0 <= number <= 100:
                        readings.append(number)
                else:
                    visit(child)

        elif isinstance(value, list):
            # Common Garmin format: [timestamp, level]
            if len(value) >= 2 and not isinstance(value[1], (dict, list)):
                number = as_number(value[1])
                if number is not None and 0 <= number <= 100:
                    readings.append(number)
            else:
                for child in value:
                    visit(child)

    visit(data)
    return readings


def extract_body_battery(data: Any) -> tuple[float | None, float | None, float | None]:
    readings = body_battery_readings(data)

    if not readings and isinstance(data, dict):
        highest = first_number(data, ("highestValue", "maxBodyBattery"))
        lowest = first_number(data, ("lowestValue", "minBodyBattery"))
        average = first_number(data, ("averageValue", "avgBodyBattery"))
        return highest, lowest, average

    if not readings:
        return None, None, None

    return max(readings), min(readings), statistics.fmean(readings)


def collect_daily_health(garmin: Garmin, day: date) -> dict[str, Any]:
    day_text = day.isoformat()

    print(f"Reading health data for {day_text}...")

    heart_rate_data = safe_call(
        f"heart rate {day_text}",
        garmin.get_heart_rates,
        day_text,
    )
    stress_data = safe_call(
        f"stress {day_text}",
        garmin.get_stress_data,
        day_text,
    )
    hrv_data = safe_call(
        f"HRV {day_text}",
        garmin.get_hrv_data,
        day_text,
    )
    sleep_data = safe_call(
        f"sleep {day_text}",
        garmin.get_sleep_data,
        day_text,
    )
    body_battery_data = safe_call(
        f"Body Battery {day_text}",
        garmin.get_body_battery,
        day_text,
        day_text,
    )

    resting_hr, average_hr = extract_heart_rate(heart_rate_data)
    nightly_hrv, weekly_hrv, hrv_status = extract_hrv(hrv_data)
    highest_bb, lowest_bb, average_bb = extract_body_battery(body_battery_data)
    sleep = extract_sleep(sleep_data)

    return {
        "date": day_text,
        "row_type": "DAY",
        "daily_avg_heart_rate_bpm": average_hr,
        "resting_heart_rate_bpm": resting_hr,
        "avg_stress_level": extract_stress(stress_data),
        "nightly_hrv_ms": nightly_hrv,
        "weekly_avg_hrv_ms": weekly_hrv,
        "hrv_status": hrv_status,
        "body_battery_high": highest_bb,
        "body_battery_low": lowest_bb,
        "body_battery_average": average_bb,
        **sleep,
    }


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

CSV_FIELDS = [
    "date",
    "row_type",
    "run_count",
    "running_distance_km",
    "running_elapsed_time",
    "avg_ground_contact_ms",
    "avg_cadence_spm",
    "avg_running_heart_rate_bpm",
    "avg_elapsed_pace_min_per_km",
    "avg_stride_length_m",
    "daily_avg_heart_rate_bpm",
    "resting_heart_rate_bpm",
    "avg_stress_level",
    "nightly_hrv_ms",
    "weekly_avg_hrv_ms",
    "hrv_status",
    "body_battery_high",
    "body_battery_low",
    "body_battery_average",
    "sleep_duration",
    "sleep_score",
    "deep_sleep_duration",
    "light_sleep_duration",
    "rem_sleep_duration",
    "awake_duration",
    "sleep_start",
    "sleep_end",
]


def format_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": row.get("date", ""),
        "row_type": row.get("row_type", ""),
        "run_count": row.get("run_count", 0),
        "running_distance_km": round_or_blank(row.get("running_distance_km")),
        "running_elapsed_time": seconds_to_hhmm(
            row.get("running_elapsed_seconds")
        ),
        "avg_ground_contact_ms": round_or_blank(
            row.get("avg_ground_contact_ms"), 1
        ),
        "avg_cadence_spm": round_or_blank(row.get("avg_cadence_spm"), 1),
        "avg_running_heart_rate_bpm": round_or_blank(
            row.get("avg_running_heart_rate_bpm"), 1
        ),
        "avg_elapsed_pace_min_per_km": pace_seconds_to_text(
            row.get("avg_elapsed_pace_s_per_km")
        ),
        "avg_stride_length_m": round_or_blank(
            row.get("avg_stride_length_m"), 3
        ),
        "daily_avg_heart_rate_bpm": round_or_blank(
            row.get("daily_avg_heart_rate_bpm"), 1
        ),
        "resting_heart_rate_bpm": round_or_blank(
            row.get("resting_heart_rate_bpm"), 1
        ),
        "avg_stress_level": round_or_blank(row.get("avg_stress_level"), 1),
        "nightly_hrv_ms": round_or_blank(row.get("nightly_hrv_ms"), 1),
        "weekly_avg_hrv_ms": round_or_blank(row.get("weekly_avg_hrv_ms"), 1),
        "hrv_status": row.get("hrv_status", ""),
        "body_battery_high": round_or_blank(row.get("body_battery_high"), 1),
        "body_battery_low": round_or_blank(row.get("body_battery_low"), 1),
        "body_battery_average": round_or_blank(
            row.get("body_battery_average"), 1
        ),
        "sleep_duration": seconds_to_hhmm(row.get("sleep_seconds")),
        "sleep_score": round_or_blank(row.get("sleep_score"), 1),
        "deep_sleep_duration": seconds_to_hhmm(
            row.get("deep_sleep_seconds")
        ),
        "light_sleep_duration": seconds_to_hhmm(
            row.get("light_sleep_seconds")
        ),
        "rem_sleep_duration": seconds_to_hhmm(row.get("rem_sleep_seconds")),
        "awake_duration": seconds_to_hhmm(row.get("awake_seconds")),
        "sleep_start": row.get("sleep_start", ""),
        "sleep_end": row.get("sleep_end", ""),
    }


def make_period_summary(
    daily_rows: list[dict[str, Any]],
    running_summary: dict[str, Any],
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    return {
        "date": f"{start_date.isoformat()} to {end_date.isoformat()}",
        "row_type": "PERIOD_SUMMARY",
        **running_summary,
        "daily_avg_heart_rate_bpm": simple_average(
            row.get("daily_avg_heart_rate_bpm") for row in daily_rows
        ),
        "resting_heart_rate_bpm": simple_average(
            row.get("resting_heart_rate_bpm") for row in daily_rows
        ),
        "avg_stress_level": simple_average(
            row.get("avg_stress_level") for row in daily_rows
        ),
        "nightly_hrv_ms": simple_average(
            row.get("nightly_hrv_ms") for row in daily_rows
        ),
        "weekly_avg_hrv_ms": simple_average(
            row.get("weekly_avg_hrv_ms") for row in daily_rows
        ),
        "hrv_status": "",
        "body_battery_high": simple_average(
            row.get("body_battery_high") for row in daily_rows
        ),
        "body_battery_low": simple_average(
            row.get("body_battery_low") for row in daily_rows
        ),
        "body_battery_average": simple_average(
            row.get("body_battery_average") for row in daily_rows
        ),
        "sleep_seconds": simple_average(
            row.get("sleep_seconds") for row in daily_rows
        ),
        "sleep_score": simple_average(
            row.get("sleep_score") for row in daily_rows
        ),
        "deep_sleep_seconds": simple_average(
            row.get("deep_sleep_seconds") for row in daily_rows
        ),
        "light_sleep_seconds": simple_average(
            row.get("light_sleep_seconds") for row in daily_rows
        ),
        "rem_sleep_seconds": simple_average(
            row.get("rem_sleep_seconds") for row in daily_rows
        ),
        "awake_seconds": simple_average(
            row.get("awake_seconds") for row in daily_rows
        ),
        "sleep_start": "",
        "sleep_end": "",
    }


def main() -> None:
    end_date = parse_end_date()
    # Inclusive 60-day window: end date plus the previous 59 dates.
    start_date = end_date - timedelta(days=REPORT_DAYS - 1)

    print(
        f"\nReport period: {start_date.isoformat()} to "
        f"{end_date.isoformat()} ({REPORT_DAYS} days)"
    )

    garmin = login_to_garmin()
    print(f"Connected as: {garmin.display_name}\n")

    running_activities = obtain_running_activities(
        garmin,
        start_date,
        end_date,
    )

    activities_by_day: dict[str, list[dict[str, Any]]] = {}
    for activity in running_activities:
        day = activity_day(activity)
        if day is not None:
            activities_by_day.setdefault(day, []).append(activity)

    daily_rows: list[dict[str, Any]] = []
    current_day = start_date

    while current_day <= end_date:
        day_text = current_day.isoformat()
        health = collect_daily_health(garmin, current_day)
        running = aggregate_running(activities_by_day.get(day_text, []))

        daily_rows.append({**health, **running})

        current_day += timedelta(days=1)
        # Be gentle with Garmin's private API.
        time.sleep(0.15)

    output_path = Path(
        f"garmin_report_{start_date.isoformat()}_to_{end_date.isoformat()}.csv"
    )

    with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()

        for row in daily_rows:
            writer.writerow(format_csv_row(row))


    print("\nExport complete.")
    print(f"Running activities included in averages: {len(running_activities)}")
    print(f"CSV saved to: {output_path.resolve()}")


if __name__ == "__main__":
    main()
