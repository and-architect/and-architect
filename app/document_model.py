import json
import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List


@dataclass
class DocumentMetadata:
    title: str = "Unbenannte Dissertation"
    author: str = ""
    institution: str = ""
    supervisor: str = ""
    date: str = ""
    abstract: str = ""
    keywords: List[str] = field(default_factory=list)
    bibliography_style: str = "apa"
    language: str = "de"
    subject: str = ""


@dataclass
class Document:
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)
    content: dict = field(default_factory=dict)
    notes: str = ""
    citations: List[dict] = field(default_factory=list)
    frames: List[dict] = field(default_factory=list)  # floating frames
    file_path: Optional[str] = None
    modified: bool = False

    def to_dict(self) -> dict:
        return {
            "version": "1.0",
            "saved_at": datetime.datetime.now().isoformat(),
            "metadata": asdict(self.metadata),
            "content": self.content,
            "notes": self.notes,
            "citations": self.citations,
            "frames": self.frames,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Document":
        doc = cls()
        meta = data.get("metadata", {})
        valid_keys = DocumentMetadata.__dataclass_fields__.keys()
        doc.metadata = DocumentMetadata(**{k: v for k, v in meta.items() if k in valid_keys})
        doc.content = data.get("content", {})
        doc.notes = data.get("notes", "")
        doc.citations = data.get("citations", [])
        doc.frames = data.get("frames", [])
        return doc

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        self.file_path = path
        self.modified = False

    @classmethod
    def load(cls, path: str) -> "Document":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        doc = cls.from_dict(data)
        doc.file_path = path
        return doc
