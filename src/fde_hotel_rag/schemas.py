"""Canonical hotel schema shared by extraction, storage, search and MCP."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


class HotelRating(BaseModel):
    """Valutazione attribuita da un catalogo o da un brand commerciale."""

    ente: str
    tipo: str = "generale"
    punteggio: int | None = Field(default=None, ge=0)
    massimo: int | None = Field(default=None, gt=0)
    testo_originale: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "HotelRating":
        if self.punteggio is not None and self.massimo is not None and self.punteggio > self.massimo:
            raise ValueError("Il punteggio non può superare il valore massimo")
        return self


class VisualRatings(BaseModel):
    ratings: list[HotelRating] = Field(default_factory=list)


class ExtractionQuality(BaseModel):
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
    regione: str = Field(default="Non specificata", validation_alias=AliasChoices("regione", "region"))
    stelle: str | None = Field(default=None, validation_alias=AliasChoices("stelle", "stars"))
    categoria_ufficiale: int | None = Field(default=None, ge=1, le=7)
    valutazioni: list[HotelRating] = Field(default_factory=list)
    qualificatori: list[str] = Field(default_factory=list)
    trattamento_principale: str | None = Field(default=None, validation_alias=AliasChoices("trattamento_principale", "treatment"))
    distanza_mare_metri: int | None = None
    pet_friendly: bool = False
    ha_piscina: bool = False
    ha_spa: bool = False
    ha_biberoneria: bool = False
    caratteristiche_chiave: list[str] = Field(default_factory=list)
    descrizione: str = Field(default="", validation_alias=AliasChoices("descrizione", "description"))
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

    def searchable_text(self) -> str:
        return "\n".join(f"{field}: {value}" for field, value in self.model_dump().items())

    def metadata(self) -> dict[str, str]:
        return {field: " | ".join(map(str, value)) if isinstance(value, list) else str(value or "") for field, value in self.model_dump().items() if field != "descrizione"}

    # Temporary read-only compatibility properties for legacy modules.
    @property
    def name(self) -> str: return self.nome
    @property
    def locality(self) -> str: return self.localita
    @property
    def region(self) -> str: return self.regione
    @property
    def stars(self) -> str | None: return self.stelle
    @property
    def treatment(self) -> list[str]: return [self.trattamento_principale] if self.trattamento_principale else []
    @property
    def room_types(self) -> list[str]: return []
    @property
    def services(self) -> list[str]: return self.caratteristiche_chiave
    @property
    def highlights(self) -> list[str]: return self.caratteristiche_chiave
    @property
    def description(self) -> str: return self.descrizione


class HotelExtraction(BaseModel):
    hotel: HotelRecord
