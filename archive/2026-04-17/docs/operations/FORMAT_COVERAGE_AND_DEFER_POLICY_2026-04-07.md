# Format Coverage And Defer Policy 2026-04-07

## Purpose

Show what `CorpusForge` does with major file families today.

This is the operator-facing answer to:

- what parses now
- what only gets placeholder text
- what the rebuild-speed profile hash-skips
- what is still outside current support

---

## Coverage Classes

### Fully Parsed Now

Representative families with real parser coverage:

- Office and text:
  - `.docx`, `.doc`, `.xlsx`, `.xls`, `.pptx`, `.ppt`, `.rtf`
  - `.txt`, `.md`, `.rst`, `.log`, `.ini`, `.cfg`, `.conf`, `.yaml`, `.yml`, `.properties`, `.reg`, `.sao`, `.rsf`
  - `.csv`, `.tsv`, `.json`, `.xml`
- PDF and image OCR:
  - `.pdf`, `.ai`
  - `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.bmp`, `.wmf`, `.emf`, `.tif`, `.tiff`
- Email and archives:
  - `.msg`, `.eml`, `.mbox`
  - `.zip`, `.tar`, `.tgz`, `.gz`, `.7z`
- Open and specialist formats:
  - `.epub`
  - `.odt`, `.ods`, `.odp`
  - `.vsdx`
  - `.cer`, `.crt`, `.pem`
  - `.dxf`
  - `.stp`, `.step`, `.ste`
  - `.enterprise program`, `.iges`
  - `.stl`
  - `.evtx`
  - `.pcap`, `.pcapng`
  - `.accdb`, `.mdb`
  - `.psd`

### Placeholder-Only Recognized

These formats are recognized and produce searchable identity text, but not full content extraction:

- `.dwg`, `.dwt`
- `.prt`, `.sldprt`
- `.asm`, `.sldasm`
- `.mpp`
- `.vsd`
- `.one`
- `.ost`
- `.eps`

These should be treated as visible-but-not-fully-parsed.

### Deferred By Default Skip List

Current repo skip list defers:

- `.dwf`

These files are hashed and written to `skip_manifest.json`, not parsed.

### Deferred By Rebuild-Speed Profile

Current rebuild-speed profile:

- [config.hash_skip_drawings.yaml](/C:/CorpusForge/config/config.hash_skip_drawings.yaml)

It hash-skips these for faster restart-safe rebuild prep:

- `.dwg`, `.dwt`, `.dxf`
- `.stp`, `.step`, `.ste`
- `.enterprise program`, `.iges`
- `.stl`
- `.vsdx`, `.drawio`, `.svg`, `.dia`
- `.psd`

This is a run-profile choice, not a permanent parser limitation.

### Unsupported

Anything outside the live parser registry and outside the defer maps is currently unsupported.

Unsupported files:

- are surfaced in CLI/GUI preflight
- are excluded from the current parse run
- can be backfilled into `file_state` with the legacy skip-state audit tool

---

## Operational Rules

### AWS Analysis Sample

Bias toward broad coverage:

- do not use the rebuild-speed defer profile unless the sample explicitly wants hash-skip behavior
- include difficult formats when possible
- accept slower chunking in exchange for better coverage data

### Recovery Rebuild

Bias toward restart-safe throughput:

- use the rebuild-speed profile when needed
- hash-skip heavy drawing/CAD families if that is required to keep completion realistic
- keep those files visible in `skip_manifest.json` and `file_state`

### Canonical Review

Do not confuse placeholder-only recognition with full parse coverage.

If a canonical family depends on content that only exists in placeholder-only formats, that family should be flagged rather than treated as fully recoverable text.
