import {redirect} from "next/navigation";

export default function HomePage() {
  redirect("/assessment?tier=comprehensive#assessment");
}
