"""M1.2: JWT według SPEC.md, „API contract” (401, `Authorization: Bearer`, /health otwarte)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from samples import PDF, PNG

from app import main as main_module
from app.auth import MSG_UNAUTHORIZED, AuthError, create_token, main, verify_token
from app.config import Settings, get_settings
from app.main import MSG_SERVER_ERROR, app

SECRET = "s" * 64  # dość dla HS256, HS384 i HS512
ON = Settings(max_file_size_mb=1, jwt_enabled=True, jwt_secret=SECRET)
UNAUTHORIZED = (401, {"detail": MSG_UNAUTHORIZED})


def use(settings: Settings) -> TestClient:
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client() -> TestClient:
    return use(ON)


@pytest.fixture(autouse=True)
def _no_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Testy JWT dotyczą wejścia do trasy, nie analizy: łańcuch M1.4 zastępuje atrapa."""
    monkeypatch.setattr(main_module, "process_file", lambda *_: {"title": "Atrapa", "tabs": [], "flow": {"links": []}})


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def post(client: TestClient, headers: dict[str, str] | None = None, data: bytes = PDF):
    files = {"file": ("wniosek.pdf", data, "application/pdf")}
    return client.post("/api/forms", files=files, headers=headers or {})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def sign(claims: dict, secret: str = SECRET, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, secret, algorithm=algorithm)


def in_hours(hours: float) -> datetime:
    return datetime.now(UTC) + timedelta(hours=hours)


def test_valid_token_returns_form(client: TestClient) -> None:
    response = post(client, bearer(create_token(ON)))
    assert response.status_code == 200, response.text


def test_scheme_is_case_insensitive(client: TestClient) -> None:
    response = post(client, {"Authorization": f"bearer {create_token(ON)}"})
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Bearer",
        "Bearer ",
        "Basic dXNlcjpwYXNz",
        "Token abc",
        "nie-jwt",
        "Bearer nie.jest.jwt",
    ],
)
def test_missing_or_malformed_header_is_401(client: TestClient, header: str | None) -> None:
    response = post(client, None if header is None else {"Authorization": header})
    assert (response.status_code, response.json()) == UNAUTHORIZED
    assert response.headers["www-authenticate"] == "Bearer"


def test_token_and_extra_words_is_401(client: TestClient) -> None:
    response = post(client, {"Authorization": f"Bearer {create_token(ON)} dodatek"})
    assert (response.status_code, response.json()) == UNAUTHORIZED


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(sign({"exp": in_hours(-1)}), id="expired"),
        pytest.param(sign({"sub": "api"}), id="no-exp"),
        pytest.param(sign({"exp": in_hours(1)}, secret="x" * 64), id="other-secret"),
        pytest.param(sign({"exp": in_hours(1)}, algorithm="HS512"), id="other-algorithm"),
        pytest.param(
            jwt.encode({"exp": in_hours(1)}, None, algorithm="none"), id="alg-none"
        ),
    ],
)
def test_bad_token_is_401(client: TestClient, token: str) -> None:
    response = post(client, bearer(token))
    assert (response.status_code, response.json()) == UNAUTHORIZED


def test_tampered_token_is_401(client: TestClient) -> None:
    header, _payload, signature = create_token(ON).split(".")
    forged = sign({"sub": "admin", "exp": in_hours(1)}, secret="y" * 64).split(".")[1]
    response = post(client, bearer(f"{header}.{forged}.{signature}"))
    assert (response.status_code, response.json()) == UNAUTHORIZED


def test_token_is_checked_before_file(client: TestClient) -> None:
    """SPEC: bez tokenu 401, nawet gdy plik jest zły (tu PNG udający PDF, inaczej 415)."""
    response = post(client, data=PNG)
    assert (response.status_code, response.json()) == UNAUTHORIZED


def test_health_is_open_with_jwt(client: TestClient) -> None:
    response = client.get("/health")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_jwt_disabled_needs_no_header() -> None:
    client = use(Settings(max_file_size_mb=1, jwt_enabled=False, jwt_secret=None))
    assert post(client).status_code == 200


@pytest.mark.parametrize(
    "settings",
    [
        pytest.param(Settings(jwt_enabled=True, jwt_secret=None), id="no-secret"),
        pytest.param(Settings(jwt_enabled=True, jwt_secret="s" * 31), id="short-secret-hs256"),
        pytest.param(
            Settings(jwt_enabled=True, jwt_secret="s" * 63, jwt_algorithm="HS512"),
            id="short-secret-hs512",
        ),
        pytest.param(
            Settings(jwt_enabled=True, jwt_secret=SECRET, jwt_algorithm="none"), id="alg-none"
        ),
        pytest.param(
            Settings(jwt_enabled=True, jwt_secret=SECRET, jwt_algorithm="RS256"), id="alg-rs256"
        ),
    ],
)
def test_bad_server_config_is_500(settings: Settings) -> None:
    token = sign({"exp": in_hours(1)})
    response = post(use(settings), bearer(token))
    assert (response.status_code, response.json()) == (500, {"detail": MSG_SERVER_ERROR})


def test_create_token_claims_and_lifetime() -> None:
    now = datetime(2026, 11, 21, 12, tzinfo=UTC)
    token = create_token(ON, hours=2, now=now)
    claims = jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_exp": False})
    assert claims == {"sub": "api", "iat": int(now.timestamp()), "exp": int(now.timestamp()) + 7200}


def test_created_token_expires() -> None:
    old = create_token(ON, hours=1, now=datetime.now(UTC) - timedelta(hours=2))
    with pytest.raises(AuthError):
        verify_token(old, ON)


def test_create_token_rejects_non_positive_hours() -> None:
    with pytest.raises(ValueError):
        create_token(ON, hours=0)


def test_script_prints_working_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("JWT_ALGORITHM", "HS384")
    assert main(["token", "--hours", "1"]) == 0
    token = capsys.readouterr().out.strip()
    assert jwt.get_unverified_header(token)["alg"] == "HS384"
    verify_token(token, Settings(jwt_enabled=True, jwt_secret=SECRET, jwt_algorithm="HS384"))


def test_script_without_secret_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    assert main(["token"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "JWT_SECRET" in captured.err
