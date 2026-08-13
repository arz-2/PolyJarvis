# literature-grounding-worker memory

- [Sharma2016 DOI typo in polymer_rules.json](feedback_sharma2016_doi_typo_polymer_rules.md) — 10.1021/jp510632u 404s; correct is 10.1021/acs.jpcb.5b10789; flag, don't self-edit
- [Paywalled CTE numeric values](feedback_paywalled_cte_numeric_values.md) — ACS/Elsevier/Springer full-text 403 via WebFetch; accept low-confidence null alpha rather than retry-loop
- [Search-snippet misattribution](feedback_search_snippet_misattribution.md) — WebSearch summary attributed a PEEK Tg number to Suter2025 (epoxy-only paper, no PEEK); always WebFetch the real source, ignore self-referential PolyJarvis arxiv hits
- [Bash scope blocks polymer_rules.json reads](feedback_bash_scope_blocks_polymer_rules_grep.md) — jq/grep/python3 on guides/polymer_rules.json denied even read-only; use Read tool with offset/limit paging for step 7's class-existence check
- [docs/ output path unvalidatable](feedback_docs_output_path_unvalidatable.md) — Write to output_path outside data/** succeeds but Read/Bash(jq) on that same path denied; no self-verify loop possible for non-data/ output_path
