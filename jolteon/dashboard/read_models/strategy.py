"""The plain name a page calls a strategy by.

A run records the class that made its decisions (see EngineRun), and a
class name is not something to put in front of a reader.
"""

import re

_BEFORE_A_CAPITAL = re.compile(r"(?<!^)(?=[A-Z])")


def strategy_name(recorded: str) -> str:
    """The recorded class name as words in sentence case, with a trailing
    "Strategy" dropped: "MarketMakingStrategy" is "Market making". A run
    that recorded no strategy stays ""."""
    words = _BEFORE_A_CAPITAL.sub(
        " ", recorded.removesuffix("Strategy")
    ).split()
    return " ".join(words[:1] + [word.lower() for word in words[1:]])
