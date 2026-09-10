import type {ReactNode} from "react";
import FinalReviewDownloadHandoff from "./FinalReviewDownloadHandoff";

export default function FinalReviewLayout({children}: {children: ReactNode}) {
  return <>
    {children}
    <FinalReviewDownloadHandoff />
  </>;
}
