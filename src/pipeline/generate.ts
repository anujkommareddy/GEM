import type { Project } from "../types";
import { saveProject, getOutputDir } from "../project";
import { generateVideo, downloadFile } from "../models/higgsfield";
import * as ui from "../ui";
import { join } from "path";
import { mkdir } from "fs/promises";
import { existsSync } from "fs";

export async function runGenerate(project: Project): Promise<Project> {
  ui.header("STAGE 5: VIDEO GENERATION");

  const readyShots = project.scenes.flatMap((scene) =>
    scene.shots
      .filter((shot) => shot.imageStatus === "approved" && shot.videoPrompt && shot.videoStatus !== "done")
      .map((shot) => ({ shot, scene }))
  );

  const doneShots = project.scenes.flatMap((scene) =>
    scene.shots.filter((shot) => shot.videoStatus === "done")
  );

  if (readyShots.length === 0 && doneShots.length > 0) {
    ui.success("All videos have been generated!");
    displaySummary(project);
    project.stage = "complete";
    await saveProject(project);
    return project;
  }

  if (readyShots.length === 0) {
    ui.warn("No shots ready for generation. Go back to look development or prompt review.");
    return project;
  }

  console.log(`  Ready to generate: ${readyShots.length} clips`);
  console.log(`  Already done: ${doneShots.length} clips\n`);

  // Cost estimate
  console.log(`  ${"\x1b[1m"}This will make ${readyShots.length} API calls to Higgsfield.${"\x1b[0m"}`);

  if (!(await ui.confirm("Start generating?"))) {
    return project;
  }

  let completed = 0;
  let failed = 0;

  for (let i = 0; i < readyShots.length; i++) {
    const { shot, scene } = readyShots[i];

    console.log(`\n  [${i + 1}/${readyShots.length}] Generating ${shot.id}...`);
    console.log(`    Prompt: ${shot.videoPrompt!.substring(0, 80)}...`);

    shot.videoStatus = "generating";
    await saveProject(project);

    try {
      if (!shot.imageUrl) {
        throw new Error("No starting image URL for this shot");
      }

      const result = await generateVideo(
        shot.videoPrompt!,
        shot.imageUrl,
        shot.duration
      );

      if (result.url) {
        // Download the video
        const outDir = join(getOutputDir(project), scene.id);
        if (!existsSync(outDir)) await mkdir(outDir, { recursive: true });
        const videoPath = join(outDir, `${shot.id}.mp4`);
        await downloadFile(result.url, videoPath);

        shot.videoUrl = result.url;
        shot.outputPath = videoPath;
        shot.videoStatus = "done";
        completed++;
        await saveProject(project);

        ui.success(`    Done! Saved: ${videoPath}`);
      }
    } catch (e: any) {
      ui.error(`    Failed: ${e.message}`);
      shot.videoStatus = "failed";
      failed++;
      await saveProject(project);
    }
  }

  // Summary
  console.log(`\n${"=".repeat(60)}`);
  console.log(`  Generation complete: ${completed} succeeded, ${failed} failed`);

  if (failed > 0) {
    const retry = await ui.confirm("Retry failed shots?");
    if (retry) {
      return runGenerate(project);
    }
  }

  if (failed === 0) {
    project.stage = "complete";
    await saveProject(project);
  }

  displaySummary(project);
  return project;
}

function displaySummary(project: Project): void {
  ui.header("PROJECT COMPLETE");

  console.log(`  ${"\x1b[1m"}${project.name}${"\x1b[0m"}`);
  if (project.logline) console.log(`  ${project.logline}\n`);

  const outDir = getOutputDir(project);
  console.log(`  Output directory: ${outDir}\n`);

  console.log(`  ${"─".repeat(50)}`);

  for (const scene of project.scenes) {
    console.log(`\n  ${"\x1b[1m"}${scene.title}${"\x1b[0m"}`);
    for (const shot of scene.shots) {
      const status = shot.videoStatus === "done" ? "\x1b[32m done \x1b[0m" :
                     shot.videoStatus === "failed" ? "\x1b[31mfailed\x1b[0m" :
                     "\x1b[33m  --  \x1b[0m";
      console.log(`    [${status}] ${shot.id} — ${shot.description.substring(0, 60)}`);
      if (shot.outputPath) console.log(`           ${"\x1b[2m"}${shot.outputPath}${"\x1b[0m"}`);
    }
  }

  console.log(`\n  ${"─".repeat(50)}`);
  console.log(`  Your raw footage is ready for editing!`);
}
