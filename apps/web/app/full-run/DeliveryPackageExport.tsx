"use client";

import {useState} from "react";

type Props = {
  apiUrl: string;
  runId: string;
  customerId: string;
  projectId: string;
  adminToken: string;
  disabled?: boolean;
};

type PackageIntegrity = {
  package_sha256: string;
  manifest_sha256: string;
  package_identity_sha256: string;
  package_version: string;
  file_count: number;
  filename: string;
};

function filenameFromDisposition(value: string | null): string {
  const match = String(value || "").match(/filename="?([^";]+)"?/i);
  return match?.[1] || "nico-approved-delivery-package.zip";
}

function saveZip(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function DeliveryPackageExport({apiUrl, runId, customerId, projectId, adminToken, disabled = false}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [integrity, setIntegrity] = useState<PackageIntegrity | null>(null);

  async function downloadPackage() {
    if (!apiUrl || !runId || !adminToken.trim() || loading || disabled) return;
    setError("");
    setIntegrity(null);
    setLoading(true);
    try {
      const params = new URLSearchParams({customer_id: customerId, project_id: projectId});
      const response = await fetch(`${apiUrl}/assessment/full-run/${encodeURIComponent(runId)}/approved-delivery/package?${params.toString()}`, {
        headers: {"X-NICO-Admin-Token": adminToken},
        cache: "no-store",
      });
      if (!response.ok) {
        let message = `Delivery package export failed with ${response.status}.`;
        try {
          const data = await response.json() as {detail?: {message?: string}};
          message = data.detail?.message || message;
        } catch {
          // Keep the safe generic message.
        }
        throw new Error(message);
      }
      const packageIntegrity: PackageIntegrity = {
        package_sha256: response.headers.get("X-NICO-Package-SHA256") || "",
        manifest_sha256: response.headers.get("X-NICO-Manifest-SHA256") || "",
        package_identity_sha256: response.headers.get("X-NICO-Package-Identity-SHA256") || "",
        package_version: response.headers.get("X-NICO-Package-Version") || "",
        file_count: Number(response.headers.get("X-NICO-Package-File-Count") || 0),
        filename: filenameFromDisposition(response.headers.get("Content-Disposition")),
      };
      if (!packageIntegrity.package_sha256 || !packageIntegrity.manifest_sha256 || !packageIntegrity.package_identity_sha256 || packageIntegrity.file_count < 1) {
        throw new Error("The delivery package response did not include complete integrity metadata.");
      }
      const blob = await response.blob();
      if (!blob.size) throw new Error("The delivery package response was empty.");
      saveZip(blob, packageIntegrity.filename);
      setIntegrity(packageIntegrity);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delivery package export failed.");
    } finally {
      setLoading(false);
    }
  }

  return <div className="mini-panel">
    <div className="section-head">
      <div><p className="eyebrow">Auditable package</p><h2>Export complete client-delivery record</h2></div>
      <span className={integrity ? "status green" : error ? "status red" : "status gray"}>{integrity ? "exported" : error ? "blocked" : "not exported"}</span>
    </div>
    <p className="muted">Exports the verified approved PDF, human approval metadata, access-grant ledger, delivery receipts, receipt-only acknowledgments, storage readiness, disclosures, and SHA-256 manifest. Raw access tokens are never included.</p>
    <div className="report-actions">
      <button type="button" className="primary-button" disabled={disabled || loading || !apiUrl || !runId || !adminToken.trim()} onClick={downloadPackage}>{loading ? "Building verified package..." : "Download delivery package ZIP"}</button>
    </div>
    {error ? <p className="error-box">{error}</p> : null}
    {integrity ? <details className="help-details" open><summary>Package integrity</summary><pre className="json-block">{JSON.stringify(integrity, null, 2)}</pre></details> : null}
  </div>;
}
