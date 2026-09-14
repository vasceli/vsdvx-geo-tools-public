from backend.services.calculator import calculate_services, distribute


def test_distribution_preserves_total():
    assert sum(distribute(100, [1, 1, 1])) == 100


def test_three_month_plan_balances_components():
    result = calculate_services(3, 120000, 18000, True)
    assert result["maps_total"] == 102000
    assert result["reputation_total"] == 18000
    assert sum(result["maps_months"]) + sum(result["reputation_months"]) == 120000
