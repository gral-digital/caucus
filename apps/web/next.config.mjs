/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // La compressione bufferizza lo streaming SSE proxato (/api/v1/chat): il
  // browser riceveva l'intera risposta in un colpo solo invece dei token
  // progressivi. Gli asset statici li comprime comunque il reverse proxy
  // davanti (nginx/CDN) in produzione.
  compress: false,
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
