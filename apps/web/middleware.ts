import {NextRequest, NextResponse} from "next/server";

const SESSION_COOKIE = "nico-specialist-session";

export function middleware(request: NextRequest) {
  if (request.cookies.get(SESSION_COOKIE)?.value) return NextResponse.next();
  const login = request.nextUrl.clone();
  login.pathname = "/specialist-login";
  login.search = "";
  login.searchParams.set("next", `${request.nextUrl.pathname}${request.nextUrl.search}`);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: [
    "/assessment/:path*",
    "/es/assessment/:path*",
    "/operations/:path*",
    "/es/operations/:path*",
    "/operator/:path*",
    "/final-review/:path*",
    "/coverage-targets/:path*",
    "/setup-readiness/:path*",
    "/setup-actions/:path*",
  ],
};
