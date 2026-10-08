#!/bin/sh
set -eu
umask 077
git init --quiet --template= .
git remote add origin https://github.com/acme/storefront.git
mkdir -p app lib
cat > package.json <<'EOF'
{
  "name": "storefront",
  "private": true,
  "packageManager": "pnpm@9.12.0",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "lint": "next lint",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "next": "15.0.3",
    "react": "19.0.0",
    "react-dom": "19.0.0"
  },
  "devDependencies": {
    "typescript": "5.6.3",
    "vitest": "2.1.4",
    "@types/react": "19.0.0"
  }
}
EOF
cat > pnpm-lock.yaml <<'EOF'
lockfileVersion: '9.0'
importers:
  .:
    dependencies:
      next:
        specifier: 15.0.3
        version: 15.0.3
      react:
        specifier: 19.0.0
        version: 19.0.0
      react-dom:
        specifier: 19.0.0
        version: 19.0.0
    devDependencies:
      typescript:
        specifier: 5.6.3
        version: 5.6.3
      vitest:
        specifier: 2.1.4
        version: 2.1.4
      '@types/react':
        specifier: 19.0.0
        version: 19.0.0
EOF
cat > tsconfig.json <<'EOF'
{ "compilerOptions": { "strict": true, "jsx": "preserve" } }
EOF
cat > .nvmrc <<'EOF'
22
EOF
cat > app/layout.tsx <<'EOF'
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
EOF
cat > app/page.tsx <<'EOF'
export default function Home() {
  return <main>Storefront</main>;
}
EOF
cat > lib/price.ts <<'EOF'
export const formatPrice = (cents: number) => `$${(cents / 100).toFixed(2)}`;
EOF
cat > lib/price.test.ts <<'EOF'
import { expect, test } from "vitest";
import { formatPrice } from "./price";

test("formats cents", () => {
  expect(formatPrice(1999)).toBe("$19.99");
});
EOF
