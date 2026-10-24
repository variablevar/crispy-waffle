/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_INTERNAL_URL || 'http://localhost:8000';

const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${backend}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
