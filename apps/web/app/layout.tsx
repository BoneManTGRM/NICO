import type {ReactNode} from "react";
import "../styles/globals.css";
import "../styles/brand.css";
import GenericRepositoryExample from "./GenericRepositoryExample";

export const metadata = {
  title: "NICO",
  description: "Neural Intelligence Cyber Operations",
};

export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <html lang="en">
      <body>
        <GenericRepositoryExample />
        {children}
      </body>
    </html>
  );
}
