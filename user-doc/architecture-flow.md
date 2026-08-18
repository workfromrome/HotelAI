# Flusso ad alto livello — fde_hotel_rag

Questo documento descrive, ad alto livello, come l'app trasforma i PDF degli hotel in un catalogo interrogabile in linguaggio naturale, e come una domanda dell'utente diventa una risposta.

## Panoramica dei componenti

| Componente | Percorso | Ruolo |
|---|---|---|
| Ingestion | `src/ingestion/` | Estrae testo dai PDF, corregge i titoli, produce record strutturati |
| Search | `src/search/` | Genera embedding e indicizza/recupera gli hotel su ChromaDB |
| RAG Engine | `src/rag/rag_engine.py` | Combina retrieval + LLM per rispondere alle domande |
| API | `src/api/main.py` | Espone il backend FastAPI al frontend |
| Frontend | `frontend/` | SPA React/Vite in stile chat |
| MCP Server | `src/mcp_server/server.py` | Espone la ricerca hotel come tool MCP (percorso alternativo, senza sintesi LLM) |
| Config | `src/fde_hotel_rag/config.py` | Chiavi API, modelli, pesi di ranking, percorsi |

## Flowchart

```mermaid
flowchart TD
    subgraph ING["1. Ingestion (offline, script)"]
        PDF["PDF hotel"] --> PARSE["ingestion/pdf_parser.py\nsegmentazione blocchi + OCR cleanup"]
        PARSE --> EXTRACT["ingestion/structured_extractor.py\nestrazione campi (regex)"]
        EXTRACT -->|titolo incerto| TITLE["gemini_title_corrector.py\nGroq -> Gemini fallback\n(con cache)"]
        TITLE --> RECORD
        EXTRACT --> RECORD["HotelRecord (Pydantic)\nCSV / JSONL"]
        RECORD --> INDEX["search/vector_store.py\nbuild_index()\nembedding + upsert ChromaDB"]
    end

    subgraph QUERY["2. Query (runtime, interattivo)"]
        USER["Utente: domanda in chat"] --> UI["frontend/ (React + Vite)\nInputBar -> App.jsx"]
        UI -->|POST /api/chat| API["src/api/main.py\nFastAPI"]
        API --> ENGINE["rag/rag_engine.py\nRAGEngine.answer_query()"]
        ENGINE --> RETRIEVE["search/retriever.py\nHotelRetriever.search_hotels()\nembedding query + similarità vettoriale\n+ rerank su metadati"]
        RETRIEVE --> CHROMA[(ChromaDB\nindice hotel)]
        RETRIEVE --> CONTEXT["Costruzione contesto\ncon citazioni pagina per hotel"]
        CONTEXT --> LLM["Chiamata LLM\nGroq (primario) -> Gemini (fallback)"]
        LLM --> RESP["RAGResponse\nrisposta + hotel + pagine citate"]
        RESP --> UI
        UI --> ANSWER["Risposta mostrata in chat\ncon badge di citazione pagina"]
    end

    subgraph MCP["Percorso alternativo: MCP"]
        MCPCLIENT["Client MCP"] --> MCPSERVER["mcp_server/server.py\ntool search_hotels()"]
        MCPSERVER --> RETRIEVE
        MCPSERVER --> MCPOUT["Risultati Markdown grezzi\n(nessuna sintesi LLM)"]
    end

    INDEX -.alimenta.-> CHROMA
```

## Note sul flusso

- **Ingestion è offline**: si esegue una volta (o quando arrivano nuovi PDF) tramite `scripts/run_pipeline.py`, non ad ogni richiesta utente.
- **Un chunk per hotel**: a differenza di molte pipeline RAG, non c'è suddivisione in sotto-chunk — l'intero blocco di testo di un hotel diventa un singolo documento indicizzato, con metadati associati (categoria, rating, ecc.) usati anche per il rerank lessicale.
- **Fallback LLM a due livelli**: sia in fase di correzione titoli sia in fase di risposta, Groq è il provider primario e Gemini il fallback in caso di errore/indisponibilità. Solo la correzione titoli usa una cache delle risposte; le risposte del RAG Engine non sono cachate.
- **"Conversazionale" è il tono del prompt, non memoria multi-turno**: ogni domanda viene elaborata come una richiesta singola — non viene passata la cronologia della conversazione al motore RAG.
- **Due modi di interrogare i dati**: il frontend web passa sempre da `RAGEngine` (risposta sintetizzata in linguaggio naturale); il server MCP espone invece il retrieval grezzo (Markdown con i risultati), senza generazione LLM.
- **Frontend e backend in dev**: Vite (porta 5173) fa da proxy verso FastAPI (porta 8000) per le chiamate `/api/*`; il backend ha comunque CORS abilitato per 5173 come rete di sicurezza aggiuntiva.
