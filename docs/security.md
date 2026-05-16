# Security

## Scope

This repository contains local monitoring configuration, scripts, and documentation for a lightweight Linux monitoring setup.

It is currently best treated as a local evaluation and experimentation project, not a production-hardened security product.

## Reporting a security issue

If you believe you found a security issue in the repository contents, please report it privately to the project maintainer rather than opening a public issue immediately.

Until a formal project contact process exists, do not publish sensitive details, credentials, or exploit instructions directly in a public bug report.

## Good-faith expectations

When reporting an issue, include:

- what file or behavior is affected
- why you believe it is security-relevant
- how it can be reproduced
- what the practical impact is in a local deployment

## Current support boundaries

The following are important project boundaries:

- default credentials and local-only assumptions exist for ease of evaluation and should not be treated as production-safe defaults
- Falco behavior on Docker Desktop or LinuxKit-style environments is currently environment-limited
- host integration scripts may assume Linux and systemd
- the repository is optimized for low-write local monitoring rather than full enterprise hardening

## What is especially sensitive in this repository

Be careful not to expose:

- local `.env` files
- generated `.data/` contents
- host-specific credentials or tokens
- personally identifying machine details that may appear in copied logs or screenshots

The repository `.gitignore` is configured to avoid committing common generated data and local credentials, but you should still review changes carefully before publishing them.
