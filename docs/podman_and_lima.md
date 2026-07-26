# Podman and Lima Container Runtime Support

This guide provides instructions for deploying, running, and troubleshooting the security observability stack using alternative container runtimes: **Podman** (rootless/rootful) and **Lima** (Linux Virtual Machines on macOS/Linux).

---

## 1. Running with Podman

Podman is a daemonless, rootless-friendly container engine that acts as a drop-in replacement for Docker. Running the stack with Podman avoids central daemon bottlenecks and eliminates Docker daemon permission issues (such as AppArmor signal-blocking).

### Podman Compose Compatibility
You can run the stack using either `podman-compose` or Podman's native support for Docker Compose files via the Podman socket:

```bash
# Using podman-compose directly
podman-compose up -d

# Or using standard docker compose mapped to the Podman socket
export DOCKER_HOST=unix:///run/user/$(id -u)/podman/podman.sock
docker compose up -d
```

### Security Configuration for Rootless Podman
Because rootless Podman maps container root (UID 0) to your host user (UID 1000), some kernel-level components require specific permissions:

1. **Falco (Syscall Monitoring):**
   Falco requires raw syscall inspection via the eBPF probe or kernel module. 
   - **Rootless limitation:** Rootless Podman cannot load kernel modules or read raw tracepoints.
   - **Recommendation:** Run Falco as a **rootful** Podman container (`sudo podman run ...`) or run it on the host directly, while keeping the rest of the stack (OpenObserve, OTEL Collector) rootless under Podman.
   
2. **OSquery and OTEL Collector File Access:**
   Ensure Podman has read access to the host log paths (e.g., `/var/log/osquery/`).
   - If log files are owned by root with `600` permissions, rootless Podman will not be able to read them.
   - Adjust permissions or run `podman` with the host user added to the appropriate log group:
     ```bash
     sudo usermod -aG osquery $USER
     ```

---

## 2. Running with Nerdctl (Containerd)

Nerdctl is a Docker-compatible CLI for containerd that supports Docker Compose out of the box, including advanced security profiles and rootless operation.

### Running with Nerdctl Compose
You can deploy the stack natively using nerdctl's compose engine:

```bash
nerdctl compose up -d
```

### Security Configuration for Rootless containerd / Nerdctl
Similar to rootless Podman, running nerdctl in rootless mode restricts kernel capability access:
1. **eBPF Syscall Monitoring (Falco):**
   Falco cannot load kernel probes inside rootless containerd namespaces.
   - **Recommendation:** Run the `falco` container using `sudo nerdctl run ...` (rootful mode) to ensure eBPF probes can bind to kernel ring buffers.
2. **Accessing Host Logs:**
   Ensure your rootless containerd daemon namespace has read access to the osquery and system log files (e.g. `/var/log/osquery/`).

---

## 3. Running with Lima (Linux Machines)

Lima (Linux Machines) provides automatic file sharing, port forwarding, and container runtime integration for macOS and Linux. It is the recommended approach for running this stack on macOS hosts.

### Step 1: Initialize a Lima VM
You can start a Lima virtual machine pre-configured with Docker or Podman:

```bash
# Start a VM using the docker template
limactl start --name=localobserve template://docker

# Or start a VM using the podman template
limactl start --name=localobserve template://podman
```

### Step 2: Configure Shell Environment
Configure your local shell to point to the Lima VM's container engine:

```bash
# Set up Docker CLI wrapper for Lima
export DOCKER_HOST=$(limactl show-ports localobserve --format 'unix://{{.LocalUnixSocket}}')

# Verify the connection
docker ps
```

### Step 3: Run the Stack
Run the compose files from your host. Lima automatically handles mounting the repository directory into the VM and forwarding ports (such as OpenObserve on `5080`) back to your host's localhost:

```bash
docker compose up -d
```

---

## 3. Troubleshooting & Conflict Resolution

### Conflict 1: Port Already in Use (e.g. Geonode)
If you have legacy services like **Geonode** (Geoserver on `8080`, Nginx on `80/443`, Postgres on `5432`) running, they can conflict with ports or consume system resources.

#### To Turn Off Geonode:
If Geonode was started via Docker, run the following to stop it:
```bash
# Stop all Geonode containers
docker stop geoserver4geonode celery4geonode django4geonode nginx4geonode rabbitmq4geonode db4geonode gsconf4geonode memcached4geonode letsencrypt4geonode

# Force remove them if necessary
docker rm -f geoserver4geonode celery4geonode django4geonode nginx4geonode rabbitmq4geonode db4geonode gsconf4geonode memcached4geonode letsencrypt4geonode
```

### Conflict 2: Docker Daemon "Permission Denied" (AppArmor Locks)
If you run `docker stop` or `docker kill` and receive:
`Error response from daemon: cannot stop container: <name>: permission denied`

This is a known issue on Ubuntu/Debian where AppArmor profiles get out of sync with Docker.

#### Solutions:
1. **Bypass with Podman (Recommended):**
   Since Podman runs rootless and daemonless, it does not rely on the system Docker AppArmor profile. You can build, run, and stop containers without hitting this block.
   
2. **Reload AppArmor Profiles (Requires Sudo):**
   If you have administrative access, remove the conflicting AppArmor profiles and restart Docker:
   ```bash
   sudo aa-remove-unknown
   sudo systemctl daemon-reload
   sudo systemctl restart docker
   ```
