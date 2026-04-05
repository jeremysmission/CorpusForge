# CorpusForge — Theory of Operations (Non-Technical)

**Author:** Jeremy Randall (CoPilot+)
**Date:** 2026-04-04 MDT
**Audience:** Program managers, operators, stakeholders
**Status:** Preliminary

---

## What Is CorpusForge?

CorpusForge is the "data preparation engine" that runs overnight on a dedicated workstation. It takes raw documents — PDFs, spreadsheets, emails, presentations, scanned images — and transforms them into a searchable, organized format that HybridRAG V2 can query the next morning.

Think of it like a librarian who works the night shift: every evening, they receive new documents, read them, catalog them, note the key people/parts/dates mentioned, and file everything so that when you arrive in the morning and ask a question, the answer is ready.

---

## How It Works

### Every Night (Automatic)

1. **Check for new documents** — downloads any files that have been added or updated
2. **Remove duplicates** — over half the files are copies; CorpusForge detects and skips them
3. **Read every document** — supports 32+ formats including scanned PDFs (using OCR)
4. **Break into searchable passages** — each document becomes a set of labeled paragraphs
5. **Add context labels** — each passage gets a note like "This is from the 2024 Thule Maintenance Report, about equipment failures"
6. **Create search indexes** — mathematical representations that allow fast similarity search
7. **Identify key facts** — part numbers, people, sites, dates are flagged for structured lookup
8. **Package for morning** — everything is bundled and ready for HybridRAG V2

### What Operators See

Nothing. CorpusForge runs automatically on a schedule. If an operator wants to check on it, there's a simple monitoring screen showing:
- Last run status (success/failure)
- How many documents were processed
- How long it took
- Any files that couldn't be read (with error details)

### What Changes from Day to Day

Only new and updated documents are processed each night. If nothing changed, the run takes minutes. A full re-processing of all 420,000 documents takes a few days but only happens once.

---

## Why It's Separate from the Search App

In V1, the document processing and the search engine were one application. This caused problems:
- Processing documents while someone was searching made everything slow
- You couldn't update the processor without restarting the search engine
- Testing one part required loading the other

CorpusForge and HybridRAG V2 are separate applications that talk through files on disk. Simple, reliable, and independent.

---

Jeremy Randall | CorpusForge | 2026-04-04 MDT
