# Model-drafted 2026-11-16; reviewed by Rich 2026-11-16 (PROVENANCE.md).
"""Checks for peeps_canada_directory: one per bullet in the prompt.

The merged columns are found by their text ("Matilda Bates", "Toronto, ON"). An icon is an
SVG or image (`fmt_icon()`), an icon font's element, or a symbol or emoji; the icons must
tell the genders apart and no "female"/"male" text can remain. L2 leaves the gender column
to that check.
"""

import re

from harness.score.intent import fold

ICON = re.compile(r"<svg|<img|<i\s|fa-|[♀♂⚢⚣🚺🚹👩👨🧑]")

DATA_COLUMNS = ["name_given", "city", "email_addr"]


def check(t, truth):
    name = t.col(like=truth.col("name_given"))
    location = t.col(like=truth.col("city"))
    email = t.col("email_addr", like=truth.col("email_addr"))
    t.row_count(10)
    t.has_columns(name, location)
    links = email.found and all(re.search(r"<a\s[^>]*href=", h) for h in email.html)
    t.expect("email addresses are links", links)

    # Each row's gender and family name, from the truth by full name
    full = [fold(x) for x in truth.col("name_given").text]
    gender = dict(zip(full, truth.col("gender").raw))
    family = dict(zip(full, truth.col("name_family").raw))
    genders = [gender.get(fold(x)) for x in name.text]
    icons = [
        c
        for c in t.visible()
        if all(ICON.search(h) for h in c.html)
        and not any(x.casefold() in ("female", "male") for x in c.text)
    ]
    apart = any(
        not {h for h, g in zip(c.html, genders) if g == "person-dress"}
        & {h for h, g in zip(c.html, genders) if g == "person"}
        for c in icons
    )
    t.expect(
        "gender as icons",
        name.found and bool(icons) and apart,
        f"columns: {[c.var for c in icons]}",
    )

    families = [family.get(fold(x)) for x in name.text]
    t.expect(
        "sorted by family name",
        name.found and None not in families and families == sorted(families),
        f"order: {families}",
    )
    t.title("Canadian Contacts")
