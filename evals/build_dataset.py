"""Writes evals/dataset.jsonl and checks every answer key against the docs it cites."""

import json
from pathlib import Path

Q = "question"
ITEMS = [
    # --- answerable: (question, expected pages, key facts the answer should mention) ---
    (Q, "How do I declare an optional query parameter in FastAPI?", ["tutorial/query-params.md"], ["None"]),
    (Q, "How do I add CORS support to my FastAPI app?", ["tutorial/cors.md"], ["CORSMiddleware", "allow_origins"]),
    (Q, "How can I run code when the application starts up and shuts down?", ["advanced/events.md"], ["lifespan"]),
    (Q, "How do I return status code 201 from a path operation?", ["tutorial/response-status-code.md"], ["status_code", "201"]),
    (Q, "How do I return a 404 error with a message when an item is not found?", ["tutorial/handling-errors.md"], ["HTTPException", "404"]),
    (Q, "How do I run a task after returning the response, like sending an email?", ["tutorial/background-tasks.md"], ["BackgroundTasks"]),
    (Q, "How do I receive uploaded files in an endpoint?", ["tutorial/request-files.md"], ["UploadFile", "python-multipart"]),
    (Q, "How do I receive form fields instead of JSON?", ["tutorial/request-forms.md"], ["Form", "python-multipart"]),
    (Q, "How do I declare a JSON request body?", ["tutorial/body.md"], ["Pydantic", "BaseModel"]),
    (Q, "How do I read a custom header like User-Agent in a path operation?", ["tutorial/header-params.md"], ["Header"]),
    (Q, "How do I read a cookie value in a path operation?", ["tutorial/cookie-params.md"], ["Cookie"]),
    (Q, "How do I make sure a password field is not returned in the response?", ["tutorial/response-model.md", "tutorial/extra-models.md"], ["response_model"]),
    (Q, "How do I add a maximum length validation to a query parameter?", ["tutorial/query-params-str-validations.md"], ["Query", "max_length"]),
    (Q, "How do I validate that a path parameter is greater than zero?", ["tutorial/path-params-numeric-validations.md"], ["Path", "gt"]),
    (Q, "What is dependency injection in FastAPI and how do I use Depends?", ["tutorial/dependencies/index.md"], ["Depends"]),
    (Q, "How do I create a dependency that closes a database session after the request?", ["tutorial/dependencies/dependencies-with-yield.md"], ["yield"]),
    (Q, "How do I apply a dependency to every route in the application?", ["tutorial/dependencies/global-dependencies.md"], ["dependencies"]),
    (Q, "How do I split a big FastAPI app into multiple files?", ["tutorial/bigger-applications.md"], ["APIRouter", "include_router"]),
    (Q, "How do I write tests for my FastAPI app?", ["tutorial/testing.md"], ["TestClient", "pytest"]),
    (Q, "How do I serve static files like CSS and images?", ["tutorial/static-files.md"], ["StaticFiles", "mount"]),
    (Q, "How do I write a custom HTTP middleware that adds a processing-time header?", ["tutorial/middleware.md"], ["call_next"]),
    (Q, "How do I issue and verify JWT access tokens?", ["tutorial/security/oauth2-jwt.md"], ["JWT"]),
    (Q, "How do I get the current logged-in user in a path operation?", ["tutorial/security/get-current-user.md"], ["get_current_user", "Depends"]),
    (Q, "How do I accept WebSocket connections?", ["advanced/websockets.md"], ["WebSocket"]),
    (Q, "How do I load settings from environment variables?", ["advanced/settings.md"], ["BaseSettings", "pydantic-settings"]),
    (Q, "How do I set a cookie on the response?", ["advanced/response-cookies.md"], ["Response"]),
    (Q, "How do I add custom headers to a response?", ["advanced/response-headers.md"], ["headers"]),
    (Q, "How do I return HTML instead of JSON?", ["advanced/custom-response.md"], ["HTMLResponse"]),
    (Q, "How do I render Jinja2 templates?", ["advanced/templates.md"], ["Jinja2Templates"]),
    (Q, "How do I replace a dependency with a fake one during tests?", ["advanced/testing-dependencies.md"], ["dependency_overrides"]),
    (Q, "My app runs behind a proxy that adds an /api/v1 path prefix. What do I configure?", ["advanced/behind-a-proxy.md"], ["root_path"]),
    (Q, "How do I mount a Flask application inside FastAPI?", ["advanced/wsgi.md"], ["WSGIMiddleware"]),
    (Q, "How do I build a Docker image for a FastAPI app?", ["deployment/docker.md"], ["Dockerfile"]),
    (Q, "How do I run FastAPI with multiple worker processes?", ["deployment/server-workers.md"], ["--workers"]),
    (Q, "How do I connect FastAPI to a SQL database?", ["tutorial/sql-databases.md"], ["SQLModel"]),
    (Q, "When should I use async def instead of def for a path operation?", ["async.md"], ["await"]),
    (Q, "How do I disable the OpenAPI docs in production?", ["how-to/conditional-openapi.md"], ["openapi_url"]),
    (Q, "How do I add example data to my request body schema in the docs?", ["tutorial/schema-extra-example.md"], ["examples"]),
    # --- in-domain but NOT answerable from the docs: should abstain ---
    ("unanswerable", "How do I configure FastAPI's built-in rate limiter?", [], []),
    ("unanswerable", "What is the default connection pool size of FastAPI's built-in PostgreSQL driver?", [], []),
    ("unanswerable", "Which FastAPI version added native gRPC endpoints?", [], []),
    ("unanswerable", "How do I enable FastAPI's built-in Redis caching decorator?", [], []),
    # --- off topic: should refuse ---
    ("off_topic", "What's a good recipe for chicken biryani?", [], []),
    ("off_topic", "Who won the 2011 Cricket World Cup?", [], []),
    ("off_topic", "Write me a short poem about the monsoon.", [], []),
    ("off_topic", "Can you help me file my income tax return?", [], []),
    # --- actions (two contain personal data that must be redacted) ---
    ("ticket", "The OAuth2 scopes example returns a 500 error for me, please open a ticket. My email is ravi.k@example.com", [], []),
    ("ticket", "Please file a bug report: uploading files over 1 GB crashes my server", [], []),
    ("escalate", "I need to talk to a human about our enterprise support contract", [], []),
    ("escalate", "Can someone from the support team call me at +91 98765 43210?", [], []),
]

docs = Path(__file__).resolve().parent.parent / "data/fastapi-src/docs/en/docs"
problems = 0
with open(Path(__file__).parent / "dataset.jsonl", "w") as f:
    for i, (kind, q, pages, facts) in enumerate(ITEMS, 1):
        for fact in facts:  # each key fact must appear on at least one expected page
            if docs.exists() and not any(fact.lower() in (docs / p).read_text().lower() for p in pages):
                print(f"#{i} '{fact}' not found in {pages}")
                problems += 1
        f.write(json.dumps({"id": i, "kind": kind, "question": q, "expected_pages": pages, "key_facts": facts}) + "\n")
print(f"{len(ITEMS)} items, {problems} answer-key problems")
