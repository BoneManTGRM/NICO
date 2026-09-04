import {redirect} from "next/navigation";

export default function Page() {
  redirect("/specialist-login?next=%2Fassessment%3Ftier%3Dcomprehensive%23assessment");
}
