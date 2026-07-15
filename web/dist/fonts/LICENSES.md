# Fonts vendored here

All four families are licensed under the SIL Open Font License 1.1, which allows
bundling and redistribution and requires the license to travel with the files.
Helicon is open source, so the licenses live next to the fonts they cover rather
than in a footnote.

| Family | Files | Copyright |
| --- | --- | --- |
| Fraunces | `Fraunces-latin*.woff2` (variable, wght 300..900) | Copyright 2018 The Fraunces Project Authors |
| Bricolage Grotesque | `BricolageGrotesque-latin*.woff2` (variable, wght 400..700) | Copyright 2022 The Bricolage Grotesque Project Authors |
| IBM Plex Mono | `IBMPlexMono-{400,500,600}-latin*.woff2` | Copyright 2017 IBM Corp, Reserved Font Name "Plex" |
| Source Sans 3 | `SourceSans3-latin*.woff2` (variable, wght 200..900) | Copyright 2010-2020 Adobe, Reserved Font Name "Source" |

Full license text: `OFL-<family>.txt` in this directory.

The `.ttf` counterparts in `mac/Sources/Helicon/Fonts/` are the same families
under the same license; CoreText cannot read woff2, so the app bundles TTFs.

## Regenerating

The woff2 files are Google's latin/latin-ext subsets, fetched once from the CSS
API with a modern user agent. Fraunces, Bricolage and Source Sans 3 are variable:
Google serves one file per subset carrying the whole weight axis regardless of
the range requested, which is why there are 12 files and not 20.
