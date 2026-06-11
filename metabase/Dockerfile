# syntax=docker/dockerfile:1
#
# Custom Metabase image on Debian instead of Alpine.
#
# Why not metabase/metabase directly?  The upstream image is Alpine (musl
# libc), and the MotherDuck DuckDB driver's native library is glibc-built.
# `gcompat` is not enough — the JVM segfaults inside DuckDB's
# `init_have_lse_atomics` probing code the first time you try to connect.
# Temurin's Debian image gives us a real glibc, which is what DuckDB's
# native loader expects.
#
# Multi-stage: copy the upstream jar + bootstrap script verbatim, then
# layer the DuckDB driver plugin on top. Pin Metabase to the minor line
# the driver targets (0.59.x as of driver 1.5.3.0). Bump both together.

ARG METABASE_VERSION=v0.59.x
ARG DUCKDB_DRIVER_VERSION=1.5.3.0

# --- stage 1: upstream image as a tarball source ------------------------
FROM metabase/metabase:${METABASE_VERSION} AS upstream

# --- stage 2: debian runtime -------------------------------------------
FROM eclipse-temurin:21-jre-noble

# Reuse upstream's launcher script verbatim. It already handles
# root/non-root boot, H2 file shuffling, JAVA_OPTS, and the su -> metabase
# user drop. Copying the jar separately because the script resolves its
# location from /app/metabase.jar.
COPY --from=upstream /app/metabase.jar   /app/metabase.jar
COPY --from=upstream /app/run_metabase.sh /app/run_metabase.sh
COPY --from=upstream /app/certs           /app/certs

# curl: metabase healthcheck curls /api/health. ca-certificates: any HTTPS
# the driver does (MotherDuck, etc.). bash + coreutils are already in the
# base image; just need curl for the healthcheck to work.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && chmod +x /app/run_metabase.sh \
    && mkdir -p /plugins /metabase.db \
    && groupadd --system --gid 2000 metabase \
    && useradd  --system --uid 2000 --gid 2000 --home-dir /home/metabase --create-home metabase \
    && chown -R metabase:metabase /plugins /metabase.db /app

# https://github.com/motherduckdb/metabase_duckdb_driver
ARG DUCKDB_DRIVER_VERSION
ADD "https://github.com/motherduckdb/metabase_duckdb_driver/releases/download/${DUCKDB_DRIVER_VERSION}/duckdb.metabase-driver.jar" \
    /plugins/duckdb.metabase-driver.jar

# ADD-with-URL writes mode 0600 (root-only); upstream launcher drops
# privileges to UID 2000 before launching the JVM, so without this the
# plugin scanner silently skips the jar.
RUN chmod 0644 /plugins/duckdb.metabase-driver.jar

ENV MB_PLUGINS_DIR=/plugins \
    MB_DB_TYPE=h2 \
    MB_DB_FILE=/metabase.db/metabase.db

EXPOSE 3000
CMD ["/app/run_metabase.sh"]
