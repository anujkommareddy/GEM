import { readFile, writeFile, mkdir } from "fs/promises";
import { existsSync } from "fs";
import { join } from "path";
import type { Project } from "./types";

const PROJECTS_DIR = join(process.cwd(), "projects");

export async function ensureProjectsDir(): Promise<void> {
  if (!existsSync(PROJECTS_DIR)) {
    await mkdir(PROJECTS_DIR, { recursive: true });
  }
}

function projectPath(name: string): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return join(PROJECTS_DIR, slug, "project.json");
}

function projectDir(name: string): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return join(PROJECTS_DIR, slug);
}

export async function saveProject(project: Project): Promise<void> {
  const dir = projectDir(project.name);
  if (!existsSync(dir)) {
    await mkdir(dir, { recursive: true });
  }
  project.updatedAt = new Date().toISOString();
  await writeFile(projectPath(project.name), JSON.stringify(project, null, 2));
}

export async function loadProject(name: string): Promise<Project | null> {
  const path = projectPath(name);
  if (!existsSync(path)) return null;
  const data = await readFile(path, "utf-8");
  return JSON.parse(data) as Project;
}

export async function listProjects(): Promise<string[]> {
  await ensureProjectsDir();
  const { readdir } = await import("fs/promises");
  const entries = await readdir(PROJECTS_DIR, { withFileTypes: true });
  const projects: string[] = [];
  for (const entry of entries) {
    if (entry.isDirectory()) {
      const pPath = join(PROJECTS_DIR, entry.name, "project.json");
      if (existsSync(pPath)) {
        const data = JSON.parse(await readFile(pPath, "utf-8"));
        projects.push(data.name);
      }
    }
  }
  return projects;
}

export function getOutputDir(project: Project): string {
  return join(projectDir(project.name), "output");
}
