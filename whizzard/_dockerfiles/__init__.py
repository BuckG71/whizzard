"""Bundled Dockerfiles, distributed as package data.

The base image (`Dockerfile`) and Hermes image (`Dockerfile.hermes`) live here
so that `pip install whizzard` includes them in the wheel and `whiz init` can
locate them at runtime via `importlib.resources.files(whizzard._dockerfiles)`.

Stage 19 (Packaging & Install) move from `docker/` at the repo root to this
in-package location. Docker build context for the Hermes image stays at the
parent of `whizzard/` so `COPY whizzard/mcp_server.py` still resolves.
"""
