# Telemetry, Data Contracts, and Pipeline Design — Research Dossier

> Research for the chess-coach analytics-engineering portfolio: app events → pipeline →
> warehouse (DuckDB + dbt locally, optionally cheap cloud) → marts/KPIs. Written as
> durable reference for the Analytics Engineer Playbook. Claims are cited; unverified
> or contested points are marked ⚠. Researched 2026-07-18.

---

## 1. Event / telemetry schema design

### Event taxonomy: object-action naming

- Segment's canonical convention for `track` events is **Object Action** (noun + verb,
  past tense, Title Case): `Article Bookmarked`, `Game Started`, `Move Played`.
  Objects come from a curated noun list; verbs from a curated verb list ("Clicked" is
  the catch-all of last resort). [Segment Track spec](https://segment.com/docs/connections/spec/track/),
  [Segment naming conventions](https://segment.com/academy/collecting-data/naming-conventions-for-clean-data/)
- Amplitude's Data Taxonomy Playbook agrees on the substance and allows either
  `verb_noun` or `noun_verb`, but insists on **one documented convention applied
  everywhere**, past-tense verbs, and a **lean taxonomy**: tracking every low-level UI
  element is "the #1 sign of non-scalable product analytics."
  [Amplitude data planning playbook](https://amplitude.com/docs/data/data-planning-playbook),
  [Amplitude event taxonomy](https://amplitude.com/blog/event-taxonomy),
  [Lean taxonomy](https://amplitude.com/blog/data-taxonomy-analytics)
- Amplitude also caps properties per event (~20) as a design forcing function — put
  variation in **properties**, not in new event names (`Trainer Session Started
  {trainer: "traps"}`, not `Traps Trainer Started` + `Repertoire Trainer Started`).
  [Amplitude playbook](https://amplitude.com/docs/data/data-planning-playbook)
- Segment's tracking-plan best practices: start from business questions/metrics, write
  the plan **before** instrumenting, and treat the tracking plan as a living, reviewed
  document. [Segment/Twilio tracking-plan best practices](https://www.twilio.com/docs/segment/protocols/tracking-plan/best-practices)

### Envelope fields (the common core across Segment/Amplitude/Snowplow)

Every event should carry a standard envelope, separate from event-specific properties:

| Field | Purpose |
|---|---|
| `event_id` (UUID) | dedup / idempotency key at load time |
| `event_name` | object-action name |
| `occurred_at` (client ts) + `received_at` (server ts) | ordering + late-arrival analysis; Segment's common fields distinguish `timestamp`/`sentAt`/`receivedAt` |
| `session_id` | session stitching (games map naturally to sessions here) |
| `user_id` / `anonymous_id` | identity (trivial for single-user, but keep the field — it shows you know the shape) |
| `schema_version` | contract evolution |
| `app_version` | correlate behavior changes with releases |
| `properties` (JSON) | event-specific payload |

Sources: [Segment Track spec](https://segment.com/docs/connections/spec/track/) (common
fields + properties split), [Snowplow schema fundamentals](https://docs.snowplow.io/docs/fundamentals/schemas/).

### Self-describing schemas (Snowplow / Iglu)

- Snowplow events are **self-describing JSON**: the payload is wrapped with a `schema`
  URI (`iglu:vendor/name/jsonschema/1-0-0`) + `data`, so every event names the exact
  schema version that validates it. Schemas live in an **Iglu registry** ("npm/Maven
  for schemas"). [Self-describing JSONs](https://docs.snowplow.io/docs/api-reference/iglu/common-architecture/self-describing-jsons/),
  [Self-describing JSON schemas](https://docs.snowplow.io/docs/api-reference/iglu/common-architecture/self-describing-json-schemas/)
- Versioning uses **SchemaVer** `MODEL-REVISION-ADDITION`: bump MODEL for breaking
  changes, REVISION/ADDITION for compatible ones — semver semantics adapted to data.
  [SchemaVer](https://docs.snowplow.io/docs/api-reference/iglu/common-architecture/schemaver/),
  [Schema versioning](https://docs.snowplow.io/docs/fundamentals/schemas/versioning/)
- A "registry" can be as simple as a static directory of JSON Schemas in the repo —
  Snowplow themselves publish an example static registry.
  [iglu-example-schema-registry](https://github.com/snowplow/iglu-example-schema-registry)

### What app/game products typically emit

Standard coverage for a product-analytics story: **session lifecycle** (start/end),
**feature usage** (each trainer/tab opened, mode entered), **core-loop events**
(game started/move played/game ended, drill attempted/passed), and **funnels** built
from those events (e.g., trap opened → watch → practice → passed). Segment's semantic
events spec is the reference model for "standard event families."
[Segment semantic events](https://segment.com/docs/connections/spec/semantic),
[Amplitude instrumentation pre-work](https://amplitude.com/docs/get-started/instrumentation-prework)

**Bottom line for this app.** Adopt Object-Action past-tense names (`Game Started`,
`Move Played`, `Drill Completed`, `Review Opened`), a fixed envelope
(`event_id` UUID, `occurred_at`/`received_at`, `session_id`, `schema_version`,
`app_version`, JSON `properties`), and a lean catalog of ~12–20 events derived from the
KPIs you want to show — written down first as a tracking plan (`docs/tracking-plan.md`
or YAML). Version each event's payload with JSON Schema files in-repo using SchemaVer
(`events/game_started/1-0-0.json`) — a mini static Iglu. Emit to an append-only
`events` table (SQLite is fine as the producer store) or JSONL log; never mutate events.

---

## 2. Data contracts between app and warehouse

### What a data contract is

- A data contract is a **formal producer↔consumer agreement** covering: **schema**
  (names, types, nullability), **semantics/business logic** (what fields mean, valid
  ranges, enums), **SLAs** (freshness/latency of delivery), **quality rules**, and
  **ownership** (who is accountable, how changes are negotiated).
  [IBM: What is a data contract](https://www.ibm.com/think/topics/data-contract),
  [Chad Sanderson, An Engineer's Guide to Data Contracts](https://dataproducts.substack.com/p/an-engineers-guide-to-data-contracts),
  [Monte Carlo: Implementing data contracts in the warehouse](https://www.montecarlodata.com/blog-implementing-data-contracts-in-the-data-warehouse/)
- Sanderson's framing: contracts are **schema-based agreements between the software
  engineers who own producing services and the data consumers who depend on them** —
  the point is to stop treating operational databases' incidental shapes as implicit
  APIs. [Consumer-defined data contract](https://dataproducts.substack.com/p/the-consumer-defined-data-contract)

### Enforcement points (current practice)

1. **Producer-side validation** — validate events against the JSON Schema at emit
   time; reject/quarantine invalid events (Snowplow does exactly this against Iglu).
   [Snowplow schemas](https://docs.snowplow.io/docs/fundamentals/schemas/)
2. **Schema registry** — versioned schema store (Iglu, or Confluent-style for
   Kafka/Avro/Protobuf shops); at solo scale, a schemas directory in git IS the
   registry. [Iglu](https://docs.snowplow.io/docs/api-reference/iglu/common-architecture/self-describing-json-schemas/)
3. **CI checks** — schema-diff / compatibility checks on PRs that touch event schemas
   or producer code; contract changes go through code review.
   [Engineer's guide pt. 1](https://dataproducts.substack.com/p/an-engineers-guide-to-data-contracts)
4. **dbt model contracts** — `contract: {enforced: true}` makes dbt verify at build
   time that the model output matches declared column names/`data_type`s (+ platform
   `constraints`), failing the build otherwise.
   [dbt model contracts](https://docs.getdbt.com/docs/mesh/govern/model-contracts),
   [contract config](https://docs.getdbt.com/reference/resource-configs/contract)
5. **dbt model versions** — when a contracted model must change breakingly, publish
   `v2` alongside `v1` with a deprecation window, bounding migration cost for
   consumers. [dbt model versions](https://docs.getdbt.com/docs/mesh/govern/model-versions)

### The lightweight solo version that still demonstrates the concept

⚠ (synthesis, not a single citable source): the consensus practitioner pattern for
small teams is: JSON Schemas in-repo + producer-side validation + a pytest that every
emitted event validates + dbt `sources.yml` with column tests and freshness + one or
two **enforced dbt contracts on the marts you present as "public"**. That exercises
every layer of the real thing without inventing infrastructure.

**Bottom line for this app.** Write one contract per event family as a JSON Schema
(schema) + a semantics section in the tracking plan (meaning, enums, units — e.g.
"cp_loss is White-POV centipawns at matched limits") + an explicit SLA ("events land
in the warehouse within 24h; daily pipeline run") + ownership header (you, but stated).
Enforce at three points: FastAPI emit-time validation, pytest contract tests in CI, and
`enforced: true` dbt contracts on the marts. If a mart must break, cut a dbt model
version rather than editing in place — that one move signals you understand contracts
as consumer protection, not paperwork.

---

## 3. SQLite (OLTP) → warehouse staging

### Extraction pattern

- Two standard incremental patterns: **cursor-based** (query for rows where
  `updated_at`/id > last cursor; requires a suitable cursor column) vs **log-based
  CDC** (read the DB's change log; captures deletes and intermediate states, no cursor
  column needed). [Airbyte sync modes](https://docs.airbyte.com/platform/using-airbyte/core-concepts/sync-modes),
  [Incremental append](https://docs.airbyte.com/platform/using-airbyte/core-concepts/sync-modes/incremental-append),
  [Airbyte CDC](https://docs.airbyte.com/platform/understanding-airbyte/cdc)
- SQLite has no server-side replication log for standard CDC tooling; at solo scale the
  correct answer is **batch incremental cursor extraction** (append-only event tables
  make this trivial: cursor on `event_id`/rowid/`received_at`), full-refresh for tiny
  dimension tables. ⚠ Deletes won't propagate under cursor extraction — fine here
  because events are immutable; state it explicitly in the docs.
  [Airbyte append+deduped](https://docs.airbyte.com/platform/using-airbyte/core-concepts/sync-modes/incremental-append-deduped)
- **ELT framing**: land raw data first, transform inside the warehouse with dbt — this
  is the modern default and the story dbt's whole toolchain assumes.
  [dbt best-practice workflows](https://docs.getdbt.com/best-practices/best-practice-workflows)

### Layering conventions

- dbt's official structure: **staging → intermediate → marts**. Staging is 1:1 with
  source tables — rename, cast, light cleaning, **no joins/aggregations**, materialized
  as views. Intermediate isolates reusable/complex logic (regrain, pivot) and is not
  exposed to end users. Marts are business entities at a declared grain (one row = one
  game / one move / one drill attempt).
  [Guide overview](https://docs.getdbt.com/best-practices/how-we-structure/1-guide-overview),
  [Staging](https://docs.getdbt.com/best-practices/how-we-structure/2-staging),
  [Intermediate](https://docs.getdbt.com/best-practices/how-we-structure/3-intermediate),
  [Marts](https://docs.getdbt.com/best-practices/how-we-structure/4-marts)
- Medallion (bronze/silver/gold) is the lakehouse-flavored equivalent: raw ingest →
  validated/cleaned → business-facing marts. Fine to mention as a mapping
  (raw source ≈ bronze, staging/intermediate ≈ silver, marts ≈ gold); dbt-native
  vocabulary is the safer choice for an analytics-eng audience.
  [Databricks medallion docs](https://docs.databricks.com/aws/en/lakehouse/medallion)

### Idempotency, re-runnability, late data

- Loads must be **idempotent**: re-running yields the same warehouse state. Mechanics:
  dedupe on `event_id`, dbt incremental models with `unique_key` (merge semantics —
  same key updates instead of duplicating), and a lookback window on the incremental
  filter to catch late-arriving events (filter on `received_at > max - N days` rather
  than exact max). [dbt incremental models](https://docs.getdbt.com/docs/build/incremental-models),
  [Incremental models in-depth](https://docs.getdbt.com/best-practices/materializations/4-incremental-models)
- Note `unique_key` columns must never be null or the merge can generate duplicates.
  [dbt incremental config](https://docs.getdbt.com/docs/build/incremental-models)
- Client `occurred_at` vs server `received_at` is the standard late/skewed-clock
  handling: partition/filter loads on `received_at`, analyze on `occurred_at`.
  [Segment Track spec](https://segment.com/docs/connections/spec/track/)

### Reviewer red flags to avoid

- `SELECT *` in staging models instead of explicit column lists (breaks contracts and
  lineage; dbt style guidance is explicit renames/casts per column).
  [dbt staging guide](https://docs.getdbt.com/best-practices/how-we-structure/2-staging)
- No tests — every model's primary key should carry `unique` + `not_null`; sources
  should have freshness checks; incremental models need dup checks on the unique key.
  [dbt workflows](https://docs.getdbt.com/best-practices/best-practice-workflows),
  [Datacoves dbt testing guide](https://datacoves.com/post/dbt-test-options)
- Snapshots misuse: `dbt snapshot` is for capturing **slowly changing state of mutable
  sources** (SCD2), not a substitute for incremental event loading — snapshotting
  immutable events is a known smell. ⚠ ("smell" framing is practitioner consensus, not
  an official-docs quote.) [dbt materializations best practices](https://docs.getdbt.com/best-practices/materializations/4-incremental-models)
- Business logic in staging, marts with undeclared grain, joins in staging, and
  intermediate models exposed to BI are the other classic structure violations per the
  dbt guide. [dbt structure guide](https://docs.getdbt.com/best-practices/how-we-structure/1-guide-overview)

**Bottom line for this app.** ELT: a small Python extractor does cursor-based
incremental pulls from `data/games.db` + the events table into DuckDB raw tables
(cursor = rowid/`received_at`, with a lookback window; full-refresh the tiny lookup
tables), then dbt-duckdb builds `stg_` (1:1, explicit columns, views) →
`int_` (per-move enrichment, regrains) → `mart_`/`fct_`/`dim_` (fct_games, fct_moves,
fct_drill_attempts, dim_openings, KPI marts). Facts are incremental with `unique_key`
and tested for uniqueness; everything is re-runnable from zero (`--full-refresh`
documented). Explicitly document "no deletes by design; events immutable."

---

## 4. Orchestration signal for hiring managers

- **Task-based vs asset-based** is the live framing: Airflow models pipelines as task
  DAGs ("do this then that"); Dagster models them as **software-defined assets**
  (declared datasets + dependencies), giving built-in lineage, materialization history,
  and much better local testing ergonomics.
  [Dagster vs Airflow (Dagster)](https://dagster.io/blog/dagster-airflow),
  [Fivetran comparison](https://www.fivetran.com/learn/dagster-vs-airflow),
  [DataCamp comparison](https://www.datacamp.com/blog/dagster-vs-airflow)
- Airflow remains the incumbent skill keyword; Dagster is the stronger *conceptual*
  signal for analytics engineering because assets ≈ dbt models and its dbt integration
  maps each model to an asset. [Dagster vs Airflow](https://dagster.io/blog/dagster-airflow)
- ⚠ For a solo, daily-batch project, running full Airflow is widely viewed as
  over-engineering (practitioner consensus, not citable to official docs). dbt-core on
  a scheduler is a legitimate production pattern: GitHub Actions gives cron scheduling,
  secrets, run history, and failure notifications free for public repos —
  with known caveats (UTC-only cron, schedules only run on the default branch,
  ephemeral runners mean a local DuckDB file doesn't persist between runs).
  [Scheduling dbt-core with GitHub Actions](https://www.andredevries.dev/posts/schedule-dbt-github-actions),
  [dbt + GitHub Actions CI/CD guide](https://blog.pmunhoz.com/dbt/dbt-orchestration/orchestrating-dbt-with-github-actions)
- What reviewers actually look for (synthesis ⚠): dependency-aware runs (not a bash
  script of steps), retries/failure alerting, separation of extract/transform/test
  stages, CI on PRs (`dbt build` against a test target), documented scheduling, and the
  ability to explain **why** the chosen orchestrator fits the scale — the justification
  is the signal, not the logo.

**Bottom line for this app.** Best signal-to-effort: **Dagster (OSS, local) with
software-defined assets wrapping the extractor + the dbt project**, giving a real DAG
UI, lineage, and schedules to screenshot — plus GitHub Actions for CI (`dbt build` +
contract tests on every PR). If you want minimum surface instead, GitHub Actions cron
alone is defensible **if** the README states the scale reasoning and the caveats
(ephemeral runner → persist DuckDB to an artifact/MotherDuck). Avoid Airflow here:
it costs setup time and reads as resume-driven at this scale.

---

## 5. Scalability understanding without fake bigness

- **Incremental models with a stated strategy** (append vs merge, unique_key, lookback
  window, full-refresh escape hatch) are the #1 "thinks about scale" artifact — and dbt's
  own guidance is to *start simple and go incremental only when runtime warrants it*;
  saying that out loud is itself senior signal.
  [dbt incremental in-depth](https://docs.getdbt.com/best-practices/materializations/4-incremental-models)
- **Partitioning/clustering**: at DuckDB-local scale you don't need it; the right move
  is a short "at 100× scale" note per mart (what you'd partition on — `received_at`
  date — and why), not fake partitions. ⚠ (framing is practitioner consensus.)
- **Testing pyramid for data**: source tests (freshness, accepted_values) → model
  tests (`unique`, `not_null`, relationships on every PK/FK) → dbt **unit tests** for
  gnarly logic → contract enforcement on public marts. Freshness = `warn_after`/
  `error_after` in `sources.yml`, run via `dbt source freshness`.
  [Datacoves dbt testing guide](https://datacoves.com/post/dbt-test-options),
  [Testing data sources in dbt](https://dbtips.substack.com/p/testing-data-sources-in-dbt),
  [dbt workflows](https://docs.getdbt.com/best-practices/best-practice-workflows)
- **Observability**: persist run results/row counts per run, alert on failure (GH
  Actions email/issue), and surface freshness in the README or a tiny status page.
  Row-count trend checks catch silently-broken incremental filters.
  [Datacoves guide](https://datacoves.com/post/dbt-test-options)
- **Cost awareness**: DuckDB + dbt-core + GitHub Actions free tier ≈ $0; if adding a
  cloud leg, MotherDuck/BigQuery sandbox stay in free/≤$50 territory. A one-paragraph
  cost model ("this runs for $0/mo; at 1000 users it becomes X because Y") demonstrates
  the muscle better than actually paying for Snowflake. ⚠ (recommendation, not a doc
  citation.)
- **Documentation & lineage**: `dbt docs generate` + exposures for the KPI dashboard
  close the loop — reviewers click lineage first.
  [dbt structure guide](https://docs.getdbt.com/best-practices/how-we-structure/1-guide-overview)

**Bottom line for this app.** Ship: incremental facts with documented strategy and a
"when I'd go further" note; a full test layer (freshness on sources, PK tests
everywhere, 2–3 dbt unit tests on the trickiest logic like White-POV cp classification);
enforced contracts on public marts; dbt docs + exposures published (GitHub Pages);
run-metadata table + failure alerting; and a scale/cost appendix in the README instead
of any pretend-big infrastructure. That combination is exactly what "textbook
fundamentals, zero red flags" looks like at portfolio scale.

---

## Source index (primary)

Segment: [Track spec](https://segment.com/docs/connections/spec/track/) · [naming](https://segment.com/academy/collecting-data/naming-conventions-for-clean-data/) · [semantic events](https://segment.com/docs/connections/spec/semantic) · [tracking-plan best practices](https://www.twilio.com/docs/segment/protocols/tracking-plan/best-practices)
Amplitude: [data planning playbook](https://amplitude.com/docs/data/data-planning-playbook) · [event taxonomy](https://amplitude.com/blog/event-taxonomy) · [lean taxonomy](https://amplitude.com/blog/data-taxonomy-analytics)
Snowplow: [schemas](https://docs.snowplow.io/docs/fundamentals/schemas/) · [self-describing JSON](https://docs.snowplow.io/docs/api-reference/iglu/common-architecture/self-describing-jsons/) · [SchemaVer](https://docs.snowplow.io/docs/api-reference/iglu/common-architecture/schemaver/) · [static registry example](https://github.com/snowplow/iglu-example-schema-registry)
Contracts: [IBM](https://www.ibm.com/think/topics/data-contract) · [Sanderson, Engineer's Guide](https://dataproducts.substack.com/p/an-engineers-guide-to-data-contracts) · [Monte Carlo](https://www.montecarlodata.com/blog-implementing-data-contracts-in-the-data-warehouse/) · [dbt model contracts](https://docs.getdbt.com/docs/mesh/govern/model-contracts) · [dbt model versions](https://docs.getdbt.com/docs/mesh/govern/model-versions)
dbt: [structure guide](https://docs.getdbt.com/best-practices/how-we-structure/1-guide-overview) · [incremental models](https://docs.getdbt.com/docs/build/incremental-models) · [incremental in-depth](https://docs.getdbt.com/best-practices/materializations/4-incremental-models) · [workflows](https://docs.getdbt.com/best-practices/best-practice-workflows) · [testing guide (Datacoves)](https://datacoves.com/post/dbt-test-options)
Extraction: [Airbyte sync modes](https://docs.airbyte.com/platform/using-airbyte/core-concepts/sync-modes) · [CDC](https://docs.airbyte.com/platform/understanding-airbyte/cdc)
Orchestration: [Dagster vs Airflow](https://dagster.io/blog/dagster-airflow) · [Fivetran comparison](https://www.fivetran.com/learn/dagster-vs-airflow) · [dbt on GitHub Actions](https://www.andredevries.dev/posts/schedule-dbt-github-actions)
Lakehouse: [Databricks medallion](https://docs.databricks.com/aws/en/lakehouse/medallion)
