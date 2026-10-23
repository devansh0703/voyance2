# DevEx Review — Voyance II (plan-devex-review)
**Verdict: APPROVE WITH 2 FOLLOW-UPS**

1. **One-command lifecycle**: `make dev2` should boot API+web concurrently; today `make api` + `make web` are separate. FOLLOW-UP added to Makefile.
2. **Module imports**: backend.live modules import via package path; train_v2 needed sys.path fix for ROOT — added regression note in the voyance-maritime skill instead of a fragile .pth hack. RESOLVED.
3. Live adapters all route through one `cached()` TTL helper — adding source #16 is a 15-line function. ✓
4. Tests run offline via committed fixtures (carried from v1) — CI stays green without network. ✓
5. Logs live in repo `logs/` (owner rule: never /tmp). ✓
