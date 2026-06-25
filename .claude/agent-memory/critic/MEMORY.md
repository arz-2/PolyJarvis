# Critic Memory Index

- [Hardware require[0] mpi>=4 stale clause](hardware-require-mpi4-stale-clause.md) — don't false-flag PCFF/OPLS kokkos mpi=1; the "never launch mpi=1" clause is the stale GPU-package rule, KOKKOS mpi=1 is correct
- [Tg ladder steps-per-T floor arithmetic](tg-ladder-steps-floor-arithmetic.md) — always recompute N=tg_t_step/(rate*dt*1e-6)>=200000 yourself; PVC4 planner wrongly claimed 100 ps clears the 200 ps floor
- [hardware_policy.host field is stale](hardware-policy-host-field-stale.md) — top-level host (Quadro RTX 6000) lags actual A800; compare live host to directional_probe.measured_on, not hardware_policy.host
- [D-05 ct_gate_reliable decouples DP>=30 carve-out](d05-ct-gate-reliable-decouples-dp30.md) — don't false-flag overall_pass=true on a DP<30 aromatic; ct_gate_reliable=false suppresses melt-diffusion arming regardless of DP
