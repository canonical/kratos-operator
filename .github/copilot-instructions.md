# GitHub Copilot Instructions for Kratos Operator

## 1. Governance & Constraints
You **MUST NOT** modify the following critical configuration files without explicit user validation:
- `charmcraft.yaml`
- `renovate.json`
- `SECURITY.md`
- `.github/workflows/**`
- `lib/**` (Vendorized libraries)

## 2. Architecture: The 3-Layer Pattern
This charm follows the **Canonical Identity Team Pattern**, a three-layer architecture (Orchestration → Abstraction → Infrastructure) where dependencies flow **downwards** only.

### Layer 1: Orchestration (`src/charm.py`)
- **Responsibility**: Handle Juju events, maintain Unit Status, decide *what* to do.
- **Data Flow**: Coordinates data from **Sources** (Config, Integrations, Secrets) to **Sinks** (Pebble, Relation Databags).
- **Prohibited**: Complex business logic, direct `lightkube` usage, direct `pebble` calls.

### Layer 2: Abstraction (Helper Modules)
- **`src/services.py`**: Encapsulates workload operations (Pebble plans, file interactions).
- **`src/integrations.py`**: Strongly-typed wrappers around Juju relations (using Pydantic).
- **`src/configs.py`**: Validates charm configuration.
- **`src/clients.py`**: Application-specific API clients (HTTP calls).

### Layer 3: Infrastructure (`ops`, `lightkube`)
- Low-level framework interaction. **Layer 1 must NEVER import `lightkube` directly**; it must use a Service/Client wrapper.

## 3. Developer Workflows

### Standard Commands (`tox`)
- `tox -e fmt`: **Run this first.** Applies standard formatting (ruff, isort).
- `tox -e lint`: Checks compliance (mypy, codespell).
- `tox -e unit`: Runs Unit tests.
- `tox -e integration`: Runs Integration tests.

## 4. Testing Strategy
**CRITICAL**: Distinguish between **Charm State Tests** and **Component Tests**.

### A. Charm State Tests (`tests/unit/test_charm.py`)
- **Goal**: Test orchestration logic and event handling.
- **Framework**: **`ops.testing`** (Context + State).
- **Pattern**:
  1. **Arrange**: Define input `State` (Relations, Config, Containers).
  2. **Act**: `context.run(event, state)`.
  3. **Assert**: Check output `State` (Status, Relation Data).
- **Anti-Pattern**: Do NOT use `unittest.mock` to mock `ops` internals here. Use `State`.

### B. Component Tests (`tests/unit/test_services.py`)
- **Goal**: Test isolated business logic in `services.py` or `utils.py`.
- **Framework**: `pytest` + `unittest.mock`.
- **Pattern**: Mock external dependencies (like `ops.model.Container`) and assert method calls.

### C. Integration Tests (`tests/integration`)
- **Framework**: **`jubilant`**.
- **Goal**: Test real deployment, integration, and side-effects on a real K8s cluster.

## 5. Coding Standards & Typing

### Python 3.12 Modern Syntax
- **MANDATORY**: Use modern union syntax `str | None` instead of `Optional[str]`.
- **MANDATORY**: Use built-in generics `list[str]`, `dict[str, Any]` instead of `typing.List`.
- **Prohibited**: `from typing import List, Dict, Optional, Union`.

### Error Handling
- **EAFP**: "Easier to Ask Forgiveness than Permission".
- **Status**:
  - `BlockedStatus`: Missing/Invalid Config or Relations (Human fix needed).
  - `WaitingStatus`: Dependency not ready (Automatic recovery expected).
  - `MaintenanceStatus`: Transient operation in progress.
  - `ActiveStatus`: Workload is running and healthy.

## 6. Juju Specifics
- **Pebble Checks**: Always check `if not container.can_connect():` before accessing workload.
- **Deferral**: Usage of `event.defer()` is allowed but should be minimized; prefer handling state changes idempotently.
