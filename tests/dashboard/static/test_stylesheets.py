"""A stylesheet of ours reaches the page through `st.html`, which
sanitises with DOMPurify. DOMPurify drops any text node holding a `<`
followed by a letter, a slash or a bang, and a stylesheet is one text
node: a `<` in one of its comments empties the whole sheet, silently,
while a test reading the markup still sees every class it expects. The
heartbeat history lost its bars that way, to a comment that named an
SVG tag.
"""

import re
from pathlib import Path

STATIC = (
    Path(__file__).resolve().parents[3] / "jolteon" / "dashboard" / "static"
)

_TAG_LIKE = re.compile(r"<[A-Za-z/!]")


def test_no_stylesheet_of_ours_holds_anything_that_reads_as_a_tag():
    offenders = {
        sheet.name: sorted(
            {
                match.group(0)
                for match in _TAG_LIKE.finditer(sheet.read_text("utf-8"))
            }
        )
        for sheet in STATIC.glob("*.css")
        if _TAG_LIKE.search(sheet.read_text("utf-8"))
    }
    assert not offenders, f"tag-like text in a stylesheet: {offenders}"
