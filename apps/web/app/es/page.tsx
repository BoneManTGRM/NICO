import {redirect} from "next/navigation";

export default function SpanishHomePage() {
  redirect("/es/assessment?tier=comprehensive#assessment");
}
