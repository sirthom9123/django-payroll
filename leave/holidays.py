"""South African public holidays.

Schedule 1 of the Public Holidays Act 36 of 1994, plus section 2(1): when a
listed day falls on a Sunday, the following Monday is a public holiday as well.
The Sunday stays a public holiday. Easter is Good Friday and the Monday after
Easter Sunday.
"""

from datetime import date, timedelta


def easter_sunday(year):
    """Gregorian Easter Sunday (Anonymous algorithm)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def public_holidays(year):
    easter = easter_sunday(year)
    listed = {
        date(year, 1, 1),
        date(year, 3, 21),
        easter - timedelta(days=2),
        easter + timedelta(days=1),
        date(year, 4, 27),
        date(year, 5, 1),
        date(year, 6, 16),
        date(year, 8, 9),
        date(year, 9, 24),
        date(year, 12, 16),
        date(year, 12, 25),
        date(year, 12, 26),
    }
    observed = {day + timedelta(days=1) for day in listed if day.weekday() == 6}
    return listed | observed


def is_public_holiday(day):
    return day in public_holidays(day.year)
