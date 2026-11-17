# Model-drafted 2026-11-05; reviewed by Rich 2026-11-05 (PROVENANCE.md).
"""Ground truth for nuclides_stable_isotopes (intent style).

Readings:
- Hydrogen to neon is z 1 to 10; "stable" is `is_stable`. That's 20 isotopes, grouped by
  element in order of z.
- An isotope is named by element and mass number (H-1); `nuclide`'s own notation is
  harder to read.
- `atomic_mass` and its uncertainty are in micro-u in the data; they're shown here in u.
- Each uncertainty is merged with its value as "value ± uncertainty". Abundance is a
  percentage. Beryllium-9's abundance has no uncertainty, so it shows the value alone.
"""

import polars as pl
from great_tables import GT

df = (
    pl.read_csv("data/nuclides.csv")
    .filter(pl.col("z") <= 10, pl.col("is_stable"))
    .sort("z", "n")
    .select(
        element="element",
        isotope=pl.format("{}-{}", "element", pl.col("z") + pl.col("n")),
        abundance="abundance",
        abundance_uncert="abundance_uncert",
        atomic_mass=pl.col("atomic_mass") / 1e6,
        # C-12 is exact (zero uncertainty), so it shows its value alone
        atomic_mass_uncert=pl.when(pl.col("atomic_mass_uncert") > 0).then(
            pl.col("atomic_mass_uncert") / 1e6
        ),
    )
)

gt = (
    GT(df, rowname_col="isotope", groupname_col="element")
    .tab_header(title="Stable Isotopes, Hydrogen to Neon")
    .fmt_percent(["abundance", "abundance_uncert"], decimals=4, drop_trailing_zeros=True)
    .fmt_number("atomic_mass", n_sigfig=10, drop_trailing_zeros=True)
    .fmt_scientific("atomic_mass_uncert", decimals=1)
    .cols_merge_uncert("abundance", "abundance_uncert", sep=" ± ")
    .cols_merge_uncert("atomic_mass", "atomic_mass_uncert", sep=" ± ")
    .cols_label(abundance="Natural Abundance", atomic_mass="Atomic Mass (u)")
)

gt_tbl = gt
