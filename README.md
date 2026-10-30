# Engine Gateway

**Engine Gateway** is a lightweight orchestration layer that makes it easy to mount, compose, and run multiple *FastAPI applications* as a distributed service for easier deployment. It dynamically loads app modules based on configuration and exposes them under configurable subpaths — enabling modular service composition, clean boundaries between components, and centralized deployment.

## Usage

### Installation

```bash
pip install dsw-engine-gateway
# or specific version
pip install dsw-engine-gateway==0.1.0
# or from repository
pip install git+https://github.com/ds-wizard/engine-gateway.git#egg=engine-gateway
```

### Configuration

Create a configuration file (e.g., `config.yaml`) to define the applications to be mounted:

```yaml
mounts:
  /example1:
    module: example_app
    app: app
  /example2:
    module: another_app.app
    factory: create_app
    kwargs:
      debug: true
```

Naturally, the `module` should be importable in your Python environment (i.e. having installed Python package exporting that module). You can specify either an `app` variable (a FastAPI instance) or a `factory` function that returns a FastAPI instance. Additional keyword arguments can be passed to the factory function via `kwargs`.

If hosting on different subpath than root, you can configure the base path of the gateway:

```yaml
gateway:
  root_path: /gateway
```

You can also configure `/info` endpoint that reports metadata about the mounted applications:

```yaml
gateway:
  info:
    enabled: true
    token: secretToken
```

(See [config.example.yaml](./config.example.yaml) for more details.)

You can also use the following environment variables to override configuration options:

- `CONFIG_FILE`: Path to the configuration file (default: `config.yaml`).
- `GATEWAY_ROOT_PATH`: Base path for the gateway (overrides `gateway.root_path`).
- `GATEWAY_INFO_ENABLED`: Enable or disable the `/info` endpoint (overrides `gateway.info.enabled`).
- `GATEWAY_INFO_TOKEN`: Token for accessing the `/info` endpoint (overrides `gateway.info.token`).
- `SENTRY_DSN`: DSN for Sentry error tracking (enables Sentry integration if set).
- `SENTRY_TRACES_SAMPLE_RATE`: Sample rate for Sentry performance tracing (default: `1.0`).
- `SENTRY_PROFILES_SAMPLE_RATE`: Sample rate for Sentry profiling (default: `1.0`).
- `SENTRY_MAX_BREADCRUMBS`: Maximum number of breadcrumbs to store in Sentry (default: `100`).
- `SENTRY_ENVIRONMENT`: Environment name for Sentry (default: `development`).
- `SENTRY_RELEASE`: Release reported to Sentry, e.g. `vX.Y.Z~<sha>` of the deployment (default: version of Engine Gateway).
- `SENTRY_COMPONENT`: Value of the `component` tag (default: `gateway`).
- `SENTRY_AWS_LAMBDA`: Enable AWS Lambda integration for Sentry (default: `false`).

### Sentry

When Sentry is enabled, events are reported in the same shape as by the FAIR Wizard backend. Every event has the `component` tag (plus any `sentry.tags`), and events from requests also have:

- `method` and `route` tags, where `route` is the template of the matched route including the root path and mount path, with UUID segments masked as `:uuid` (e.g. `/gateway/plugins/:uuid/projects/{project_uuid}`),
- `traceUuid` tag from the `X-Trace-Uuid` request header, which is also used as the Sentry trace ID (unless the request has a `sentry-trace` header),
- `tenantUuid` tag and user ID from the `tenantUuid` and `userUuid` (or `sub`) claims of the bearer JWT; the token is decoded without verification and used only for these values,
- fingerprint `[method, route, exception type]`, so errors are grouped per route.

Request data is kept in a separate scope for each request, so it does not leak between requests (or Lambda invocations).

### Development

```bash
pip install -r requirements.txt -r requirements.dev.txt -e .
pytest
```

### Usage

You can run the Engine Gateway using Uvicorn:

```bash
uvicorn engine_gateway:create_app --host
```

In typical use cases, you would use `engine_gateway` as a dependency and re-packing it together with your config files and environment setup into a Docker image for deployment:

```Dockerfile
FROM dsw-engine-gateway:latest

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY config.yaml /app/config.yaml

CMD ["uvicorn", "engine_gateway:create_app", "--host", "0.0.0.0", "--port", "80", "--proxy-headers"]
```

## License

This project is licensed under the Apache-2.0 License. See the [LICENSE](./LICENSE) file for details.
