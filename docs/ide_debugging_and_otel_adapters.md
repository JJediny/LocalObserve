# LocalObserve IDE Debugging, Libre Software Installers & OTEL Log Adapters Guide

This guide details the prepackaged Libre software binary toolchain for ultra-lean log monitoring, provides step-by-step setup instructions for major IDE debuggers, and documents OpenTelemetry (OTEL) log and telemetry adapters across programming languages and AI Agent frameworks.

---

## 1. Minimal Libre Software Binary Toolchain

LocalObserve provides prepackaged installation tasks for standalone Libre (FLOSS) binaries. This allows full security event collection, log tailing, and streaming detection without requiring Docker or heavyweight container daemons.

### Libre Software Package Matrix

| Component | Software Project | Version | Architecture | Installer / Task Command | Host Path |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **Falco** | Falcosecurity (CNCF) | `0.43.1` | `x86_64` | `bash scripts/install-falco-system.sh` | `/usr/bin/falco` / `~/.local/bin/falco` |
| **rsigma** | Timescale | `0.19.0` | `x86_64` | `task install-rsigma` | `./rsigma` |
| **event-generator** | Falcosecurity | `0.12.0` | `x86_64` | `task install-tools` | `./event-generator` |
| **otelcol-contrib** | OpenTelemetry | `0.125.0` | `x86_64` | `mise install` | `~/.local/share/mise/installs/otelcol-contrib` |
| **osquery** | Linux Foundation | `5.12.1` | `x86_64` | `bash setup-osqueryd.sh` | `/usr/bin/osqueryd` |

### One-Command Minimal Host Installation

To install all minimal Libre software binaries locally on the host:

```bash
# 1. Install CLI tools & binaries via Taskfile
task install-rsigma
task install-tools

# 2. Install Falco binary
bash scripts/install-falco-system.sh
```

---

## 2. IDE Debugger Integration Setup

Integrating LocalObserve with your IDE enables real-time observation of logs, spans, and security alerts directly during interactive debugging sessions.

LocalObserve exposes standard OpenTelemetry ingestion endpoints on localhost:
- **OTLP gRPC**: `http://localhost:4317`
- **OTLP HTTP/JSON**: `http://localhost:4318`
- **OpenObserve Web UI**: `http://localhost:5080` (Default: `root@example.com` / `ComplexPass#123`)

### A. Visual Studio Code (`.vscode/launch.json`)

Configure VS Code to export OTEL telemetry automatically whenever you launch a debug session:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Debug with LocalObserve OTEL",
      "type": "debugpy",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal",
      "env": {
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
        "OTEL_SERVICE_NAME": "dev-python-app",
        "OTEL_LOGS_EXPORTER": "otlp",
        "PYTHONUNBUFFERED": "1"
      }
    },
    {
      "name": "Go: Debug with LocalObserve OTEL",
      "type": "go",
      "request": "launch",
      "mode": "auto",
      "program": "${fileDirname}",
      "env": {
        "OTEL_EXPORTER_OTLP_ENDPOINT": "localhost:4317",
        "OTEL_SERVICE_NAME": "dev-go-app"
      }
    },
    {
      "name": "Node.js: Debug with LocalObserve OTEL",
      "type": "node",
      "request": "launch",
      "program": "${workspaceFolder}/src/index.ts",
      "preLaunchTask": "tsc: build",
      "env": {
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
        "OTEL_SERVICE_NAME": "dev-node-app"
      }
    }
  ]
}
```

### B. JetBrains IDEs (PyCharm / GoLand / IntelliJ / CLion)

1. Open **Run/Debug Configurations** (`Shift + Alt + F10` -> Edit Configurations).
2. Add Environment Variables:
   ```env
   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
   OTEL_SERVICE_NAME=my-local-service
   OTEL_LOG_LEVEL=debug
   ```
3. Set a breakpoint and start debugging (`Shift + F9`). Log events generated during breakpoint evaluation flow directly into OpenObserve.

---

## 3. Programming Language OTEL Log Adapters

LocalObserve ingests structured logs from any application configured with OpenTelemetry OTLP exporters.

### Python (`opentelemetry-sdk`)

```python
import logging
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

# 1. Configure OTEL Logger Provider
resource = Resource.create({"service.name": "python-agent-service"})
logger_provider = LoggerProvider(resource=resource)
set_logger_provider(logger_provider)

# 2. Attach OTLP HTTP Exporter targeting LocalObserve OTel Collector
exporter = OTLPLogExporter(endpoint="http://localhost:4318/v1/logs")
logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

# 3. Hook into Python standard logging
handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)

# 4. Emit log event
logger = logging.getLogger("app")
logger.info("LocalObserve Python OTEL Log Adapter initialized successfully.")
```

### Go (`go.opentelemetry.io/otel`)

```go
package main

import (
	"context"
	"log/slog"
	"os"

	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploggrpc"
	"go.opentelemetry.io/otel/log/global"
	sdklog "go.opentelemetry.io/otel/sdk/log"
	"go.opentelemetry.io/otel/sdk/resource"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
)

func main() {
	ctx := context.Background()

	exporter, err := otlploggrpc.New(ctx,
		otlploggrpc.WithEndpoint("localhost:4317"),
		otlploggrpc.WithInsecure(),
	)
	if err != nil {
		slog.Error("Failed to create OTLP exporter", "error", err)
		os.Exit(1)
	}

	res, _ := resource.New(ctx, resource.WithAttributes(semconv.ServiceNameKey.String("go-backend")))
	processor := sdklog.NewBatchProcessor(exporter)
	provider := sdklog.NewLoggerProvider(
		sdklog.WithResource(res),
		sdklog.WithProcessor(processor),
	)
	global.SetLoggerProvider(provider)

	slog.Info("Go OTEL Log Adapter connected to LocalObserve.")
}
```

### Node.js / TypeScript (`@opentelemetry/sdk-logs`)

```typescript
import { LoggerProvider, BatchLogRecordProcessor } from '@opentelemetry/sdk-logs';
import { OTLPLogExporter } from '@opentelemetry/exporter-logs-otlp-http';
import { Resource } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME } from '@opentelemetry/semantic-conventions';

const loggerProvider = new LoggerProvider({
  resource: new Resource({ [ATTR_SERVICE_NAME]: 'ts-agent-service' }),
});

const logExporter = new OTLPLogExporter({
  url: 'http://localhost:4318/v1/logs',
});

loggerProvider.addLogRecordProcessor(new BatchLogRecordProcessor(logExporter));
const logger = loggerProvider.getLogger('default');

logger.emit({
  body: 'TypeScript OTEL Log Adapter initialized.',
  severityText: 'INFO',
});
```

---

## 4. AI Agent & LLM Framework Telemetry

Capturing structured telemetry from autonomous AI agents, tool calls, and LLM reasoning steps is critical for debugging agentic applications.

### LangChain & LlamaIndex Callback Adapter

```python
from langchain_community.callbacks.tracers.open_telemetry import OpenTelemetryCallbackHandler
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

# Configure Tracer Provider targeting LocalObserve OTLP port
tracer_provider = TracerProvider()
span_processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces"))
tracer_provider.add_span_processor(span_processor)
trace.set_tracer_provider(tracer_provider)

# Attach LangChain OTEL Callback
handler = OpenTelemetryCallbackHandler(tracer_provider=tracer_provider)

# Usage in LangChain Agent / Chain:
# agent.invoke({"input": "Analyze process telemetry"}, config={"callbacks": [handler]})
```

### Model Context Protocol (MCP) Server Logging

MCP servers communicating via JSON-RPC over stdio or HTTP can route tool execution logs directly to LocalObserve:

```python
import json
import requests
import time

def log_mcp_tool_execution(tool_name: str, arguments: dict, duration_ms: float, status: str):
    """Emit an MCP tool execution log record to LocalObserve via OTLP HTTP."""
    payload = {
        "resourceLogs": [{
            "resource": {
                "attributes": [{"key": "service.name", "value": {"stringValue": "mcp-server-graphify"}}]
            },
            "scopeLogs": [{
                "logRecords": [{
                    "timeUnixNano": str(int(time.time() * 1e9)),
                    "severityText": "INFO" if status == "ok" else "ERROR",
                    "body": {"stringValue": f"MCP Tool Execution: {tool_name}"},
                    "attributes": [
                        {"key": "mcp.tool", "value": {"stringValue": tool_name}},
                        {"key": "mcp.duration_ms", "value": {"doubleValue": duration_ms}},
                        {"key": "mcp.status", "value": {"stringValue": status}},
                        {"key": "mcp.args", "value": {"stringValue": json.dumps(arguments)}}
                    ]
                }]
            }]
        }]
    }
    try:
        requests.post("http://localhost:4318/v1/logs", json=payload, timeout=2)
    except Exception as e:
        pass
```

---

## 5. Troubleshooting & Diagnostic Links

- 🛠️ **[Troubleshooting Guide](./troubleshooting.md)** — Diagnosing OTLP connection failures, CORS issues, and port mapping.
- 📜 **[Logs & Telemetry Guide](./logs.md)** — OTTL processor transformation rules and log stream mappings.
- 🦅 **[Falco Host Install Guide](./falco-host-install.md)** — Installing host Falco binaries without containers.
- 🌐 **[Multi-Runtime & Alerting Guide](./runtimes_alerting_and_resource_guide.md)** — Docker, Podman, and Nerdctl compose resource profiles.
- 🚀 **[Deployment Guide](./deployment.md)** — Full production hardening and deployment architecture.
