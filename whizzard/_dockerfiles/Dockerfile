# Whizzard execution cell — baseline image.
#
# A minimal Debian-based image with a non-root user. Base image pinned by
# digest per Stage 18 (D-74 / D-75-amended): a floating tag silently rolls
# the containment surface, so the digest is the integrity anchor session
# logs and `whiz image status` reference.
#
# To refresh the pin: `docker pull debian:12-slim` then read `RepoDigests`
# via `docker image inspect`. Bump the SHA below and rebuild.

FROM debian:13-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

# Install only what a generic shell session needs. Keep the image small.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        coreutils \
        curl \
        less \
        procps \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user. UID 1000 chosen so that mounted host files owned by the
# typical default macOS/Linux user UID are accessible without a chown dance.
ARG WHIZZARD_UID=1000
ARG WHIZZARD_GID=1000
RUN groupadd --gid ${WHIZZARD_GID} whizzard && \
    useradd --uid ${WHIZZARD_UID} --gid ${WHIZZARD_GID} \
            --create-home --shell /bin/bash whizzard

USER whizzard
WORKDIR /home/whizzard

# tini is included via --init at docker run time; CMD is set by the caller.
CMD ["/bin/bash"]
