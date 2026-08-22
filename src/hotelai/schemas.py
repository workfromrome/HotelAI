"""Canonical hotel schema shared by extraction, storage, search and MCP.

`HotelRecord` is the one shape every layer agrees on: `ingestion` produces it, it is
serialized to CSV/JSONL, `search/vector_store.py` re-reads it via `read_csv`, and the
MCP/RAG layers consume it via Chroma metadata. Field names are Italian because that is
the delivered CSV's contract (`nome`, `localita`, ...); `AliasChoices` accepts the
English equivalents too so records built programmatically in tests can use either.
"""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


class HotelRating(BaseModel):
    """Valutazione attribuita da un catalogo o da un brand commerciale."""

    ente: str
    tipo: str = "generale"
    punteggio: int | None = Field(default=None, ge=0)
    massimo: int | None = Field(default=None, ge=1)
    testo_originale: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> HotelRating:
        if self.punteggio is not None and self.massimo is not None and self.punteggio > self.massimo:
            raise ValueError("Il punteggio non può superare il valore massimo")
        return self


class VisualRatings(BaseModel):
    ratings: list[HotelRating] = Field(default_factory=list)


class ExtractionQuality(BaseModel):
    """Per-record data-quality audit trail: how `structured_extractor` answers
    "how did you check data quality and what limits did you find" (see README)."""

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    needs_review: bool = False
    issues: list[str] = Field(default_factory=list)
    field_confidence: dict[str, float] = Field(default_factory=dict)

    @field_validator("field_confidence")
    @classmethod
    def validate_field_confidence(cls, values: dict[str, float]) -> dict[str, float]:
        if any(not 0.0 <= score <= 1.0 for score in values.values()):
            raise ValueError("La confidence dei campi deve essere compresa tra 0 e 1")
        return values


class HotelSource(BaseModel):
    pages: list[int] = Field(default_factory=list)
    raw_text: str = ""


class HotelRecord(BaseModel):
    """Canonical schema; Italian names are the serialized contract."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = ""
    nome: str = Field(validation_alias=AliasChoices("nome", "name"))
    localita: str = Field(default="Non specificata", validation_alias=AliasChoices("localita", "locality"))
    stelle: str | None = Field(default=None, validation_alias=AliasChoices("stelle", "stars"))
    categoria_ufficiale: int | None = Field(default=None, ge=1, le=7)
    valutazioni: list[HotelRating] = Field(default_factory=list)
    qualificatori: list[str] = Field(default_factory=list)
    trattamento_principale: str | None = Field(default=None, validation_alias=AliasChoices("trattamento_principale", "treatment"))
    pet_friendly: bool = False
    ha_piscina: bool = False
    ha_spa: bool = False
    ha_biberoneria: bool = False
    caratteristiche_chiave: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    source: HotelSource = Field(default_factory=HotelSource)
    quality: ExtractionQuality = Field(default_factory=ExtractionQuality)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, values: object) -> object:
        if not isinstance(values, dict): return values
        data = dict(values)
        if isinstance(data.get("treatment"), list): data["treatment"] = data["treatment"][0] if data["treatment"] else None
        if "services" in data and "caratteristiche_chiave" not in data: data["caratteristiche_chiave"] = data["services"]
        if "highlights" in data and "caratteristiche_chiave" not in data: data["caratteristiche_chiave"] = data["highlights"]
        return data
