# Ollama + OpenObserve Integration

This document outlines how to connect your local Ollama instance to OpenObserve for AI-powered log analysis and natural language querying.

## 1. Configure Ollama to allow Docker access
By default, Ollama only listens on `127.0.0.1`. Since OpenObserve is running in a Docker container, we need to tell Ollama to listen on all interfaces.

### On Linux (Systemd):
1. Run: `sudo systemctl edit ollama.service`
2. Add these lines:
   ```ini
   [Service]
   Environment="OLLAMA_HOST=0.0.0.0"
   Environment="OLLAMA_ORIGINS=*"
   ```
3. Restart Ollama:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart ollama
   ```

## 2. Docker Networking
We have configured `docker-compose.yaml` with an `extra_hosts` entry so that the OpenObserve container can reach your host machine via the hostname `host.docker.internal`.

## 3. Configure AI Provider in OpenObserve UI
Once Ollama is restarted and the stack is up:
1. Log in to OpenObserve (http://localhost:5080).
2. Go to **Settings** > **AI Providers**.
3. Add a new provider:
   - **Name**: `Ollama`
   - **Type**: `Ollama`
   - **Endpoint**: `http://host.docker.internal:11434`
   - **Model**: `llama3.2` (or your preferred pulled model)
4. Click **Save**.

## 4. Verify
You can now use the **AI Assistant** tab in OpenObserve to ask questions about your logs or metrics using your local GPU-powered RTX 3090 via Ollama.
