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

const LIST_MARKER_PATTERN = /^(\s*)([-*+]|\d+\.)\s+/

/**
 * Some LLM answers put a blank line between a bullet's bold title and its description
 * (e.g. "- **Hotel X**\n\nDescrizione..."). CommonMark then treats the unindented
 * description as a new top-level paragraph *outside* the list instead of nesting it
 * inside the `<li>`, which breaks the tight-list CSS (`li > p { margin: 0 }` never
 * applies) and shows up as an oversized gap under each bullet. This re-indents that
 * first orphaned paragraph so it nests back under the preceding list item, without
 * touching already-tight lists or unrelated prose.
 */
export function tightenLooseListItems(text) {
  if (!text) return text
  const lines = text.split('\n')
  let pendingIndent = null

  return lines
    .map((line, i) => {
      const marker = line.match(LIST_MARKER_PATTERN)
      if (marker) {
        pendingIndent = ' '.repeat(marker[0].length)
        return line
      }
      if (line.trim() === '') return line

      const isRightAfterBlank = (lines[i - 1] ?? '').trim() === ''
      const alreadyIndented = /^\s/.test(line)
      if (pendingIndent && isRightAfterBlank && !alreadyIndented) {
        const fixed = pendingIndent + line
        pendingIndent = null
        return fixed
      }
      pendingIndent = null
      return line
    })
    .join('\n')
}

/** Query text that triggers the local canned response in App.jsx instead of calling the LLM. */
export const TEST_QUERY_TEXT = 'Messaggio di prova (senza LLM)'

export const TEST_RESPONSE_TEXT = `Questa è una risposta di **prova**, generata localmente senza contattare il modello linguistico: serve solo a verificare l'animazione di comparsa del testo, lettera per lettera.

Alcuni esempi di formattazione che una risposta reale potrebbe usare:

- Punti elenco come questo
- Testo in **grassetto** o *corsivo*
- Citazioni di pagina che vengono rimosse dal testo visibile, ad esempio qui [Pag. 4-5]

**Hotel Esempio** — una struttura fittizia usata solo per avere un testo abbastanza lungo su cui osservare l'animazione, con più paragrafi e formattazione markdown proprio come farebbe una risposta reale dell'assistente.`

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
