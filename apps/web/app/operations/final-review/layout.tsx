import type {ReactNode} from "react";
import FinalReviewApprovedReportHydration from "./FinalReviewApprovedReportHydration";
import FinalReviewDownloadHandoff from "./FinalReviewDownloadHandoff";

export default function FinalReviewLayout({children}: {children: ReactNode}) {
  return <>
    <FinalReviewApprovedReportHydration />
    {children}
    <FinalReviewDownloadHandoff />
  </>;
}
