import Anthropic from "@anthropic-ai/sdk";
import type { Project } from "../types";
import { saveProject, getOutputDir } from "../project";
import { generateImage, downloadFile } from "../models/higgsfield";
import * as ui from "../ui";
import { join } from "path";
import { mkdir } from "fs/promises";
import { existsSync } from "fs";

const client = new Anthropic();

export async function runLookDev(project: Project): Promise<Project> {
  ui.header("STAGE 3: LOOK DEVELOPMENT");
  ui.info("Generating a starting image for each shot.");
  ui.info("You'll approve each image before we move to video prompts.\n");

  const totalShots = project.scenes.reduce((sum, s) => sum + s.shots.length, 0);
  let shotNum = 0;

  for (let si = 0; si < project.scenes.length; si++) {
    const scene = project.scenes[si];
    ui.subheader(`SCENE ${si + 1}: ${scene.title}`);

    for (let shi = 0; shi < scene.shots.length; shi++) {
      const shot = scene.shots[shi];
      shotNum++;

      if (shot.imageStatus === "approved") {
        ui.success(`  Shot ${shotNum}/${totalShots} [${shot.id}] — already approved`);
        continue;
      }

      console.log(`\n  Shot ${shotNum}/${totalShots}`);
      ui.displayShot(si, shi, shot);

      // Generate image prompt if not already set
      if (!shot.imagePrompt) {
        shot.imagePrompt = await generateImagePrompt(shot, project);
        await saveProject(project);
      }

      // Show the prompt
      console.log(`\n    ${"\x1b[1m"}Image Prompt:${"\x1b[0m"} ${shot.imagePrompt}\n`);

      // Approval loop for this shot
      while (shot.imageStatus !== "approved") {
        const choice = await ui.choose(`Shot ${shotNum}/${totalShots} — what do you want to do?`, [
          "Generate this image",
          "Edit the image prompt first",
          "Skip this shot for now",
        ]);

        if (choice === 0) {
          // Generate
          ui.info("  Generating image...");
          try {
            const result = await generateImage(shot.imagePrompt!);
            if (result.url) {
              // Download the image
              const outDir = join(getOutputDir(project), scene.id);
              if (!existsSync(outDir)) await mkdir(outDir, { recursive: true });
              const imgPath = join(outDir, `${shot.id}.png`);
              await downloadFile(result.url, imgPath);
              shot.imageUrl = result.url;
              shot.outputPath = imgPath;
              shot.imageStatus = "generating";
              await saveProject(project);

              ui.success(`  Image saved: ${imgPath}`);
              console.log(`  URL: ${result.url}\n`);

              const approved = await ui.choose("Do you approve this image?", [
                "Approve — this is the look I want",
                "Reject — regenerate with same prompt",
                "Reject — edit prompt and regenerate",
              ]);

              if (approved === 0) {
                shot.imageStatus = "approved";
                await saveProject(project);
                ui.success("  Approved!");
              } else if (approved === 2) {
                const newPrompt = await ui.ask("  New prompt:");
                shot.imagePrompt = newPrompt;
                shot.imageStatus = "rejected";
                await saveProject(project);
              } else {
                shot.imageStatus = "rejected";
                await saveProject(project);
              }
            }
          } catch (e: any) {
            ui.error(`  Generation failed: ${e.message}`);
            shot.imageStatus = "failed";
            await saveProject(project);
          }
        } else if (choice === 1) {
          // Edit prompt
          console.log(`  Current: ${shot.imagePrompt}`);
          const newPrompt = await ui.ask("  New prompt:");
          shot.imagePrompt = newPrompt;
          await saveProject(project);
          console.log(`  Updated!\n`);
        } else {
          // Skip
          ui.warn("  Skipped for now.");
          break;
        }
      }
    }
  }

  // Check if all shots are approved
  const allApproved = project.scenes.every((s) =>
    s.shots.every((shot) => shot.imageStatus === "approved")
  );

  if (allApproved) {
    ui.success("\nAll shots approved!");
    const advance = await ui.confirm("Move to prompt review?");
    if (advance) {
      project.stage = "prompt-review";
      await saveProject(project);
    }
  } else {
    const unapproved = project.scenes.reduce(
      (sum, s) => sum + s.shots.filter((shot) => shot.imageStatus !== "approved").length,
      0
    );
    ui.warn(`\n${unapproved} shot(s) still need approval.`);
    const choice = await ui.choose("What do you want to do?", [
      "Continue approving remaining shots",
      "Move to prompt review anyway (unapproved shots will be skipped)",
      "Save and exit",
    ]);

    if (choice === 0) {
      return runLookDev(project);
    } else if (choice === 1) {
      project.stage = "prompt-review";
      await saveProject(project);
    }
  }

  return project;
}

async function generateImagePrompt(
  shot: { visual: string; camera: string; mood: string; description: string },
  project: Project
): Promise<string> {
  const response = await client.messages.create({
    model: "claude-sonnet-4-20250514",
    max_tokens: 500,
    system: `You generate concise, specific image generation prompts for AI image models like Flux.
Focus on visual details: subject, setting, lighting, composition, colors, style.
Do NOT include camera movement (that's for video). Focus on a single still frame.
Keep prompts under 200 words. Be specific and visual.
Output ONLY the prompt text, nothing else.`,
    messages: [
      {
        role: "user",
        content: `Generate an image prompt for this shot:
Visual: ${shot.visual}
Camera: ${shot.camera}
Mood: ${shot.mood}
Description: ${shot.description}
Overall style: ${project.style || "cinematic"}
Overall tone: ${project.tone || "dramatic"}`,
      },
    ],
  });

  return response.content[0].type === "text" ? response.content[0].text.trim() : shot.visual;
}
