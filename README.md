# Keplero Hotel PDF Search

## Roadmap enterprise verificata

Il repository include ora una pipeline separata in ingestion, structured extraction, vector search e MCP:

```text
PDF -> ingestion.pdf_parser -> HotelSchema -> CSV -> ChromaDB -> HotelRetriever -> FastMCP
```

L'indicizzazione Chroma importa il CSV appena scritto (`build_index_from_csv`), non i record ancora in memoria: è il collegamento esplicito richiesto tra "Parte 1 - Estrazione" e "Parte 2 - Ricerca" di questo assignment. Dettagli e motivazione in [`user-doc/csv-driven-indexing.md`](user-doc/csv-driven-indexing.md).

### Verifica offline completa

```powershell
$env:PYTHONPATH = "src"
python -m ingestion.pdf_parser "data\raw\FileHotels.pdf"
python -m ingestion.structured_extractor "data\raw\FileHotels.pdf" "data\processed\hotels_data.csv" --offline
python -m pytest -q
```

La verifica offline attuale produce 19 blocchi PDF e 19 record strutturati.

### Provider LLM e quote

Impostare `GOOGLE_API_KEY` e/o `GROQ_API_KEY` in `.env`. La revisione dei record a bassa confidence e le risposte RAG usano Groq (`openai/gpt-oss-120b`, free tier osservato: 30 richieste/minuto, 1.000/giorno) come provider di default, con fallback automatico su Gemini (`gemini-flash-latest`, free tier osservato: 20 richieste/giorno) quando Groq non è configurato o esaurisce i retry; senza nessuna delle due chiavi l'estrazione resta comunque deterministica (fallback locale) e le risposte RAG restituiscono il messaggio di fallback fisso. Gli embedding usano invece solo Gemini (`gemini-embedding-001`, configurabile tramite `EMBEDDING_MODEL`; `text-embedding-004` è mantenuto solo come riferimento storico, l'endpoint attuale ha restituito 404 per quel modello) — senza `GOOGLE_API_KEY` l'indicizzazione usa un embedder offline deterministico, non semanticamente equivalente.

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

```text
PDF
 ├─ pdfplumber (pdf_parser.py)   -> segmentazione in schede + word bounding box di riferimento
 └─ PyMuPDF (pymupdf_parser.py)  -> header font-size-aware -> nome/localita canonici
                                     -> HotelRecord (structured_extractor.py)
                                     -> revisione Groq (default) / Gemini (fallback) se confidence bassa
                                     -> CSV/JSONL -> [CSV re-read] -> ChromaDB (embedding Gemini)
                                     -> HotelRetriever -> FastMCP / RAGEngine (RAGEngine non esposto come tool MCP)
```

- `pymupdf_parser.py` è la fonte canonica di `nome`/`localita` (estrazione per dimensione del font nell'header); `pdf_parser.py` (`pdfplumber`) fornisce la segmentazione in schede e le word bounding box usate dal fallback visuale sulle valutazioni.
- I record con confidence deterministica bassa (`quality.confidence < settings.llm_fallback_confidence_threshold`) vengono rivisti da un LLM: Groq (`openai/gpt-oss-120b`) è il provider di default, con fallback automatico su Gemini (`gemini-flash-latest`) quando Groq non è configurato o fallisce; i record ad alta confidence non consumano chiamate API.
- `gemini-embedding-001` crea i vettori ChromaDB in `data/processed/chromadb`.
- Ogni documento vettoriale include i metadata strutturati del record (esclusi `source`/`quality`, che sono solo per audit); i risultati sono ordinati con un punteggio ibrido vettoriale + overlap lessicale sui metadata (`vector_weight`/`metadata_weight` in `.env`).
- FastMCP espone `search_hotels(query: str) -> str`, restituendo sempre al massimo cinque risultati.
- `RAGEngine` (`src/rag/rag_engine.py`) usa la stessa cascata Groq-poi-Gemini per sintetizzare una risposta in linguaggio naturale con citazioni di pagina, esposta via `POST /api/chat` nel backend FastAPI (non ancora come tool MCP).

I provider si selezionano tramite `LLM_PROVIDER` ed `EMBEDDING_PROVIDER` in `.env`.

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
python scripts/run_pipeline.py "data\raw\FileHotels.pdf"
python -m mcp_server.server
```

Per la verifica offline senza API key, eseguire `python scripts/run_pipeline.py "data\raw\FileHotels.pdf" --offline`. La modalità offline produce solo CSV/JSONL (nessuna chiamata Groq/Gemini); non costruisce Chroma. L'indice e il retrieval richiedono un provider embedding configurato.

Il raggruppamento individua le intestazioni delle schede nel testo PDF e associa la pagina seguente. Se un catalogo non conserva le intestazioni, usa il fallback strutturale “introduzione + coppie di pagine”. I nomi non sono mantenuti in liste applicative: sono estratti dall'intestazione e normalizzati solo per correggere artefatti OCR evidenti.

`GOOGLE_MODEL`, `GROQ_MODEL`, `EMBEDDING_MODEL`, `REQUEST_DELAY_SECONDS`, `GEMINI_REQUESTS_PER_MINUTE`, `GROQ_REQUESTS_PER_MINUTE` e `MAX_RETRIES` sono configurabili in `.env`. Gli errori Google 404, 429 e 5xx sono espliciti; 429 e 5xx vengono ritentati con backoff.

## Dati estratti e qualità

Il JSONL è lo storage canonico auditabile; il CSV è l'interfaccia tra estrazione e indicizzazione, oltre che la vista tabellare consegnata. I record possono contenere categoria numerica, valutazioni (`ente`, `tipo`, `punteggio/massimo`), qualificatori, testo originale, pagine sorgente e confidence per campo. I punteggi non leggibili restano `null`. L'estrazione deterministica (PyMuPDF per nome/localita, euristiche testuali/regex per gli altri campi) è il primo passo; Groq testuale (fallback Gemini) rivede i record a bassa confidence, e Gemini Vision legge le valutazioni visuali quando il testo non le riporta come punteggi numerici.

## MCP client configuration

```json
{
  "mcpServers": {
    "keplero-hotels": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "<path assoluto alla cartella del repository>",
      "env": {"PYTHONPATH": "src"}
    }
  }
}
```

## Web App (chatbot)

Backend FastAPI (`src/api/main.py`) e frontend React/Vite (`frontend/`), tema scuro stile ChatGPT/Claude:

```powershell
$env:PYTHONPATH = "src"
python -m uvicorn api.main:app --reload --reload-dir src --port 8000
# --reload-dir src limita il watcher al codice sorgente: senza, il salvataggio
# dei file generati da /api/ingest sotto data/ farebbe riavviare il server a metà richiesta.
```

```powershell
cd frontend
npm install
npm run dev
```

Il frontend gira su `http://localhost:5173` e proxya `/api/*` verso il backend su `http://localhost:8000` (`vite.config.js`); il backend ha anche CORS aperto verso `localhost:5173` come seconda difesa. Endpoint: `POST /api/chat`, `GET /api/hotels` (19 record canonici da `data/processed/hotels_data.jsonl`), `GET /api/health`. Le risposte dell'assistente non vengono renderizzate come Markdown (nessuna libreria aggiunta per questo) — testo semplice con interruzioni di riga preservate.

## Verification

```powershell
$env:PYTHONPATH = "src"
pytest -q
```

Il PDF fornito deve produrre 19 righe CSV; `source_pages` rende ogni campo tracciabile fino alle pagine originali. Limiti residui: l'ordine del testo PDF e gli artefatti OCR possono richiedere una revisione visiva; il fallback locale è conservativo e non sostituisce la validazione semantica del modello.
