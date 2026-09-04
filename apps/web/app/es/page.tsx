import {redirect} from "next/navigation";

export default function SpanishHomePage() {
  // The specialist login uses its own fixed post-authentication destination. This
  // query marker preserves the public Comprehensive-only entrypoint contract without
  // accepting or forwarding any caller-controlled redirect target.
  redirect("/es/specialist-login?tier=comprehensive");
}
