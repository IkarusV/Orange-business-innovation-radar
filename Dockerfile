# Single-container build for the Cobalt Data Society Innovation Radar (Reflex
# 0.9.8) targeting Fly.io, which builds from a Dockerfile rather than going
# through Reflex Cloud's deploy API.
#
# How the frontend gets served (verified against the installed Reflex source,
# not guessed):
#
#   * `reflex run --env prod --backend-only` does NOT serve the frontend.
#     reflex/utils/exec.py:run_backend_prod() explicitly does
#     `REFLEX_MOUNT_FRONTEND_COMPILED_APP.set(mount_frontend_compiled_app)`,
#     and that argument is False for backend-only. So a backend-only process
#     serves the API and websocket but returns 404 for every page.
#
#   * `reflex run --env prod` (fullstack) DOES serve both on one port, but
#     reflex/reflex.py:_run_prod() calls `_compile_app()` and
#     `build.setup_frontend_prod()` at startup - i.e. it re-runs the Vite build
#     on every container boot, which would require the whole Node/bun toolchain
#     in the runtime image and add minutes to each cold start.
#
# So: build the frontend once at image-build time with `reflex export`, then at
# runtime start the ASGI app directly with REFLEX_MOUNT_FRONTEND_COMPILED_APP=1.
# reflex/app.py:782 appends the compiled-frontend static Mount whenever that var
# is set, independent of how the process was launched. One port, no Node at
# runtime, no rebuild on boot.

# ---------------------------------------------------------------- builder ----
FROM python:3.12 AS builder

# Baked into the compiled frontend bundle: the browser uses this to reach the
# backend (/_event websocket, /_upload, /ping). Frontend and backend are served
# from the same origin here, so it is just the public app URL.
ARG REFLEX_API_URL=https://cobalt-data-society-radar.fly.dev
ENV REFLEX_API_URL=$REFLEX_API_URL
ENV REFLEX_DEPLOY_URL=$REFLEX_API_URL
ENV REFLEX_TELEMETRY_ENABLED=false

RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

WORKDIR /app
COPY requirements-deploy.txt /app/
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY . /app

# Reflex downloads its own managed bun/Node toolchain here - no system Node
# needed. Produces the static bundle at .web/build/client.
RUN reflex export --frontend-only --no-zip --env prod

# node_modules is only needed to produce the bundle, not to serve it.
RUN rm -rf /app/.web/node_modules /app/.web/.vite

# ---------------------------------------------------------------- runtime ----
FROM python:3.12-slim

ENV PORT=8080
ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# NOTE the double-underscore prefix on the next two. Both are declared in
# reflex_base/environment.py with `internal=True`, and EnvVar.__get__ rewrites
# an internal variable's name to f"__{name}". So the variable Reflex actually
# reads from the environment is `__REFLEX_SKIP_COMPILE`, not
# `REFLEX_SKIP_COMPILE`. Setting the un-prefixed name silently does nothing.

# Serve the pre-built frontend from this same process (reflex/app.py:782).
ENV __REFLEX_MOUNT_FRONTEND_COMPILED_APP=true
# The frontend is already built and there is no Node toolchain in this image;
# without this, App.__call__ -> _compile -> compile_app tries to install
# frontend packages and dies with "Bun or npm not found".
ENV __REFLEX_SKIP_COMPILE=true
# REFLEX_ENV_MODE is a normal (non-internal) variable, so no prefix here.
ENV REFLEX_ENV_MODE=prod
ENV REFLEX_TELEMETRY_ENABLED=false
ENV REFLEX_API_URL=https://cobalt-data-society-radar.fly.dev
ENV REFLEX_DEPLOY_URL=https://cobalt-data-society-radar.fly.dev

WORKDIR /app
COPY --from=builder /app /app

RUN adduser --disabled-password --home /app --no-create-home reflex \
    && chown -R reflex:reflex /app
USER reflex

EXPOSE 8080

# Start the Reflex ASGI app directly. `app` is an rx.App instance whose
# __call__() returns the ASGI app, hence uvicorn's --factory.
#
# --proxy-headers/--forwarded-allow-ips: Fly terminates TLS and forwards plain
# HTTP, so without these the app thinks it is on http:// and StaticFiles emits
# `Location: http://...` for its trailing-slash redirects, bouncing the browser
# out to HTTP before force_https pulls it back.
CMD ["sh", "-c", "exec python -m uvicorn --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --factory radar_v2.radar_v2:app"]
