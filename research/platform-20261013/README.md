# Recovered driver research, 2026-10-13

Preserved from Claude's camera, S Pen and S2MPB02 agents after the session
limit stopped their parent. These files are **unreviewed experimental inputs**,
not part of the kernel patch stack and not installed on the tablet.

The camera agent completed its report. The S Pen agent left a driver patch
and device tree before an API limit stopped it; no final report or build test
was completed. The S2MPB02 agent provided a draft driver and source analysis,
but chip presence and rail consumers remain uncertain.

Camera power wiring in the Samsung source resolves to PM8994 regulators;
the earlier hardware notes naming S2MPB02 as a camera prerequisite were wrong.
The camera fragment still contains assumptions about the core supply, lane
count and addresses. Resolve those before applying power or starting capture.

Scratch paths in the original notes are provenance references. Agent artifacts
are retained here without changing their original claims; subsequent verified
results belong in the project's hardware notes. Source-file licence headers
apply to the draft code; no vendor firmware is included.
