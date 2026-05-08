## 2026-05-08

- Kept query helpers fully pure and side-effect free.
- Enforced strict v1 behavior: no antimeridian bbox support, no open datetime intervals, no repeat/multi-level z syntax.
- Used case-sensitive CRS validation and case-insensitive CoverageJSON negotiation as specified.
