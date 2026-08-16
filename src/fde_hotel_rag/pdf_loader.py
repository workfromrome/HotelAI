from pathlib import Path
import pdfplumber

def load_pages(path: Path) -> list[str]:
    if not path.is_file(): raise FileNotFoundError(f"PDF non trovato: {path}")
    with pdfplumber.open(path) as pdf: pages = [" ".join((p.extract_text() or "").split()) for p in pdf.pages]
    if not any(pages): raise ValueError("Nel PDF non è stato trovato testo estraibile")
    return pages

def write_raw(pages: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(f"--- PAGE {i} ---\n{p}" for i,p in enumerate(pages,1)), encoding="utf-8")
