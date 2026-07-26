#!/usr/bin/env python3
import os
import subprocess
import time
import socket
import json
import shutil
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(os.path.dirname(BASE_DIR))
BIN_PATH = os.path.join(WORKSPACE_DIR, "openobserve_bin")
PORT = 25080

DOCKERFILES = {
    "alpine": """FROM alpine:latest
RUN apk add --no-cache gcompat libstdc++ libgcc zlib ca-certificates
WORKDIR /
COPY openobserve_bin /openobserve
ENTRYPOINT ["/openobserve"]
""",
    "debian-trixie-slim": """FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /
COPY openobserve_bin /openobserve
ENTRYPOINT ["/openobserve"]
""",
    "ubuntu-noble": """FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /
COPY openobserve_bin /openobserve
ENTRYPOINT ["/openobserve"]
""",
    "ubi-minimal": """FROM registry.access.redhat.com/ubi9/ubi-minimal:latest
WORKDIR /
COPY openobserve_bin /openobserve
ENTRYPOINT ["/openobserve"]
"""
}

# The official image serves as our Distroless baseline (Debian 13 trixie-based distroless)
OFFICIAL_IMAGE = "public.ecr.aws/zinclabs/openobserve@sha256:0c057ffda5a29cbf945023e4710bf38f192e61f807201a7c6611f9a8761c1756"

def check_binary():
    if not os.path.exists(BIN_PATH):
        raise FileNotFoundError(f"OpenObserve binary not found at {BIN_PATH}. Please extract it first.")
    print(f"Using OpenObserve binary: {BIN_PATH} ({os.path.getsize(BIN_PATH) / 1024 / 1024:.2f} MB)")

def run_command(cmd, cwd=None, timeout=None):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd, timeout=timeout)
    if res.returncode != 0:
        raise Exception(f"Command '{cmd}' failed (code {res.returncode}):\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
    return res.stdout.strip()

def get_image_size(image_name):
    size_str = run_command(f"podman image inspect {image_name} --format '{{{{.Size}}}}'")
    return int(size_str) / 1024 / 1024 # in MB

def wait_for_http(port, timeout=12.0):
    start_time = time.time()
    url = f"http://127.0.0.1:{port}/healthz"
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as response:
                if response.status in (200, 401, 404):
                    return time.time() - start_time
        except urllib.error.HTTPError as e:
            # If the HTTP server answers with any HTTP code, it means it is up!
            return time.time() - start_time
        except Exception:
            time.sleep(0.2)
    return -1.0

def get_process_memory(pid):
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            lines = f.readlines()
        rss = 0
        vsize = 0
        for line in lines:
            if line.startswith("VmRSS:"):
                rss = int(line.split()[1]) # in KB
            elif line.startswith("VmSize:"):
                vsize = int(line.split()[1]) # in KB
        return rss / 1024.0, vsize / 1024.0 # return in MB
    except Exception:
        return 0.0, 0.0

def get_podman_stats_memory(container_name):
    try:
        out = run_command(f"podman stats {container_name} --no-stream --format '{{{{.MemUsage}}}}'")
        # Out will be like: "12.34MB / 16.00GB" or similar
        mem_part = out.split("/")[0].strip()
        if "GB" in mem_part:
            val = float(mem_part.replace("GB", "").strip()) * 1024.0
        elif "MB" in mem_part:
            val = float(mem_part.replace("MB", "").strip())
        elif "KB" in mem_part:
            val = float(mem_part.replace("KB", "").strip()) / 1024.0
        else:
            val = float(mem_part.replace("B", "").strip()) / 1024.0 / 1024.0
        return val
    except Exception as e:
        print(f"Error reading podman stats: {e}")
        return 0.0

def run_container_benchmark(image_name, tag):
    container_name = f"oo-bench-{tag}"
    
    # Ensure no old container with same name exists
    subprocess.run(f"podman rm -f {container_name}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    cmd = (
        f"podman run -d --name {container_name} -p {PORT}:5080 "
        f"-e ZO_ROOT_USER_EMAIL=admin@example.com "
        f"-e ZO_ROOT_USER_PASSWORD=AdminPassword123 "
        f"-e ZO_DATA_DIR=/data "
        f"{image_name}"
    )
    
    print(f"Starting container {container_name}...")
    run_command(cmd)
    
    try:
        # Check if it crashes immediately
        time.sleep(1.5)
        running_str = run_command(f"podman inspect {container_name} --format '{{{{.State.Running}}}}'")
        if running_str != "true":
            logs = run_command(f"podman logs {container_name}")
            exit_code = run_command(f"podman inspect {container_name} --format '{{{{.State.ExitCode}}}}'")
            raise Exception(f"Container crashed on startup (exit code {exit_code}). Logs:\n{logs}")
            
        # Measure time to become responsive
        startup_time = wait_for_http(PORT, timeout=10.0)
        if startup_time < 0:
            logs = run_command(f"podman logs {container_name}")
            raise Exception(f"Container was running but HTTP port 5080 not responsive on localhost:{PORT}. Logs:\n{logs}")
        
        print(f"Container HTTP responsive in {startup_time * 1000:.2f} ms")
        
        # Give it a second to settle
        time.sleep(1.5)
        
        # Get memory usage
        pid_str = run_command(f"podman inspect {container_name} --format '{{{{.State.Pid}}}}'")
        pid = int(pid_str)
        
        rss, vsize = get_process_memory(pid)
        if rss == 0.0:
            rss = get_podman_stats_memory(container_name)
            vsize = rss
            
        print(f"Memory stats: RSS = {rss:.2f} MB")
        
        # Test direct execution within container
        exec_works = False
        try:
            version_out = run_command(f"podman exec {container_name} /openobserve --version")
            if "openobserve" in version_out:
                exec_works = True
        except Exception as e:
            print(f"Direct exec fails: {e}")
            
        return {
            "startup_success": True,
            "startup_time_ms": startup_time * 1000,
            "rss_mb": rss,
            "vsize_mb": vsize,
            "exec_works": exec_works
        }
        
    finally:
        print(f"Cleaning up container {container_name}...")
        subprocess.run(f"podman stop {container_name}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(f"podman rm {container_name}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def main():
    check_binary()
    
    results = {}
    
    # 1. Official Distroless Image (Baseline)
    print("\n" + "="*50)
    print("BENCHMARKING BASE IMAGE: distroless (official baseline)")
    print("="*50)
    try:
        final_size = get_image_size(OFFICIAL_IMAGE)
        print(f"Image Size: {final_size:.2f} MB")
        bench_results = run_container_benchmark(OFFICIAL_IMAGE, "distroless")
        results["distroless (official)"] = {
            "base_image": "distroless",
            "build_success": True,
            "image_size_mb": final_size,
            "build_time_sec": 0.0,
            **bench_results
        }
    except Exception as e:
        print(f"Benchmark failed for distroless (official): {e}")
        results["distroless (official)"] = {
            "base_image": "distroless",
            "build_success": False,
            "error": str(e)
        }

    # 2. Build and Test other candidates
    for tag, dockerfile_content in DOCKERFILES.items():
        print("\n" + "="*50)
        print(f"BENCHMARKING BASE IMAGE: {tag}")
        print("="*50)
        
        build_dir = os.path.join(BASE_DIR, f"build_{tag}")
        os.makedirs(build_dir, exist_ok=True)
        
        try:
            with open(os.path.join(build_dir, "Dockerfile"), "w") as f:
                f.write(dockerfile_content)
                
            shutil.copy2(BIN_PATH, os.path.join(build_dir, "openobserve_bin"))
            
            image_name = f"openobserve-bench:{tag}"
            print(f"Building image {image_name}...")
            build_time_start = time.time()
            run_command(f"podman build -t {image_name} {build_dir}")
            build_time = time.time() - build_time_start
            print(f"Built image in {build_time:.2f} seconds")
            
            final_size = get_image_size(image_name)
            print(f"Final Image Size: {final_size:.2f} MB")
            
            bench_results = run_container_benchmark(image_name, tag)
            
            results[tag] = {
                "base_image": tag,
                "build_success": True,
                "image_size_mb": final_size,
                "build_time_sec": build_time,
                **bench_results
            }
            
        except Exception as e:
            print(f"Benchmark failed for {tag}: {e}")
            results[tag] = {
                "base_image": tag,
                "build_success": False,
                "error": str(e)
            }
        finally:
            shutil.rmtree(build_dir, ignore_errors=True)
            
    # Print comparison report
    print("\n" + "="*85)
    print("BENCHMARK COMPARISON REPORT")
    print("="*85)
    
    print(f"{'Base Image':<25} | {'Size (MB)':<10} | {'Startup (ms)':<12} | {'RSS Mem (MB)':<12} | {'Direct Exec?':<12}")
    print("-" * 83)
    for tag, res in results.items():
        if res.get("build_success") and res.get("startup_success"):
            exec_works_str = "Yes" if res["exec_works"] else "No (shell restricted)"
            print(f"{tag:<25} | {res['image_size_mb']:<10.2f} | {res['startup_time_ms']:<12.2f} | {res['rss_mb']:<12.2f} | {exec_works_str:<12}")
        else:
            err_msg = res.get("error", "Build/Run failed").replace("\n", " ")
            if len(err_msg) > 40:
                err_msg = err_msg[:37] + "..."
            print(f"{tag:<25} | {'FAILED':<10} | {err_msg:<40}")

    with open(os.path.join(BASE_DIR, "results.json"), "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved results to {os.path.join(BASE_DIR, 'results.json')}")

if __name__ == "__main__":
    main()
