# CorpusForge — Architecture Pseudocode & Block Diagram

**Author:** Jeremy Randall (CoPilot+)
**Repo:** CorpusForge
**Date:** 2026-04-04 MDT
**Design Rule:** All classes < 500 lines of code (comments excluded)

---

## 1. Pipeline Block Diagram

```
  CONFIG (config.yaml)
       |
       v
  +--PIPELINE ORCHESTRATOR (pipeline.py)--+
  |                                        |
  |  [1] DOWNLOAD & SYNC                  |
  |      syncer.py -> data/source/         |
  |                                        |
  |  [2] HASH & DEDUPLICATE               |
  |      hasher.py + deduplicator.py       |
  |      State DB: file_state.sqlite3      |
  |            |                           |
  |            v                           |
  |      new_files[] + changed_files[]     |
  |                                        |
  |  [3] PARSE                             |
  |      dispatcher.py -> parsers/         |
  |      pdf | docx | xlsx | pptx | csv    |
  |      msg | html | txt | rtf | ...      |
  |      quality_scorer.py (0.0-1.0)       |
  |      ocr.py (scanned PDF fallback)     |
  |            |                           |
  |            v                           |
  |      parsed_docs[]                     |
  |                                        |
  |  [4] CHUNK                             |
  |      chunker.py (1200/200/sentence)    |
  |      chunk_ids.py (SHA-256 IDs)        |
  |            |                           |
  |            v                           |
  |      chunks[]                          |
  |                                        |
  |  [5] ENRICH                            |
  |      enricher.py + ollama_client.py    |
  |      phi4:14B on GPU (free, local)     |
  |            |                           |
  |            v                           |
  |      enriched_chunks[]                 |
  |                                        |
  |  [6] EMBED                             |
  |      embedder.py + batch_manager.py    |
  |      nomic-embed-text v1.5 (768d)      |
  |      CUDA primary, ONNX fallback       |
  |            |                           |
  |            v                           |
  |      vectors[] (float16)               |
  |                                        |
  |  [7] EXTRACT                           |
  |      ner_extractor.py (GLiNER2, CPU)   |
  |            |                           |
  |            v                           |
  |      candidate_entities[]              |
  |                                        |
  |  [8] EXPORT                            |
  |      packager.py -> data/output/       |
  |      manifest.py -> manifest.json      |
  |      run_report.json                   |
  |                                        |
  +----------------------------------------+
       |
       v
  EXPORT PACKAGE (consumed by HybridRAG V2)
  data/output/
    chunks.jsonl
    vectors/
    entities.jsonl
    manifest.json
    run_report.json
```

---

## 2. Module Pseudocode

### 2.1 Pipeline Orchestrator (`src/pipeline.py`)

```python
class Pipeline:
    """Orchestrates all stages. Each stage is independent and checkpointed."""

    def __init__(self, config: ForgeConfig):
        self.config = config
        self.syncer = Syncer(config.paths.source_dirs, config.paths.landing_zone)
        self.hasher = Hasher(config.paths.state_db)
        self.deduplicator = Deduplicator(self.hasher)
        self.dispatcher = ParseDispatcher(config.parse)
        self.chunker = Chunker(config.chunk.size, config.chunk.overlap)
        self.enricher = Enricher(config.enrich)
        self.embedder = Embedder(config.embed)
        self.extractor = NERExtractor(config.extract)
        self.packager = Packager(config.paths.output_dir)

    def run(self, full_reindex: bool = False):
        """Run full pipeline. Incremental by default."""
        run_stats = RunStats()

        # Stage 1: Download
        new_files = self.syncer.sync()
        run_stats.downloaded = len(new_files)

        # Stage 2: Hash & dedup
        if full_reindex:
            work_files = self.hasher.get_all_files()
        else:
            work_files = self.deduplicator.filter_new_and_changed(new_files)
        run_stats.to_process = len(work_files)

        # Stage 3: Parse
        parsed_docs = []
        for file_path in work_files:
            try:
                doc = self.dispatcher.parse(file_path)
                parsed_docs.append(doc)
                run_stats.parsed += 1
            except ParseError as e:
                run_stats.log_error(file_path, e)

        # Stage 4: Chunk
        all_chunks = []
        for doc in parsed_docs:
            chunks = self.chunker.chunk(doc.text, doc.source_path)
            all_chunks.extend(chunks)
        run_stats.chunks_created = len(all_chunks)

        # Stage 5: Enrich
        if self.config.enrich.enabled:
            all_chunks = self.enricher.enrich_batch(all_chunks)
            run_stats.chunks_enriched = len(all_chunks)

        # Stage 6: Embed
        vectors = self.embedder.embed_batch(
            [c.enriched_text or c.text for c in all_chunks]
        )
        run_stats.vectors_created = len(vectors)

        # Stage 7: Extract entities
        if self.config.extract.enabled:
            entities = self.extractor.extract_batch(all_chunks)
            run_stats.entities_extracted = len(entities)
        else:
            entities = []

        # Stage 8: Export
        self.packager.export(all_chunks, vectors, entities, run_stats)

        return run_stats
```

### 2.2 Deduplicator (`src/download/deduplicator.py`)

```python
class Deduplicator:
    """Detects and eliminates duplicate files before processing."""

    def filter_new_and_changed(self, files: list[Path]) -> list[Path]:
        """Return only files that are new or changed since last run."""
        work_list = []
        for path in files:
            content_hash = self.hasher.hash_file(path)
            previous_hash = self.hasher.get_stored_hash(path)

            if content_hash == previous_hash:
                continue  # unchanged, skip

            # Check for _1 suffix duplicates
            if self.is_suffix_duplicate(path, content_hash):
                continue  # content-identical duplicate, skip

            self.hasher.update_hash(path, content_hash)
            work_list.append(path)

        return work_list

    def is_suffix_duplicate(self, path: Path, content_hash: str) -> bool:
        """Check if this file is a _1 suffix copy of another file."""
        stem = path.stem
        if stem.endswith('_1'):
            original_stem = stem[:-2]
            original_path = path.with_stem(original_stem)
            if original_path.exists():
                original_hash = self.hasher.hash_file(original_path)
                if original_hash == content_hash:
                    return True  # identical content, skip the _1 version
        return False
```

### 2.3 Parse Dispatcher (`src/parse/dispatcher.py`)

```python
PARSER_MAP = {
    '.pdf': PDFParser,
    '.docx': DocxParser,
    '.xlsx': XlsxParser,
    '.pptx': PptxParser,
    '.csv': CsvParser,
    '.txt': TxtParser,
    '.md': TxtParser,
    '.msg': MsgParser,
    '.html': HtmlParser,
    '.htm': HtmlParser,
    '.rtf': RtfParser,
    '.json': JsonParser,
    '.xml': XmlParser,
    # ... 32+ formats
}

class ParseDispatcher:
    """Routes files to the appropriate parser based on extension."""

    def parse(self, file_path: Path) -> ParsedDocument:
        ext = file_path.suffix.lower()
        parser_class = PARSER_MAP.get(ext)
        if parser_class is None:
            raise ParseError(f"Unsupported format: {ext}")

        parser = parser_class(timeout=self.config.timeout_seconds)
        text = parser.parse(file_path)

        quality = self.quality_scorer.score(text, file_path)

        return ParsedDocument(
            source_path=str(file_path),
            text=text,
            parse_quality=quality,
            file_ext=ext,
            file_size=file_path.stat().st_size,
        )
```

### 2.4 Chunker (`src/chunk/chunker.py`)

```python
class Chunker:
    """Fixed-size chunking with sentence-boundary awareness."""

    def __init__(self, chunk_size: int = 1200, overlap: int = 200):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str, source_path: str) -> list[Chunk]:
        chunks = []
        start = 0
        chunk_index = 0

        while start < len(text):
            end = start + self.chunk_size

            # Find sentence boundary near the end
            if end < len(text):
                boundary = self.find_sentence_boundary(text, end)
                if boundary > start:
                    end = boundary

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunk_id = generate_chunk_id(source_path, chunk_index)
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    text=chunk_text,
                    source_path=source_path,
                    chunk_index=chunk_index,
                    text_length=len(chunk_text),
                ))
                chunk_index += 1

            start = end - self.overlap

        return chunks
```

### 2.5 Enricher (`src/enrich/enricher.py`)

```python
class Enricher:
    """Contextual enrichment via phi4:14B on local Ollama."""

    ENRICHMENT_PROMPT = """Given this document chunk, provide a brief context prefix
(1-2 sentences) that situates it within its source document. Include the document
topic, section context, and any key entities mentioned. Answer only with the
context prefix, nothing else.

Source file: {source_path}
Chunk text: {chunk_text}"""

    def __init__(self, config):
        self.client = OllamaClient(config.ollama_url, model="phi4:14b-q4_K_M")

    def enrich_batch(self, chunks: list[Chunk]) -> list[Chunk]:
        """Add contextual prefix to each chunk. Checkpointed for resume."""
        for chunk in chunks:
            if chunk.enriched_text:
                continue  # already enriched (resume case)
            try:
                context = self.client.generate(
                    self.ENRICHMENT_PROMPT.format(
                        source_path=chunk.source_path,
                        chunk_text=chunk.text[:500]  # first 500 chars for speed
                    )
                )
                chunk.enriched_text = f"[{context.strip()}]\n{chunk.text}"
            except Exception as e:
                chunk.enriched_text = chunk.text  # fallback: use raw text
                log.warning(f"Enrichment failed for {chunk.chunk_id}: {e}")
        return chunks
```

### 2.6 Embedder (`src/embed/embedder.py`)

```python
class Embedder:
    """Three-tier embedding: CUDA -> ONNX -> error. No Ollama fallback."""

    def __init__(self, config):
        self.model_name = config.model_name  # "nomic-ai/nomic-embed-text-v1.5"
        self.dim = config.dim  # 768
        self.device = self.detect_device()
        self.model = self.load_model()
        self.batch_manager = BatchManager(config.max_batch_tokens)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Embed texts with token-budget batching and OOM backoff."""
        all_vectors = []
        for batch in self.batch_manager.create_batches(texts):
            try:
                vectors = self.model.encode(
                    batch,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                all_vectors.append(vectors.astype(np.float16))
            except RuntimeError as e:
                if "out of memory" in str(e).lower():
                    self.batch_manager.reduce_batch_size()
                    # retry with smaller batch
                    vectors = self.retry_with_smaller_batches(batch)
                    all_vectors.append(vectors)
                else:
                    raise
        return np.vstack(all_vectors)
```

### 2.7 Export Packager (`src/export/packager.py`)

```python
class Packager:
    """Builds the export package consumed by HybridRAG V2."""

    def export(self, chunks: list[Chunk], vectors: np.ndarray,
               entities: list[RawEntity], stats: RunStats):
        """Write all artifacts to output directory."""
        output_dir = self.output_dir / f"export_{datetime.now():%Y%m%d_%H%M}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # chunks.jsonl
        with open(output_dir / "chunks.jsonl", "w") as f:
            for chunk in chunks:
                f.write(json.dumps({
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "enriched_text": chunk.enriched_text,
                    "source_path": chunk.source_path,
                    "chunk_index": chunk.chunk_index,
                    "text_length": chunk.text_length,
                    "parse_quality": chunk.parse_quality,
                }) + "\n")

        # vectors (numpy save, float16)
        np.save(output_dir / "vectors.npy", vectors)

        # entities.jsonl
        with open(output_dir / "entities.jsonl", "w") as f:
            for entity in entities:
                f.write(json.dumps({
                    "text": entity.text,
                    "type": entity.type,
                    "confidence": entity.confidence,
                    "chunk_id": entity.chunk_id,
                    "source_path": entity.source_path,
                }) + "\n")

        # manifest.json
        manifest = {
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
            "chunk_count": len(chunks),
            "vector_dim": 768,
            "vector_dtype": "float16",
            "embedding_model": "nomic-embed-text-v1.5",
            "enrichment_model": "phi4:14b-q4_K_M",
            "entity_count": len(entities),
            "stats": stats.to_dict(),
        }
        with open(output_dir / "manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)

        # Symlink "latest" for V2 to find
        latest_link = self.output_dir / "latest"
        if latest_link.exists():
            latest_link.unlink()
        latest_link.symlink_to(output_dir)
```

---

## 3. Data Flow Between CorpusForge and HybridRAG V2

```
CORPUSFORGE                              HYBRIDRAG V2
===========                              =============

[Nightly 02:00 AM]                       [Startup / triggered]
    |                                         |
    v                                         v
Parse + Chunk + Enrich                   Check data/source/latest/
+ Embed + Extract                        for new manifest.json
    |                                         |
    v                                         v
data/output/latest/                      Import:
  chunks.jsonl ------>                     Load chunks + vectors -> LanceDB
  vectors.npy ------->                     GPT-4o 2nd-pass extraction
  entities.jsonl ---->                     Quality gate + normalize
  manifest.json ----->                     Docling table extraction
                                           Promote to SQLite
                                              |
                                              v
                                           Ready for queries
```

---

Jeremy Randall | CorpusForge | 2026-04-04 MDT
