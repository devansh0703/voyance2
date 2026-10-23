# Office Hours — Voyance II consultation record
**Auto-decided per owner standing directive** ("don't ask me; choose recommended"; never ask permission).

## Questions brought to the table
1. **Q: live AIS source with zero signup?** → Digitraffic Finland Marine AIS (CC BY 4.0, keyless REST, ~1 Hz national feed) as primary; Danish Maritime Authority AIS listed as documented secondary (endpoint flakiness observed historically); NOAA archives remain the training corpus. Decision: ship Digitraffic now.
2. **Q: GPU vs CPU boundary?** → Training (XGBoost CUDA quantiles + GPU random forest) on RTX 4060; inference and small sklearn fits (IsolationForest/GMM/HMM, <2 s) stay CPU — putting those on GPU would add transfer overhead for no wall-clock win. Owner directive interpreted as: never train big models on CPU. Recorded.
3. **Q: keep v1 quantile ETA or retrain?** → Keep (already GPU, 4.49 h MAE); v2 adds RF runtime + anomaly + HMM artifacts alongside.
4. **Q: UI direction?** → Terminal-editorial de-slop (see design review). Research-backed (UX Collective de-slopification; Bloomberg Terminal density).
