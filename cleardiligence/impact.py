def estimate_impact(monthly_assessments: float, manual_hours: float, time_saved_percent: float, hourly_cost: float) -> dict:
    if min(monthly_assessments, manual_hours, hourly_cost) < 0 or not 0 <= time_saved_percent <= 100:
        raise ValueError("Assumptions must be nonnegative and time saved between 0 and 100")
    baseline = monthly_assessments * manual_hours * 12
    released = baseline * time_saved_percent / 100
    return {"annual_manual_hours": baseline, "annual_hours_released": released, "annual_assisted_hours": baseline - released, "capacity_value": released * hourly_cost, "fte_capacity": released / 2080}
