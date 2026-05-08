# Airlock/Warlock execution cell — Stage 1 baseline image
#
# A minimal Debian-based image with a non-root user. Stage 9 will pin the
# base image by digest. For Stage 1 we use a tag and the build will be
# reproducible enough for verifying contained execution.

FROM debian:12-slim

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
ARG WARLOCK_UID=1000
ARG WARLOCK_GID=1000
RUN groupadd --gid ${WARLOCK_GID} warlock && \
    useradd --uid ${WARLOCK_UID} --gid ${WARLOCK_GID} \
            --create-home --shell /bin/bash warlock

USER warlock
WORKDIR /home/warlock

# tini is included via --init at docker run time; CMD is set by the caller.
CMD ["/bin/bash"]
