/** @type {import('next').NextConfig} */
const nextConfig = {
  // NICO does not use next/image. Disable the native optimizer so the optional
  // Sharp integration is never invoked at runtime; the lock still pins a patched
  // Sharp release to keep production dependency evidence clean.
  images: {
    unoptimized: true,
  },
};

module.exports = nextConfig;
