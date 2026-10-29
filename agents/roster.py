"""The council, in speaking order. This tuple is the one place the order is set.

The Analyst goes first so its tool numbers are on the table for everyone else.
The Judge is not here: it does not rate, it only explains the verdict at the end.
"""

from agents.alternatives_hunter import ALTERNATIVES_HUNTER
from agents.analyst import ANALYST
from agents.budget_guardian import BUDGET_GUARDIAN
from agents.future_you import FUTURE_YOU

COUNCIL = (ANALYST, FUTURE_YOU, BUDGET_GUARDIAN, ALTERNATIVES_HUNTER)
