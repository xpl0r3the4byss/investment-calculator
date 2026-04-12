"""
Shared configuration for the children's Acorns Early accounts.
Used by both the Catch-up Planner and the individual child pages.
"""

from datetime import date

CHILDREN = [
    {"name": "Easton",  "birth_date": date(2015,  8, 25)},
    {"name": "Ava",     "birth_date": date(2018,  1, 12)},
    {"name": "Millie",  "birth_date": date(2019, 10, 29)},
    {"name": "Michael", "birth_date": date(2021,  1, 11)},
    {"name": "Trip",    "birth_date": date(2022,  7, 12)},
]

ACORNS_EARLY_PORTFOLIO = "Aggressive (100% stocks)"
MONTHLY_TARGET = 5.0
