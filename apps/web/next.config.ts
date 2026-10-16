import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  agentRules: false,
  // Documents are checked by printing to the SecurePrint printer; the old
  // upload page is gone, so send old links to the dashboard.
  async redirects() {
    return [{ source: "/analyze", destination: "/dashboard", permanent: false }];
  },
};

export default nextConfig;
