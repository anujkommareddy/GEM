import Anthropic from "@anthropic-ai/sdk";
import type { Project, Scene, Shot } from "../types";
import { saveProject } from "../project";
import * as ui from "../ui";

const client = new Anthropic();

const SYSTEM_PROMPT = `You are a visual director breaking down a film concept into a detailed shot-by-shot production plan. You think in images, not words.

For each scene and shot, describe exactly what the camera SEES. Be specific about:
- Framing (wide, medium, close-up, extreme close-up)
- Camera movement (static, pan, tilt, dolly, crane, handheld)
- Lighting and color palette
- Subject action and position
- Mood and atmosphere
- Duration in seconds (typically 3-10 seconds per shot for AI video)

Output ONLY valid JSON. No markdown, no explanation outside the JSON.`;

export async function runPlan(project: Project): Promise<Project> {
  ui.header("STAGE 2: PLAN YOUR FILM");
  ui.info("Breaking your concept into scenes and shots.\n");

  if (project.logline) console.log(`  Logline: ${project.logline}`);
  if (project.tone) console.log(`  Tone: ${project.tone}`);
  if (project.style) console.log(`  Style: ${project.style}`);
  console.log();

  const planPrompt = `Break this concept into a detailed shot-by-shot plan.

CONCEPT: ${project.developedConcept || project.concept}
${project.logline ? `LOGLINE: ${project.logline}` : ""}
${project.tone ? `TONE: ${project.tone}` : ""}
${project.style ? `STYLE: ${project.style}` : ""}
${project.targetDuration ? `TARGET DURATION: ${project.targetDuration}` : ""}

Return a JSON object with this exact structure:
{
  "scenes": [
    {
      "id": "scene-01",
      "title": "Scene title",
      "description": "What happens in this scene",
      "shots": [
        {
          "id": "shot-01-01",
          "description": "What happens in this shot",
          "visual": "Exactly what the camera sees — be very specific about subject, setting, lighting, colors",
          "camera": "Camera type and movement (e.g. 'Slow dolly forward, eye-level, shallow depth of field')",
          "mood": "Emotional quality of the shot",
          "duration": 5
        }
      ]
    }
  ]
}

Be specific and visual. Each shot should be 3-10 seconds. Think about pacing and flow between shots.`;

  ui.info("Generating visual plan...\n");

  const response = await client.messages.create({
    model: "claude-sonnet-4-20250514",
    max_tokens: 4000,
    system: SYSTEM_PROMPT,
    messages: [{ role: "user", content: planPrompt }],
  });

  const text = response.content[0].type === "text" ? response.content[0].text : "";

  // Extract JSON from response
  let planData: { scenes: Array<{ id: string; title: string; description: string; shots: Array<{ id: string; description: string; visual: string; camera: string; mood: string; duration: number }> }> };
  try {
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error("No JSON found in response");
    planData = JSON.parse(jsonMatch[0]);
  } catch (e) {
    ui.error("Failed to parse plan. Retrying...");
    const retryResponse = await client.messages.create({
      model: "claude-sonnet-4-20250514",
      max_tokens: 4000,
      system: SYSTEM_PROMPT + "\n\nCRITICAL: Return ONLY valid JSON. Nothing else.",
      messages: [{ role: "user", content: planPrompt }],
    });
    const retryText = retryResponse.content[0].type === "text" ? retryResponse.content[0].text : "";
    const retryMatch = retryText.match(/\{[\s\S]*\}/);
    if (!retryMatch) throw new Error("Could not generate plan");
    planData = JSON.parse(retryMatch[0]);
  }

  // Convert to our types
  project.scenes = planData.scenes.map((scene): Scene => ({
    id: scene.id,
    title: scene.title,
    description: scene.description,
    shots: scene.shots.map((shot): Shot => ({
      id: shot.id,
      description: shot.description,
      visual: shot.visual,
      camera: shot.camera,
      mood: shot.mood,
      duration: shot.duration,
      imageStatus: "pending",
      videoStatus: "pending",
    })),
  }));

  // Display the plan
  displayPlan(project);

  // Let user iterate on the plan
  while (true) {
    const choice = await ui.choose("What do you want to do?", [
      "Approve this plan — move to look development",
      "Give feedback — regenerate the plan",
      "Go back to concept development",
    ]);

    if (choice === 0) {
      project.stage = "look-dev";
      await saveProject(project);
      ui.success("Plan approved! Moving to look development.");
      return project;
    } else if (choice === 1) {
      const feedback = await ui.ask("What should change?");
      ui.info("Regenerating plan...\n");

      const feedbackResponse = await client.messages.create({
        model: "claude-sonnet-4-20250514",
        max_tokens: 4000,
        system: SYSTEM_PROMPT,
        messages: [
          { role: "user", content: planPrompt },
          { role: "assistant", content: text },
          { role: "user", content: `Update the plan based on this feedback: ${feedback}\n\nReturn the complete updated plan as JSON in the same format.` },
        ],
      });

      const fbText = feedbackResponse.content[0].type === "text" ? feedbackResponse.content[0].text : "";
      const fbMatch = fbText.match(/\{[\s\S]*\}/);
      if (fbMatch) {
        const fbData = JSON.parse(fbMatch[0]);
        project.scenes = fbData.scenes.map((scene: any): Scene => ({
          id: scene.id,
          title: scene.title,
          description: scene.description,
          shots: scene.shots.map((shot: any): Shot => ({
            id: shot.id,
            description: shot.description,
            visual: shot.visual,
            camera: shot.camera,
            mood: shot.mood,
            duration: shot.duration,
            imageStatus: "pending",
            videoStatus: "pending",
          })),
        }));
        displayPlan(project);
      } else {
        ui.error("Failed to parse updated plan. Keeping previous version.");
      }
    } else {
      project.stage = "develop";
      await saveProject(project);
      return project;
    }
  }
}

function displayPlan(project: Project): void {
  const totalShots = project.scenes.reduce((sum, s) => sum + s.shots.length, 0);
  const totalDuration = project.scenes.reduce(
    (sum, s) => sum + s.shots.reduce((ss, shot) => ss + shot.duration, 0),
    0
  );

  ui.subheader(`VISUAL PLAN: ${totalShots} shots across ${project.scenes.length} scenes (~${totalDuration}s)`);

  for (let si = 0; si < project.scenes.length; si++) {
    const scene = project.scenes[si];
    console.log(`\n  ${"\x1b[1m"}SCENE ${si + 1}: ${scene.title}${"\x1b[0m"}`);
    console.log(`  ${"\x1b[2m"}${scene.description}${"\x1b[0m"}\n`);

    for (let shi = 0; shi < scene.shots.length; shi++) {
      ui.displayShot(si, shi, scene.shots[shi]);
      console.log();
    }
  }
}
