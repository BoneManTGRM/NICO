import {redirect} from "next/navigation";

export default function SpanishHomePage() {
  redirect("/specialist-login?next=%2Fes%2Fassessment%3Ftier%3Dcomprehensive%23assessment");
}
