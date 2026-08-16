import hashlib, json
from pathlib import Path
from collections.abc import Sequence
from ..schemas import HotelRecord
class JsonlStorage:
    def __init__(self, path: Path): self.path = path
    def save(self, records: Sequence[HotelRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as file:
            for record in records: file.write(json.dumps(record.model_dump(), ensure_ascii=False) + "\n")
    def load(self) -> list[HotelRecord]:
        if not self.path.exists(): return []
        return [HotelRecord.model_validate(json.loads(line)) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    @staticmethod
    def content_hash(record: HotelRecord) -> str: return hashlib.sha256(record.model_dump_json().encode()).hexdigest()
