---
name: pla_backbone_ester_oxygen_type
description: PLA backbone path includes ester-bridging o_2, not pendant o_1; coordination+PCFF convention determines type
metadata:
  type: feedback
---

PLA (polyester) backbone is `...–o_2–c1–c_1–o_2–c1–c_1–...`, where:
- `o_2` (type 7) bridges two repeat units: bonded to carbonyl c_1 of one unit AND secondary c1 of the next
- `o_1` (type 6) is a pendant carbonyl oxygen: bonded only to c_1 within a single unit

Coordination number + PCFF convention settles this:
- From bond dump: type-7 o_2 has two heavy neighbours (c_1 and c1), type-6 o_1 has one (c_1 only)
- PCFF naming: o_1 = C=O pendant, o_2 = C–O ether/ester bridging

**Why:** Mistakenly selected [2,3,6] (c1, c_1, o_1) which covers only 2/3 of the backbone. This yields `backbone_type_coverage ≈ 0.67 << 0.90`, forcing a re-run.

**How to apply:** For any polyester (PLA, PCL, PET, etc.), verify o_1 vs o_2 coordination by checking the bond list. The ester-connecting oxygen is always o_2.
