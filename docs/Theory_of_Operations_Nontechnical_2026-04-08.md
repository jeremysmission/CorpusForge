# CorpusForge — Theory of Operations (Non-Technical)

**Author:** Jeremy Randall (CoPilot+)
**Date:** 2026-04-08 MDT
**Audience:** Program managers, operators, stakeholders
**Status:** Current

---

## What Is CorpusForge?

CorpusForge is the "data preparation engine" that runs overnight on a dedicated workstation. It takes raw documents — PDFs, spreadsheets, emails, presentations, and scanned images — and transforms them into a searchable, organized format that HybridRAG V2 can query the next morning.

Think of it like a librarian who works the night shift: every evening, they receive new documents, read them, catalog them, note the key people, parts, and dates mentioned, and file everything so that when you arrive in the morning and ask a question, the answer is ready.

---

## How It Works

### Every Night (Automatic)

1. **Check for new documents** — downloads any files that have been added or updated
2. **Remove duplicates** — about half of all files are copies (e.g., `Report.docx` + `Report_1.docx`). CorpusForge detects and skips them automatically, saving hours of unnecessary processing.
3. **Read every document** — supports 31 parser types covering 60+ formats including scanned PDFs (using OCR when Tesseract is installed)
4. **Break into searchable passages** — each document becomes a set of labeled paragraphs (~1,200 characters each)
5. **Optionally add context labels** — each passage can get a note like "This is from the 2024 Maintenance Report, about equipment failures"
6. **Create search indexes** — mathematical representations that allow fast similarity search (305 passages per second on GPU)
7. **Identify key facts** — part numbers, people, sites, dates, and organizations are flagged using pattern matching and AI extraction
8. **Package for morning** — everything is bundled into an export package ready for HybridRAG V2

### What Operators See

The pipeline can run fully automatically, or operators can use the GUI to:
- Start/stop pipeline runs
- Monitor progress (files processed, chunks created, vectors embedded)
- Adjust settings (number of workers, which stages to run)
- Review run history (last 10 runs with stats)
- Run a dedup-only pass to clean up duplicates before a full pipeline run

After each run, the operator can review:
- **run_report.txt** — what was processed, what was skipped, what failed
- **skip_manifest.json** — every deferred file listed with the reason it was skipped

### What Changes from Day to Day

Only new and updated documents are processed each night. If nothing changed, the run takes minutes. A full re-processing of all text documents takes about an hour. Adding image OCR extends that to 1-2 days.

---

## What Gets Deferred and Why

Not every file format is processed in every run. The operator controls what is deferred through a config file:

| Category | What Happens | Why |
|----------|-------------|-----|
| Text documents (PDF, Word, Excel, email) | **Processed** — these are the primary target | High-value searchable content |
| Images (JPG, PNG, etc.) | **Deferred** until OCR tools are installed | Requires Tesseract and Poppler native tools |
| Archives (ZIP, TAR) | **Deferred** | Nested extraction not yet supported |
| Sensor data (.rsf) | **Deferred** | Binary measurement data, not useful for question-answering |
| CAD/engineering drawings | **Identity card only** | Requires proprietary software to fully parse |

Every deferred file is still hashed and tracked. When the remaining tools are installed or capability is added, those files are automatically picked up in the next run.

---

## Why It's Separate from the Search App

In the previous version, document processing and the search engine were one application. This caused problems:
- Processing documents while someone was searching made everything slow
- You could not update the processor without restarting the search engine
- Testing one part required loading the other

CorpusForge and HybridRAG V2 are separate applications that communicate through files on disk. Simple, reliable, and independent.

---

Jeremy Randall | CorpusForge | 2026-04-08 MDT
