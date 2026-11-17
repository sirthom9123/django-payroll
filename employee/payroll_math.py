from decimal import Decimal, ROUND_HALF_UP

TWOPLACES = Decimal("0.01")
UIF_RATE = Decimal("0.01")
BASIC_SALARY_LIMIT = Decimal("99999.99")


def money(value):
    """Round a money figure to cents with half-up, the rule used on a payslip."""
    if value is None:
        value = Decimal("0")
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def basic_salary(rate, hours):
    return money(Decimal(rate or 0) * Decimal(hours or 0))


def uif_on_basic(basic):
    """Employee UIF is 1% of basic salary. Overtime and allowances are not included."""
    return money(Decimal(basic or 0) * UIF_RATE)


def overtime_pay(hours, rate):
    return money(Decimal(hours or 0) * Decimal(rate or 0))


def sum_money(amounts):
    total = Decimal("0")
    for amount in amounts:
        if amount is not None:
            total += Decimal(amount)
    return money(total)


def age_on(born, on_date):
    years = on_date.year - born.year
    if (on_date.month, on_date.day) < (born.month, born.day):
        years -= 1
    return years


def annual_tax(annual_income, bands):
    """SARS statutory tax on annual taxable income, before rebates."""
    income = Decimal(annual_income or 0)
    if income <= 0:
        return Decimal("0")
    chosen = None
    for band in bands:
        upper = band.income_to
        if income >= Decimal(band.income_from) and (upper is None or income <= Decimal(upper)):
            chosen = band
            break
    if chosen is None:
        raise ValueError("Remuneration is outside the PAYE bands.")
    rate = Decimal(chosen.rate_percent) / Decimal("100")
    return Decimal(chosen.base_tax) + rate * (income - Decimal(chosen.above_amount))


def monthly_paye(remuneration, bands, rebate):
    """One payroll run is one month. Annualise, apply the table, then divide by 12."""
    annual_income = Decimal(remuneration or 0) * 12
    payable = annual_tax(annual_income, bands) - Decimal(rebate or 0)
    if payable < 0:
        payable = Decimal("0")
    return money(payable / 12)
