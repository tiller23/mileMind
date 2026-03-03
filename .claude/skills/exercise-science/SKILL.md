---
name: exercise-science
description: >
  Reference formulas and expected values for MileMind's deterministic
  physiological models. Banister, Daniels, ACWR, taper decay.
---

# Exercise Science Reference

## Banister Impulse-Response Model
- Fitness (CTL): exponential moving average, τ1 = 42 days (default)
- Fatigue (ATL): exponential moving average, τ2 = 7 days (default)
- Form (TSB): CTL - ATL
- Formula: w(t) = w(0) * e^(-t/τ)

## Daniels-Gilbert VO2 Equations
- VO2 = -4.60 + 0.182258 * v + 0.000104 * v^2  (v in m/min)
- %VO2max = 0.8 + 0.1894393 * e^(-0.012778 * t) + 0.2989558 * e^(-0.1932605 * t)
- Reference: github.com/mekeetsa/vdot

## ACWR Thresholds
- Safe zone: 0.8 - 1.3
- Warning zone: 1.3 - 1.5
- Hard cap: 1.5 (system rejects regardless of preference)
- Calculate with both rolling 7:28 day ratio AND EWMA

## Known Test Values (from equations)
- 5K in 20:00 → VDOT ≈ 49.8 (Daniels' published table says ~46.8; equations differ)
- Marathon in 3:30:00 → VDOT ≈ 44.6 (Daniels' published table says ~46.2; equations differ)
- CTL after 30 days of 50 TSS/day (τ=42): ~25.6
- Note: VDOT equation outputs differ from Daniels' book tables. Our implementation
  uses the exact Daniels-Gilbert regression equations from Gilbert (1979).

## Reference Repos
- Banister: GoldenCheetah (C++), choochoo (Python)
- VDOT: mekeetsa/vdot, st3v/running-formulas-mcp
- ACWR: ale-uy/Acute_Chronic_Workload_Ratio (Python)
- Monte Carlo: mountain-software-jp/trail-simulator (Python)
