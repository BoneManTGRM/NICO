import {OperationsControlCenter} from "./operations-control-center";

export default function OperationsPage() {
  return <><nav aria-label="Operator tools"><a href="/operations/provider-intake">GitHub operator intake</a>{" · "}<a href="/operations/scanner-evidence">Retained scanner evidence</a></nav><OperationsControlCenter /></>;
}
