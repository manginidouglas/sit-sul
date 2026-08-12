# Frozen OSM input

The committed manifest describes the real 2.07 GB Brazil PBF downloaded on
2026-08-12. The PBF is ignored by Git. `scripts/routing/download_osm.sh` validates
its official MD5, locally calculated SHA-256, and size. A valid existing raw is
reused; an invalid existing raw causes a hard failure and is never replaced.
