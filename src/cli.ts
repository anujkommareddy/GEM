#!/usr/bin/env bun
import { createProject, type Project } from "./types";
import { saveProject, loadProject, listProjects, ensureProjectsDir } from "./project";
import { runDevelop } from "./pipeline/develop";
import { runPlan } from "./pipeline/plan";
import { runLookDev } from "./pipeline/look-dev";
import { runPromptReview } from "./pipeline/prompt-review";
import { runGenerate } from "./pipeline/generate";
import * as ui from "./ui";

async function main() {
  ui.header("GEM — Generative Entertainment Machine");
  ui.info("Concept → Develop → Plan → Look Dev → Prompts → Generate\n");

  await ensureProjectsDir();

  // Check for required API key
  if (!process.env.ANTHROPIC_API_KEY) {
    ui.error("ANTHROPIC_API_KEY is not set. Set it in your environment or .env file.");
    process.exit(1);
  }

  const choice = await ui.choose("What do you want to do?", [
    "Start a new project",
    "Continue an existing project",
    "List all projects",
  ]);

  let project: Project;

  if (choice === 0) {
    const name = await ui.ask("Project name:");
    const concept = await ui.ask("Your concept (one sentence or paragraph):");
    project = createProject(name, concept);
    await saveProject(project);
    ui.success(`Project "${name}" created!\n`);
  } else if (choice === 1) {
    const projects = await listProjects();
    if (projects.length === 0) {
      ui.warn("No projects found. Starting a new one.\n");
      const name = await ui.ask("Project name:");
      const concept = await ui.ask("Your concept:");
      project = createProject(name, concept);
      await saveProject(project);
    } else {
      const idx = await ui.choose("Which project?", projects.map((p) => p));
      const loaded = await loadProject(projects[idx]);
      if (!loaded) {
        ui.error("Could not load project.");
        process.exit(1);
      }
      project = loaded;
      ui.success(`Loaded "${project.name}" — stage: ${ui.stageLabel(project.stage)}\n`);
    }
  } else {
    const projects = await listProjects();
    if (projects.length === 0) {
      ui.warn("No projects yet.");
    } else {
      for (const p of projects) {
        const proj = await loadProject(p);
        if (proj) {
          const totalShots = proj.scenes.reduce((s, sc) => s + sc.shots.length, 0);
          console.log(`  ${"\x1b[1m"}${proj.name}${"\x1b[0m"} — ${ui.stageLabel(proj.stage)} — ${totalShots} shots`);
          if (proj.logline) console.log(`    ${"\x1b[2m"}${proj.logline}${"\x1b[0m"}`);
        }
      }
    }
    ui.closeUI();
    return;
  }

  // Run the pipeline from the current stage
  await runPipeline(project);

  ui.closeUI();
}

async function runPipeline(project: Project): Promise<void> {
  while (true) {
    switch (project.stage) {
      case "develop":
        project = await runDevelop(project);
        if (project.stage === "develop") return; // User chose to exit
        break;

      case "plan":
        project = await runPlan(project);
        if (project.stage === "develop") continue; // User went back
        if (project.stage === "plan") return;
        break;

      case "look-dev":
        // Check for Higgsfield credentials
        if (!process.env.HF_CREDENTIALS) {
          ui.warn("\nHF_CREDENTIALS not set. You need Higgsfield API credentials for image generation.");
          ui.info("Set HF_CREDENTIALS=your_key_id:your_key_secret in your environment.\n");
          const skip = await ui.confirm("Continue anyway? (will fail on generation)");
          if (!skip) return;
        }
        project = await runLookDev(project);
        if (project.stage === "look-dev") return;
        break;

      case "prompt-review":
        project = await runPromptReview(project);
        if (project.stage === "prompt-review") return;
        break;

      case "generate":
        if (!process.env.HF_CREDENTIALS) {
          ui.error("HF_CREDENTIALS required for video generation.");
          return;
        }
        project = await runGenerate(project);
        return;

      case "complete":
        ui.header("PROJECT COMPLETE");
        ui.info(`"${project.name}" is done! Your clips are in the projects folder.`);
        return;
    }
  }
}

main().catch((e) => {
  ui.error(`\nFatal error: ${e.message}`);
  process.exit(1);
});
