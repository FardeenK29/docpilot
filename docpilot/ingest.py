"""Chunk the FastAPI docs, embed them locally and store them in Qdrant.

    python -m docpilot.ingest            # uses data/fastapi-src (see README)
"""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from .config import DATA_DIR, get_settings

DOCS_ROOT = DATA_DIR / "fastapi-src" / "docs" / "en" / "docs"
SITE = "https://fastapi.tiangolo.com"
SECTIONS = ["tutorial", "advanced", "how-to", "deployment"]
TOP_LEVEL = ["async.md", "python-types.md", "features.md", "fastapi-cli.md",
             "environment-variables.md", "virtual-environments.md"]
ANCHOR = re.compile(r"\s*\{\s*#([\w-]+)\s*\}\s*$")


def doc_files() -> list[Path]:
    files = [DOCS_ROOT / f for f in TOP_LEVEL if (DOCS_ROOT / f).exists()]
    for s in SECTIONS:
        files += sorted((DOCS_ROOT / s).rglob("*.md"))
    return files


def page_url(path: Path) -> str:
    rel = path.relative_to(DOCS_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "index":
        parts = parts[:-1]
    return f"{SITE}/{'/'.join(parts)}/" if parts else f"{SITE}/"


def clean(text: str) -> str:
    text = re.sub(r"\{\*.*?\*\}", "", text)                       # code-include directives
    text = re.sub(r"^///.*$", "", text, flags=re.M)                # admonition fences
    text = re.sub(r"<dfn title=\"[^\"]*\">([^<]*)</dfn>", r"\1", text)
    text = re.sub(r"<abbr title=\"[^\"]*\">([^<]*)</abbr>", r"\1", text)
    text = re.sub(r"<img[^>]*>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_page(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    headers = [("#", "h1"), ("##", "h2"), ("###", "h3")]
    sections = MarkdownHeaderTextSplitter(headers, strip_headers=False).split_text(raw)
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=120)
    url = page_url(path)
    page = str(path.relative_to(DOCS_ROOT))
    title = ANCHOR.sub("", raw.splitlines()[0].lstrip("# ")).strip()
    chunks = []
    for sec in sections:
        heading_raw = sec.metadata.get("h3") or sec.metadata.get("h2") or sec.metadata.get("h1") or title
        m = ANCHOR.search(heading_raw)
        heading = ANCHOR.sub("", heading_raw).strip()
        text = clean(ANCHOR.sub("", sec.page_content))
        for piece in splitter.split_text(text):
            if len(piece) < 80:
                continue
            chunks.append({"text": piece, "page": page, "title": title, "heading": heading,
                           "url": url + (f"#{m.group(1)}" if m else "")})
    return chunks


def main() -> None:
    s = get_settings()
    files = doc_files()
    chunks = [c for f in files for c in chunk_page(f)]
    print(f"{len(files)} pages -> {len(chunks)} chunks")

    emb = OllamaEmbeddings(model=s.embed_model, base_url=s.ollama_url)
    t = time.perf_counter()
    vectors = []
    for i in range(0, len(chunks), 64):
        batch = chunks[i:i + 64]
        # nomic-embed-text expects task prefixes
        vectors += emb.embed_documents([f"search_document: {c['title']} - {c['heading']}\n{c['text']}" for c in batch])
        print(f"  embedded {min(i + 64, len(chunks))}/{len(chunks)}", end="\r")
    print(f"\nembedding took {time.perf_counter() - t:.1f}s")

    client = QdrantClient(path=s.qdrant_path)
    if client.collection_exists(s.collection):
        client.delete_collection(s.collection)
    client.create_collection(s.collection, vectors_config=VectorParams(size=len(vectors[0]), distance=Distance.COSINE))
    client.upsert(s.collection, points=[
        PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{c['url']}|{i}")), vector=v, payload=c)
        for i, (c, v) in enumerate(zip(chunks, vectors))])
    print(f"stored {client.count(s.collection).count} vectors in {s.qdrant_path}")
    client.close()


if __name__ == "__main__":
    main()
