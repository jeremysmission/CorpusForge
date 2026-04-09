# Simulation Data — Dedup Findings

**Date:** 2026-04-08 | **Author:** Agent 1 (Forge Coder)
**Data Source:** C:\CorpusForge\ProductionSource\verified\source\verified\ (87 GB)

---

## Summary

| Metric | Value |
|--------|-------|
| Total files | 53,750 |
| Unique files (after dedup) | 27,015 |
| Duplicates removed | 26,735 (49.7%) |
| Dedup throughput | 204.6 files/sec |
| Dedup elapsed | 262.7s (4.4 min) |

**Finding:** Exactly half the corpus is duplicate files, primarily the `_1` suffix pattern
(e.g., `Report.docx` + `Report_1.docx` with identical content). This matches V1 measurements
(55.6% dupes in V1).

---

## Format Distribution (27,015 unique files)

| Format | Count | % | Category |
|--------|-------|---|----------|
| .jpg | 14,623 | 54.1% | Image — OCR or skip |
| .zip | 6,551 | 24.2% | Archive — deferred |
| .sao | 1,388 | 5.1% | Sensor data — deferred |
| .rsf | 1,379 | 5.1% | Sensor data — deferred |
| .pdf | 1,132 | 4.2% | Text — primary target |
| .docx | 416 | 1.5% | Text — primary target |
| .png | 331 | 1.2% | Image — OCR or skip |
| .xml | 315 | 1.2% | Structured — parseable |
| .jpeg | 281 | 1.0% | Image — OCR or skip |
| .xlsx | 266 | 1.0% | Spreadsheet — parseable |
| .doc | 128 | 0.5% | Text — primary target |
| .txt | 56 | 0.2% | Text — primary target |
| .msg | 32 | 0.1% | Email — parseable |
| .pptx | 29 | 0.1% | Presentation — parseable |
| .ini | 26 | 0.1% | Config — low value |
| .xls | 25 | 0.1% | Spreadsheet — parseable |
| .ppt | 11 | <0.1% | Presentation — parseable |
| .html | 9 | <0.1% | Text — parseable |
| .log | 7 | <0.1% | Log — low value |
| .dxf | 2 | <0.1% | CAD — specialty parser |

---

## Key Findings

### 1. Image Dominance
55% of unique files are images (JPG/JPEG/PNG). These need:
- OCR via Tesseract if they contain text (site visit photos with signage, equipment labels)
- Skip if they are pure photographs (site visit scenery)
- Recommendation: Run OCR in `auto` mode, let quality scoring filter garbage

### 2. Archive Volume
24% are ZIP files. These are likely:
- Bundled deliverables or site visit packages
- May contain parseable files inside (nested extraction not yet supported)
- Recommendation: Defer for now, document as known gap

### 3. Sensor Data Files
10% are `.SAO` and `.RSF` files — domain-specific sensor measurement data.
These are binary scientific formats, not text. Defer to skip list.

### 4. Parseable Text (~2,100 files)
The actual text corpus after filtering images/archives/sensor data:
- PDF: 1,132
- DOCX: 416
- DOC: 128
- XLSX: 266
- XLS: 25
- XML: 315
- TXT: 56
- PPTX: 29
- PPT: 11
- HTML: 9
- MSG: 32
- **Total parseable: ~2,419 files**

### 5. Dedup Pattern
The `_1` suffix pattern is the dominant duplication vector, confirming V1 findings.
Content-hash dedup catches additional cross-name duplicates (same content, different filenames).

---

## Recommendations for Full 700GB Ingest

1. **Dedup first** — always run dedup before parse. 50% volume reduction saves hours.
2. **Skip images for initial pass** — OCR adds significant time. Process text first, images second.
3. **Defer ZIP/SAO/RSF** — document in skip manifest, tackle in future sprint.
4. **Target ~2,400 text files** from 87GB — the actual retrievable corpus is small but high-value.
5. **Hash continuity** — dedup state DB persists. When remaining 610GB arrives, already-processed files are automatically skipped.

---

Signed: Agent 1 (Forge Coder) | CorpusForge | 2026-04-08 | MDT
