import type { NextConfig } from "next";

const apiUrl = process.env.INTERNAL_API_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "image.api.playstation.com",
      },
      {
        protocol: "https",
        hostname: "**.playstation.com",
      },
    ],
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
      {
        source: "/healthz",
        destination: `${apiUrl}/healthz`,
      },
    ];
  },
};

export default nextConfig;
