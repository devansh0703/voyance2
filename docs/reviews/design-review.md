# Design Review — Voyance II UI (plan-design-review)
**Verdict: APPROVE — de-slop direction is correct and opinionated.**

## What changed (vs v1 which WAS slop)
- Killed: aurora gradient mesh, glassmorphism blur, shimmer text, bioluminescent-cyan-on-navy glow, oversized rounded cards. These are the exact tells listed in de-slopification guides (UX Collective 2026; MindStudio 2026).
- Adopted: Bloomberg-terminal density — flat #0b0d0c surface, hairline #2a2f2b rules, JetBrains Mono for every datum, single amber accent #ffb454, uppercase 10px microtype labels, dense `table.dense` with 1px row rules, sharp corners, no shadows.
- Typography: Sora only for page titles; everything data-adjacent is mono. Irregularity comes from the dense asymmetric grid (380px register rail vs fluid map), not decoration.

## Checklist findings
1. Contrast: dim #8b948c on #121513 ≈ 4.6:1 — passes AA for small text at 12px mono. ✓
2. Empty states: every panel has an honest "not generated/loading" state — no skeletons pretending data. ✓
3. Motion: only the ticker stream animates; reduced-motion kills it. ✓
4. Map chrome: MapLibre controls restyled flat; heading vectors use the accent. ✓
5. Risk: amber accent overuse — cap at ≤3 accent elements per viewport. Watch in QA pass.
