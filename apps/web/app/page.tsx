import {redirect} from "next/navigation";

export default function Page() {
  redirect("/assessment?tier=comprehensive#assessment");
}
