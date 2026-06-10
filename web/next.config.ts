import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    ppr: false,
  },
  // pdfjs-dist optionally requires the 'canvas' npm package for Node.js — ignore it in browser bundle
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      canvas: false,
    };
    return config;
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
              "font-src 'self' https://cdn.jsdelivr.net",
              // cdn.jsdelivr.net needed for pdfjs worker script + KaTeX
              "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net",
              // worker-src needed because pdfjs loads its worker from CDN
              "worker-src 'self' blob: https://cdn.jsdelivr.net",
              "connect-src 'self' https://*.supabase.co",
              "img-src 'self' data: blob:",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
