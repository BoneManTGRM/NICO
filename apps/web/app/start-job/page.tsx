import {redirect} from "next/navigation";

export default function StartJobRedirectPage() {
  redirect("/assessment?tier=express#assessment");
}
