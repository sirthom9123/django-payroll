from datetime import date
from decimal import Decimal

# SARS rates for individuals, 2026/27 tax year (1 March 2026 to 28 February 2027).
# https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/


def seed_tax_year_2027(apps, schema_editor):
    TaxYear = apps.get_model("employee", "TaxYear")
    TaxBand = apps.get_model("employee", "TaxBand")
    data = TAX_YEAR_2027
    if TaxYear.objects.filter(name=data["name"]).exists():
        return
    year = TaxYear.objects.create(
        name=data["name"],
        start_date=data["start_date"],
        end_date=data["end_date"],
        primary_rebate=data["primary_rebate"],
        secondary_rebate=data["secondary_rebate"],
        tertiary_rebate=data["tertiary_rebate"],
    )
    for band in data["bands"]:
        TaxBand.objects.create(tax_year=year, **band)
TAX_YEAR_2027 = {
    "name": "2026/27",
    "start_date": date(2026, 3, 1),
    "end_date": date(2027, 2, 28),
    "primary_rebate": Decimal("17820.00"),
    "secondary_rebate": Decimal("9765.00"),
    "tertiary_rebate": Decimal("3249.00"),
    "bands": [
        {
            "income_from": Decimal("0"),
            "income_to": Decimal("245100"),
            "rate_percent": Decimal("18"),
            "base_tax": Decimal("0"),
            "above_amount": Decimal("0"),
        },
        {
            "income_from": Decimal("245101"),
            "income_to": Decimal("383100"),
            "rate_percent": Decimal("26"),
            "base_tax": Decimal("44118"),
            "above_amount": Decimal("245100"),
        },
        {
            "income_from": Decimal("383101"),
            "income_to": Decimal("530200"),
            "rate_percent": Decimal("31"),
            "base_tax": Decimal("79998"),
            "above_amount": Decimal("383100"),
        },
        {
            "income_from": Decimal("530201"),
            "income_to": Decimal("695800"),
            "rate_percent": Decimal("36"),
            "base_tax": Decimal("125599"),
            "above_amount": Decimal("530200"),
        },
        {
            "income_from": Decimal("695801"),
            "income_to": Decimal("887000"),
            "rate_percent": Decimal("39"),
            "base_tax": Decimal("185215"),
            "above_amount": Decimal("695800"),
        },
        {
            "income_from": Decimal("887001"),
            "income_to": Decimal("1878600"),
            "rate_percent": Decimal("41"),
            "base_tax": Decimal("259783"),
            "above_amount": Decimal("887000"),
        },
        {
            "income_from": Decimal("1878601"),
            "income_to": None,
            "rate_percent": Decimal("45"),
            "base_tax": Decimal("666339"),
            "above_amount": Decimal("1878600"),
        },
    ],
}
