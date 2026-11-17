# Rubric

Each table was built with the Great Tables package in Python, in answer to a request. Grade it
as the person who made the request would read it: someone who wants to learn something from
the table.

Requests come in two styles. Some say what the reader should learn and leave the design to
the builder. Others list the features the table should have. For a list, each item the request
names counts under answers_prompt, and the other dimensions still apply to the whole table.

Some things are checked elsewhere, so leave them out:

- Whether the values are correct. You can't recompute them from the image, so don't guess. The
  exception is a value that is visibly impossible, such as a share above 100% or a negative
  count. Count that under answers_prompt.
- How the table was built. Two tables that look the same get the same grades.

Some things earn no credit by themselves:

- Size. A table with more rows, columns or notes than the request needs isn't better for it.
- Decoration. Color, borders, bold and icons count only when the request asks for them or
  when they help the reader find or compare something.
- A particular style. There are many good ways to present the same data, and no table here is
  the one right answer.

Judge each dimension on its own, so that a problem counts once, under the dimension it belongs
to. The anchors describe scores of 1, 3 and 5. Use 2 or 4 when a table falls between two
anchors.

A tall table may arrive as several images, labeled as parts, in order from top to bottom.
Read them as one table.

## answers_prompt: Answers the request

Does the table show what was asked for? This covers the subject, the rows (which ones, how
many, and in what order when the request gives one), the measures, and every feature the
request names. The reader should be able to find the answer to the request in the table
without working it out themselves.

- **1:** The table misses the main point of the request. It shows the wrong subject, leaves out
  a measure the request is about, or shows the wrong rows.
- **3:** The main point is answered, but something the request asks for is missing or wrong.
  For example, a requested sort isn't applied, one listed feature is absent, or there are 12
  rows where the request asks for 10.
- **5:** Everything the request asks for is there and visible, and the answer to the request
  is easy to find.

## labels: Labels name the right concepts

This covers the title and subtitle, column labels, spanners, row group labels, and notes. Each
should tell the reader what they're looking at, in words the reader would use, with units
where a number needs them.

- **1:** A label names the wrong concept or misleads, such as a percent change labeled as a
  count or a median labeled as a mean. Or most labels are raw data names (`p99_ms`,
  `pop_2021`) that the reader has to decode.
- **3:** Every label names the right concept, but some are raw data names, units are missing
  where they matter, or the title is missing or generic ("Data Table", "Results").
- **5:** Every label is clear and accurate, with units where they're needed, and the title
  says what the table shows.

## hierarchy: Sensible hierarchy

This covers how the table is organized: what identifies each row (the stub), row groups,
spanners over related columns, column order, and row order. Good structure lets the reader
find a row and make the comparisons the request is about. More structure isn't better. A flat
table that serves the request scores 5.

- **1:** The structure works against the reader. Rows are grouped by something unrelated to
  the request, the column that identifies each row is buried, related columns are scattered,
  or rows are in no useful order when the request is about a ranking or a change over time.
- **3:** The structure is workable but misses something that would clearly help. For example,
  an obvious grouping is left out, the identifying column isn't first, or a spanner sits over
  columns that don't belong together.
- **5:** The structure fits the request. The reader can find any row and make the comparisons
  the request is about without hunting. Small differences in column order that cost the reader
  nothing don't count against it.

## precision: Appropriate precision

This covers how values are shown: decimals suited to the measure and the comparison, thousands
separators (but not in years or IDs), currency and percent signs, readable dates, and missing
values. Formatting should be consistent within a column.

- **1:** Values are hard to read or misleading. Examples are long raw decimals (0.4736842105),
  shares shown as fractions under a label that says percent, large numbers without separators
  throughout, or "None" and "nan" in cells.
- **3:** Most values read well, but a column or two has too many or too few decimals, lacks
  separators or currency or percent signs, or mixes formats.
- **5:** Every column is formatted for its measure. The precision is enough for the comparison
  and no more, and missing values are shown on purpose (a dash or a word, not "None").

## layout: Fits the viewport

This covers whether the table can be read as a whole at a normal size: its width and length,
wrapping, alignment, and contrast. Styling counts here when it helps or hurts legibility.

- **1:** Parts of the table can't be read. Text is clipped, overlaps or has poor contrast, or
  the table is so wide or long that the reader can't take it in.
- **3:** The table is readable but bulkier or busier than it needs to be. Examples are columns
  the request doesn't need that widen it, headers wrapped across several lines, or color and
  borders that distract from the values.
- **5:** The table is compact and clean. Everything is legible, numbers line up for
  comparison, and nothing distracts.
