#!/usr/bin/env bash
set -euo pipefail
git init -q
git remote add origin https://github.com/acme/storefront.git
cat > 'package.json' <<'EOF_0'
{
  "name": "storefront",
  "private": true,
  "packageManager": "pnpm@9.12.0",
  "scripts": {"dev": "next dev", "build": "next build", "lint": "next lint", "typecheck": "tsc --noEmit", "test": "vitest run"},
  "dependencies": {"next": "15.0.3", "react": "19.0.0", "react-dom": "19.0.0"},
  "devDependencies": {"typescript": "5.6.3", "vitest": "2.1.4", "@types/react": "19.0.0"}
}
EOF_0
# Real lockfile generated from package.json with `pnpm install --lockfile-only`.
cp "$(dirname "$0")/fixtures/pnpm-lock.yaml" pnpm-lock.yaml
cat > 'tsconfig.json' <<'EOF_2'
{ "compilerOptions": { "strict": true, "jsx": "preserve" } }
EOF_2
cat > '.nvmrc' <<'EOF_3'
22
EOF_3
mkdir -p 'app'
cat > 'app/layout.tsx' <<'EOF_4'
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
EOF_4
mkdir -p 'app'
cat > 'app/page.tsx' <<'EOF_5'
export default function Home() {
  return <main>Storefront</main>;
}
EOF_5
mkdir -p 'lib'
cat > 'lib/price.ts' <<'EOF_6'
export const formatPrice = (cents: number) => `$${(cents / 100).toFixed(2)}`;
EOF_6
mkdir -p 'lib'
cat > 'lib/price.test.ts' <<'EOF_7'
import { expect, test } from "vitest";
import { formatPrice } from "./price";

test("formats cents", () => {
  expect(formatPrice(1999)).toBe("$19.99");
});
EOF_7
