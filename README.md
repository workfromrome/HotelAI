# Keplero Hotel PDF Search

## Roadmap enterprise verificata

Il repository include ora una pipeline separata in ingestion, structured extraction, vector search e MCP:

```text
PDF -> ingestion.pdf_parser -> HotelSchema -> CSV
                         \-> ChromaDB -> HotelRetriever -> FastMCP
```

### Verifica offline completa

```powershell
$env:PYTHONPATH = "src"
python -m ingestion.pdf_parser "C:\Users\olso4\Downloads\FDE_test\FDE_test\FileHotels.pdf"
python -m ingestion.structured_extractor `
  "C:\Users\olso4\Downloads\FDE_test\FDE_test\FileHotels.pdf" `
  "data\processed\hotels_data.csv" --offline
python -m pytest -q
```

La verifica offline attuale produce 19 blocchi PDF e 19 record strutturati.

### Gemini / Google AI Studio

Impostare `GOOGLE_API_KEY` in `.env`. L’estrazione usa Gemini con schema Pydantic; gli embedding usano `gemini-embedding-001`, configurabile tramite `EMBEDDING_MODEL`. `text-embedding-004` è mantenuto solo come riferimento storico: l’endpoint attuale ha restituito 404 per quel modello. Il piano gratuito di Google AI Studio può essere usato entro i limiti di quota e disponibilità del modello.

### MCP

```powershell
$env:PYTHONPATH = "src"
python -m mcp_server.server
```

Per client desktop MCP compatibili o MCP Inspector usare un comando Python con `-m mcp_server.server`, impostando `PYTHONPATH=src` e la directory del repository come working directory. Il server espone il tool `search_hotels` e restituisce al massimo cinque risultati Markdown.

### Query di esempio

- `Cerco una struttura pet-friendly vicino al mare.`
- `Mostrami soluzioni con pensione completa e piscina.`
- `Quali strutture sono più adatte a una famiglia con bambini?`
- `Cerco una struttura con spa o centro benessere.`
- `Trova strutture con camere family e parcheggio.`

Pipeline piccolo e verificabile per il catalogo alberghiero fornito. Estrae una riga per hotel, salva dati pronti alla ricerca in ChromaDB ed espone un singolo tool MCP.

## Architecture

- `pdfplumber` extracts every PDF page into `data/raw/file_hotels.txt` for inspection.
- Google AI Studio (`gemini-flash-latest`) produce schede strutturate validate con Pydantic quando la confidence locale è bassa.
- `gemini-embedding-001` crea i vettori ChromaDB in `data/processed/chromadb`.
- Each vector document includes the CSV metadata; results are re-ranked with transparent lexical metadata overlap. This gives natural-language similarity plus explicit matches for features such as `piscina`, `pet-friendly`, and `pensione completa`.
- FastMCP exposes `search_hotels(query: str) -> str`, always requesting a maximum of five results.

Il confine tra provider è volutamente piccolo: `gemini_extract` e `GoogleEmbeddingFunction` possono essere sostituiti con adapter Groq, modelli open-source locali o altri provider gratuiti/con quota senza modificare parsing, CSV, retrieval o MCP. I provider si selezionano tramite `LLM_PROVIDER` ed `EMBEDDING_PROVIDER`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set a real `GOOGLE_API_KEY` in `.env`, then run:

```powershell
$env:PYTHONPATH = "src"
python scripts/run_pipeline.py "..\FileHotels.pdf"
python -m fde_hotel_rag.server
```

Per la verifica offline senza API key, eseguire `python scripts/run_pipeline.py "C:\Users\olso4\Downloads\FDE_test\FDE_test\FileHotels.pdf" --offline`. La modalità offline produce testo grezzo e CSV e salva lo stato progressivo; non costruisce Chroma. L'indice e il retrieval richiedono un provider embedding configurato.

Il raggruppamento individua le intestazioni delle schede nel testo PDF e associa la pagina seguente. Se un catalogo non conserva le intestazioni, usa il fallback strutturale “introduzione + coppie di pagine”. I nomi non sono mantenuti in liste applicative: sono estratti dall'intestazione e normalizzati solo per correggere artefatti OCR evidenti.

`GOOGLE_MODEL`, `GROQ_MODEL`, `EMBEDDING_MODEL`, `REQUEST_DELAY_SECONDS`, `GEMINI_REQUESTS_PER_MINUTE`, `GROQ_REQUESTS_PER_MINUTE` e `MAX_RETRIES` sono configurabili in `.env`. Gli errori Google 404, 429 e 5xx sono espliciti; 429 e 5xx vengono ritentati con backoff. `data/processed/extraction_state.json` permette il resume senza ripetere record già validati.

## Dati estratti e qualità

Il JSONL è lo storage canonico auditabile; il CSV è una vista tabellare. I record possono contenere categoria numerica, valutazioni (`ente`, `tipo`, `punteggio/massimo`), qualificatori, testo originale, pagine sorgente e confidence per campo. I punteggi non leggibili restano `null`. Il parser usa prima testo/layout `pdfplumber`; Gemini testuale e Vision sono fallback per i casi ambigui.

## MCP client configuration

```json
{
  "mcpServers": {
    "keplero-hotels": {
      "command": "python",
      "args": ["-m", "fde_hotel_rag.server"],
      "cwd": "C:\\Users\\olso4\\Downloads\\FDE_test\\FDE_test\\fde_hotel_rag",
      "env": {"PYTHONPATH": "src"}
    }
  }
}
```

## Verification

```powershell
$env:PYTHONPATH = "src"
pytest -q
```

Il PDF fornito deve produrre 19 righe CSV. Verificare un campione contro `data/raw/file_hotels.txt`; `source_pages` rende ogni campo tracciabile. Limiti residui: l'ordine del testo PDF e gli artefatti OCR possono richiedere una revisione visiva; il fallback locale è conservativo e non sostituisce la validazione semantica del modello.

## Architettura corrente (aggiornamento temporaneo)

Accanto al parser canonico `pdfplumber`, il progetto include un candidato PyMuPDF per i PDF multi-colonna:

```text
PDF
 ├─ pdfplumber                 -> segmentazione canonica
 └─ PyMuPDF get_text("dict")   -> header BBox/font-size
                                  -> ExtractionQuality
                                  -> correzione titolo mirata (Groq/Gemini)
                                  -> HotelRecord
                                  -> ChromaDB / Retriever
                                  -> RAGEngine -> FastMCP (RAGEngine non ancora esposto come tool MCP)
```

PyMuPDF usa filtri spaziali e tipografici per isolare il nome nell’header. I record con `quality.needs_review=True` possono essere inviati alla correzione titolo: Groq (`openai/gpt-oss-120b`, free tier 30 RPM / 1.000 richieste al giorno) è il provider di default, con fallback automatico su Gemini Flash quando Groq non è configurato o esaurisce i retry (limite giornaliero Gemini free tier osservato: 20 richieste/modello); i record ad alta confidence non consumano chiamate API. Ogni provider ha un proprio timer di backoff calcolato sul proprio limite RPM configurato, così i due limiti non si mescolano mai. `RAGEngine` (`src/rag/rag_engine.py`) recupera i documenti più rilevanti e genera una risposta italiana con citazioni di pagina usando la stessa cascata Groq-poi-Gemini (senza retry/backoff, essendo sul percorso di query interattiva); quando il contesto non è sufficiente, entrambi i provider falliscono o la query è vuota, restituisce sempre `Informazione non sufficiente nei documenti forniti` senza sollevare eccezioni.

Questa sezione è temporanea e verrà consolidata insieme alla documentazione della futura webapp.
