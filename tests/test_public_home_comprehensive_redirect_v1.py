from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGLISH_HOME = ROOT / "apps/web/app/page.tsx"
SPANISH_HOME = ROOT / "apps/web/app/es/page.tsx"
ENGLISH_LOGIN = ROOT / "apps/web/app/specialist-login/page.tsx"
SPANISH_LOGIN = ROOT / "apps/web/app/es/specialist-login/page.tsx"
MIDDLEWARE = ROOT / "apps/web/middleware.ts"


def test_english_home_redirects_to_fixed_specialist_login() -> None:
    source = ENGLISH_HOME.read_text(encoding="utf-8")

    assert 'from "next/navigation"' in source or "from 'next/navigation'" in source
    assert 'redirect("/specialist-login")' in source
    assert "next=" not in source
    assert "Express Assessment" not in source
    assert "Mid Assessment" not in source
    assert "Retainer Operations" not in source


def test_spanish_home_redirects_to_fixed_spanish_specialist_login() -> None:
    source = SPANISH_HOME.read_text(encoding="utf-8")

    assert 'from "next/navigation"' in source or "from 'next/navigation'" in source
    assert 'redirect("/es/specialist-login")' in source
    assert "next=" not in source
    assert "Express Assessment" not in source
    assert "Mid Assessment" not in source
    assert "Retainer Operations" not in source


def test_both_homes_are_server_components_not_client_redirects() -> None:
    english = ENGLISH_HOME.read_text(encoding="utf-8")
    spanish = SPANISH_HOME.read_text(encoding="utf-8")

    assert '"use client"' not in english
    assert '"use client"' not in spanish
    assert "useLayoutEffect" not in english
    assert "useLayoutEffect" not in spanish
    assert "usePathname" not in english
    assert "usePathname" not in spanish
    assert "window.location" not in english
    assert "window.location" not in spanish


def test_login_destinations_require_the_shared_local_only_validator() -> None:
    english = ENGLISH_LOGIN.read_text(encoding="utf-8")
    spanish = SPANISH_LOGIN.read_text(encoding="utf-8")

    for login, locale in ((english, "en"), (spanish, "es")):
        call = f'specialistReturnTo(window.location.search, "{locale}")'
        assert f"const destination = {call};" in login
        assert "window.location.replace(destination)" in login
        assert f"window.location.assign({call})" in login
        assert "new URLSearchParams({returnTo: destination})" in login
        assert "window.location.assign(window.location.search)" not in login
    validator = (ROOT / "apps/web/app/specialist-login/returnTo.ts").read_text(encoding="utf-8")
    assert 'getAll("returnTo")' in validator
    assert "values.length !== 1" in validator
    assert 'parsed.origin !== "https://nico.invalid"' in validator
    assert "parsed.pathname !== pathname" in validator
    assert "PROTECTED_ROOTS.some" in validator


def test_specialist_middleware_covers_english_spanish_and_operator_surfaces() -> None:
    source = MIDDLEWARE.read_text(encoding="utf-8")

    for route in (
        '"/assessment/:path*"',
        '"/es/assessment/:path*"',
        '"/operations/:path*"',
        '"/operator/:path*"',
        '"/final-review/:path*"',
    ):
        assert route in source
    assert '"nico-specialist-session"' in source
    assert '? "/es/specialist-login"' in source
    assert ': "/specialist-login"' in source
    assert 'login.search = "";' in source
    assert 'login.searchParams.set("returnTo", request.nextUrl.pathname + request.nextUrl.search)' in source
