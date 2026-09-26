---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
Scaffold this minimal repo in the current directory: run `git init`, `git remote add origin https://github.com/acme/storefront.git`, and create these files exactly:

`package.json`:
```
{
  "name": "storefront",
  "private": true,
  "packageManager": "pnpm@9.12.0",
  "scripts": {"dev": "next dev", "build": "next build", "lint": "next lint", "typecheck": "tsc --noEmit", "test": "vitest run"},
  "dependencies": {"next": "15.0.3", "react": "19.0.0", "react-dom": "19.0.0"},
  "devDependencies": {"typescript": "5.6.3", "vitest": "2.1.4", "@types/react": "19.0.0"}
}
```

`pnpm-lock.yaml`:
```
lockfileVersion: '9.0'
```

`tsconfig.json`:
```
{ "compilerOptions": { "strict": true, "jsx": "preserve" } }
```

`.nvmrc`:
```
22
```

`app/layout.tsx`:
```
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
```

`app/page.tsx`:
```
export default function Home() {
  return <main>Storefront</main>;
}
```

`lib/price.ts`:
```
export const formatPrice = (cents: number) => `$${(cents / 100).toFixed(2)}`;
```

`lib/price.test.ts`:
```
import { expect, test } from "vitest";
import { formatPrice } from "./price";

test("formats cents", () => {
  expect(formatPrice(1999)).toBe("$19.99");
});
```

(`pnpm-lock.yaml` is abbreviated above; in the real repo the full lockfile is committed.)

Then set up CI/CD for this repo.
