// Score persistence for the demo dashboard.

export interface IScoreStorageProviderFactory {
  read(key: string): Promise<string | null>;
  write(key: string, value: string): Promise<void>;
}

export class FileStorage implements IScoreStorageProviderFactory {
  constructor(private readonly root: string) {}

  async read(key: string): Promise<string | null> {
    const fs = await import("node:fs/promises");
    try {
      return await fs.readFile(`${this.root}/${key}.json`, "utf8");
    } catch (err: unknown) {
      if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
      throw err;
    }
  }

  async write(key: string, value: string): Promise<void> {
    const fs = await import("node:fs/promises");
    await fs.writeFile(`${this.root}/${key}.json`, value, "utf8");
  }
}
