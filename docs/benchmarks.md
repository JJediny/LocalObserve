# Security Telemetry Stack Evaluation & Benchmark

This document provides a comparative evaluation of the two parallel logging pipelines currently deployed in the infrastructure: **Alloy + Loki + Grafana** vs. **OpenTelemetry (OTEL) Collector + OpenObserve**.

## 1. Architectural Overview

### Stack A: Grafana Ecosystem
*   **Collector**: Grafana Alloy
*   **Database**: Grafana Loki
*   **Visualization**: Grafana Dashboards
*   **Role**: Highly integrated, tailored for Prometheus metrics and Loki logs via LogQL.

### Stack B: OpenObserve Ecosystem
*   **Collector**: OpenTelemetry (OTEL) Collector
*   **Database & Visualization**: OpenObserve (Single Go Binary + Rust/Parquet Backend)
*   **Role**: High-throughput, low-storage-footprint analytics engine utilizing native SQL for queries.

---

## 2. Ingestion & Storage Performance (Benchmark)

Based on recent local telemetry ingestion (driven by high-frequency `osquery` and `event-generator` loads), the following performance benchmarks were observed:

| Metric | Loki (Grafana) | OpenObserve |
| :--- | :--- | :--- |
| **Ingestion Limits** | Strict (Default ~4MB/s) | Unbounded (Line-rate) |
| **Handling Spikes** | Prone to `429 Too Many Requests` | Handled seamlessly |
| **Data Format** | Inverted Index + Chunked Blocks | Apache Parquet (Columnar) |
| **Raw Data Ingested** | ~420 MB | ~421 MB |
| **Storage Footprint** | ~120 MB | **9.32 MB** (45x compression) |

**Winner: OpenObserve**
OpenObserve’s use of Apache Parquet provides industry-leading compression ratios for highly structured, repetitive JSON logs (like osquery and falco events). Loki struggled with the initial firehose and required significant tuning (`limits_config` and `chunk_target_size`) to avoid dropping data.

---

## 3. Query Language & Analytics

| Feature | Loki (LogQL) | OpenObserve (SQL) |
| :--- | :--- | :--- |
| **Syntax** | Pipe-based, regex heavy (`\|~ "regex"`) | Standard SQL (`SELECT * FROM...`) |
| **Learning Curve** | Steep for advanced parsing | Very Low (Standard SQL) |
| **JSON Extraction** | Requires `\| json` stages | Natively flattened columns |

**Winner: OpenObserve**
For security analysts hunting through Falco and Osquery logs, OpenObserve allows writing standard SQL queries (e.g., `SELECT parsed_message FROM osquery WHERE event_type = 'file_access' GROUP BY hostIdentifier`). Achieving the same in LogQL requires complex regex pipelines and unrolling JSON blobs dynamically at query time.

---

## 4. Visualization & Ecosystem

| Feature | Grafana | OpenObserve |
| :--- | :--- | :--- |
| **Dashboards** | Industry Standard, Highly Customizable | Basic, Functional, Less Flexible |
| **Alerting** | Integrated with Alertmanager | Native Alerts |
| **Plugins** | Massive ecosystem (Falco, AWS, etc.) | Limited |

**Winner: Grafana Ecosystem**
While OpenObserve provides a very fast native UI, Grafana is the undisputed industry standard for dashboarding. The ability to import community dashboards (like the Falco dashboard) and integrate with countless other data sources makes Grafana superior for "single pane of glass" visibility.

---

## 5. Falco & Osquery specific considerations

*   **High Cardinality**: Osquery and Falco generate highly dynamic JSON payloads. In Loki, extracting these fields into indexed "labels" destroys performance due to unbounded cardinality. Loki forces you to parse the JSON *at query time*, making large analytical queries slow.
*   **Columnar Advantage**: OpenObserve automatically flattens JSON fields into Parquet columns. This means high cardinality is not an issue, and querying a specific nested Falco field (like `output_fields.proc.name`) scans only that specific column, making it exponentially faster for threat hunting across large datasets.

## Conclusion & Recommendation

For **Security Information and Event Management (SIEM)** and threat hunting: **OpenObserve** is the clear winner. Its ability to ingest unthrottled JSON, compress it by 45x via Parquet, and allow analysts to query it using native SQL makes it significantly more effective for Falco/Osquery telemetry.

For **System Observability & Dashboards**: **Grafana + Loki** remains superior for visualizing metrics and providing high-level operational dashboards, but it requires careful tuning to prevent ingestion failures under heavy load.
