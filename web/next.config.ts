import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

// 本番は静的書き出しにし、FastAPI が /api と一緒に出す（docs/01_design/technical_design.md §1）。
// 静的書き出しでは rewrites が使えないので、開発サーバー（next dev）のときだけ /api を手元の FastAPI に中継する。
const API_DEV_ORIGIN = "http://127.0.0.1:8101";

const turbopack: NextConfig["turbopack"] = {
  rules: {
    "*.css": {
      loaders: ["@tailwindcss/turbopack"],
      as: "*.css",
    },
  },
};

export default function config(phase: string): NextConfig {
  if (phase === PHASE_DEVELOPMENT_SERVER) {
    return {
      turbopack,
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${API_DEV_ORIGIN}/api/:path*` }];
      },
    };
  }
  return {
    output: "export",
    images: { unoptimized: true },
    turbopack,
  };
}
