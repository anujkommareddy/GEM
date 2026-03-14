import Anthropic from "@anthropic-ai/sdk";
import type { Project } from "../types";
import { saveProject } from "../project";
import * as ui from "../ui";

const client = new Anthropic();

export async function runPromptReview(project: Project): Promise<Project> {
  ui.header("STAGE 4: PROMPT REVIEW");
  ui.info("Review and approve the video generation prompts for each shot.");
  ui.info("These prompts will be sent directly to the video model.\n");

  // Generate video prompts for shots that don't have them
  const shotsNeedingPrompts = project.scenes.flatMap((s) =>
    s.shots.filter((shot) => !shot.videoPrompt && shot.imageStatus === "approved")
  );

  if (shotsNeedingPrompts.length > 0) {
    ui.info(`Generating video prompts for ${shotsNeedingPrompts.length} shots...\n`);

    for (const shot of shotsNeedingPrompts) {
      shot.videoPrompt = await generateVideoPrompt(shot, project);
      await saveProject(project);
    }
  }

  // Review each shot's video prompt
  let shotNum = 0;
  const totalShots = project.scenes.reduce(
    (sum, s) => sum + s.shots.filter((shot) => shot.imageStatus === "approved").length,
    0
  );

  for (let si = 0; si < project.scenes.length; si++) {
    const scene = project.scenes[si];
    ui.subheader(`SCENE ${si + 1}: ${scene.title}`);

    for (let shi = 0; shi < scene.shots.length; shi++) {
      const shot = scene.shots[shi];

      if (shot.imageStatus !== "approved") {
        ui.warn(`  [${shot.id}] — skipped (image not approved)`);
        continue;
      }

      if (shot.videoStatus === "done") {
        ui.success(`  [${shot.id}] — already generated`);
        continue;
      }

      shotNum++;
      console.log(`\n  Shot ${shotNum}/${totalShots} [${shot.id}]`);
      console.log(`    ${"\x1b[1m"}Description:${"\x1b[0m"} ${shot.description}`);
      console.log(`    ${"\x1b[1m"}Visual:${"\x1b[0m"} ${shot.visual}`);
      console.log(`    ${"\x1b[1m"}Camera:${"\x1b[0m"} ${shot.camera}`);
      console.log(`    ${"\x1b[1m"}Duration:${"\x1b[0m"} ${shot.duration}s`);
      if (shot.imageUrl) {
        console.log(`    ${"\x1b[1m"}Starting Image:${"\x1b[0m"} ${shot.imageUrl}`);
      }
      console.log(`\n    ${"\x1b[1m"}Video Prompt:${"\x1b[0m"}`);
      console.log(`    ${shot.videoPrompt}\n`);

      const choice = await ui.choose("This prompt will be sent to the video model:", [
        "Approve this prompt",
        "Edit this prompt",
        "Regenerate this prompt",
      ]);

      if (choice === 1) {
        console.log(`  Current: ${shot.videoPrompt}`);
        const newPrompt = await ui.ask("  New prompt:");
        shot.videoPrompt = newPrompt;
        await saveProject(project);
        ui.success("  Updated!");
      } else if (choice === 2) {
        shot.videoPrompt = await generateVideoPrompt(shot, project);
        console.log(`\n    ${"\x1b[1m"}New Video Prompt:${"\x1b[0m"}`);
        console.log(`    ${shot.videoPrompt}\n`);
        await saveProject(project);

        if (!(await ui.confirm("  Approve this version?"))) {
          const edited = await ui.ask("  Your version:");
          shot.videoPrompt = edited;
          await saveProject(project);
        }
      }
      // choice === 0: approved as-is
    }
  }

  ui.success("\nAll prompts reviewed!");

  const totalApproved = project.scenes.reduce(
    (sum, s) => sum + s.shots.filter((shot) => shot.imageStatus === "approved" && shot.videoPrompt).length,
    0
  );

  console.log(`\n  Ready to generate: ${totalApproved} video clips`);

  const advance = await ui.confirm("Move to video generation?");
  if (advance) {
    project.stage = "generate";
    await saveProject(project);
  }

  return project;
}

async function generateVideoPrompt(
  shot: { visual: string; camera: string; mood: string; description: string; duration: number },
  project: Project
): Promise<string> {
  const response = await client.messages.create({
    model: "claude-sonnet-4-20250514",
    max_tokens: 500,
    system: `You generate concise video generation prompts for AI video models.
These prompts will animate a starting image into a video clip.
Focus on MOTION and ACTION: what moves, how the camera moves, what changes.
Do NOT describe the scene setup (the starting image already has that).
Keep prompts under 150 words. Be specific about movement and timing.
Output ONLY the prompt text, nothing else.`,
    messages: [
      {
        role: "user",
        content: `Generate a video prompt for this shot (${shot.duration} seconds):
Description: ${shot.description}
Visual: ${shot.visual}
Camera movement: ${shot.camera}
Mood: ${shot.mood}
Style: ${project.style || "cinematic"}`,
      },
    ],
  });

  return response.content[0].type === "text" ? response.content[0].text.trim() : shot.description;
}
