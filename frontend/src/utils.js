const PAGE_CITATION_PATTERN = /\s?\[Pag\.?\s*\d+(?:\s*[-–—‑]\s*\d+)?(?:\s*,\s*\d+(?:\s*[-–—‑]\s*\d+)?)*\s*\]/gi

/**
 * Strip inline "[Pag. 2-3]" style citations from assistant text: the page badges
 * rendered below the message already carry that information, so leaving the raw
 * citation in the table/prose text is redundant.
 */
export function stripPageCitations(text) {
  if (!text) return text
  return text.replace(PAGE_CITATION_PATTERN, '').replace(/[ \t]+([.,;:!?])/g, '$1')
}

/** Group a sorted/unsorted list of page numbers into dash ranges, e.g. [2,3,7] -> ["2-3", "7"]. */
export function formatPageRanges(pages) {
  if (!pages || pages.length === 0) return []
  const ordered = [...new Set(pages)].sort((a, b) => a - b)
  const ranges = []
  let start = ordered[0]
  let end = ordered[0]

  for (let i = 1; i <= ordered.length; i += 1) {
    const current = ordered[i]
    if (current === end + 1) {
      end = current
      continue
    }
    ranges.push(start === end ? `${start}` : `${start}-${end}`)
    start = current
    end = current
  }
  return ranges
}
