# Public-release privacy removal, November 3, 2026

The superseded `results/archives/gdpopt_baron_highs_20261001_partial.tar.gz`
contained a GAMS license payload in a solver temporary directory. It and its
checksum sidecar have been removed from the distributable tree. The aggregate
archive checksum index omits only that archive's entry. The license contents
are not reproduced here.

The partial archive was historical evidence, not a current comparison input.
The completed RIC/GLOA campaign remains in
[`dantzig_gdp_compare_20261001_175249_6lvrs3wy.zip`](../results/archives/dantzig_gdp_compare_20261001_175249_6lvrs3wy.zip).
All 24 completed CSTR result/vector files in the partial snapshot were compared
with that final ZIP and are byte-identical. Other retained experiment records,
source snapshots, solver logs and their checksums are unchanged.

The [removal record](publication_sanitization.json) identifies the original
archive, sidecar and checksum-index hashes. Historical preservation inventories
remain unchanged: they describe the original private snapshots. Their references
to the removed archive are historical provenance. The Process preservation
verifier permits only these exact removals and the exact revised checksum index;
it continues to reject other missing or changed evidence.

The archive entered Git history at
`030f65b1645691c93c5fbf50ee9ad91b34b141c2`. The original local audit found it
in 243 reachable commit snapshots, including the default branch and topic
branches. Removing current files does not remove those historical copies.
Publish only a verified history that removes the archive at every revision,
or a new history-free sanitized repository. Keep the original Git database
and the quarantined archive private. Rewriting history changes commit IDs;
current manuscript snapshot links now use its clean equivalent,
`ea65c5339486b576008df68645ea68d22f7c7213`.
The [history report](publication_history.json) and
[commit map](publication_commit_map.tsv) retain the original-to-clean identities.

History cleanup does not revoke a license or erase independent clones and
GitHub pull-request/cached objects. The license administrator can determine
whether the license should be replaced. Any remote history replacement and
GitHub support request are separate actions from the local cleanup.
