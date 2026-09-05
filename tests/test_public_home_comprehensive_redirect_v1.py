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


def test_login_destinations_are_validated_with_locale_fallbacks() -> None:
    # Exact saved-run returns replace the former discard-all-query contract.
    # The behavioral suite exercises safe recovery and malicious targets at both
    # real component navigation seams; raw user input must never navigate.
    for path, locale in ((ENGLISH_LOGIN, "en"), (SPANISH_LOGIN, "es")):
        source = path.read_text(encoding="utf-8")
        assert 'import {specialistReturnTo}' in source
        assert f'const destination = specialistReturnTo(window.location.search, "{locale}")' in source
        assert "window.location.replace(destination)" in source
        assert f'window.location.assign(specialistReturnTo(window.location.search, "{locale}"))' in source
        assert "window.location.assign(window.location.search)" not in source
        assert "window.location.replace(window.location.search)" not in source

    validator = (ROOT / "apps/web/app/specialist-login/returnTo.ts").read_text(encoding="utf-8")
    assert 'const fallback = `${locale === "es" ? "/es" : ""}/assessment?tier=comprehensive#assessment`' in validator
    assert "return fallback" in validator


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
    assert 'login.search = ""' in source
    assert 'login.searchParams.set("returnTo", request.nextUrl.pathname + request.nextUrl.search)' in source
    assert source.index('login.search = ""') < source.index('login.searchParams.set("returnTo"')
