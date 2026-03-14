import Anthropic from "@anthropic-ai/sdk";
import type { Project } from "../types";
import { saveProject } from "../project";
import * as ui from "../ui";

const client = new Anthropic();

const SYSTEM_PROMPT = `You are a creative development partner for AI-generated films and videos. Your job is to help develop raw concepts into compelling, visually rich ideas ready for production.

When given a concept, you should:
1. Identify what makes it compelling
2. Find the strongest version of the idea
3. Think about visual storytelling — what will the AUDIENCE SEE?
4. Consider pacing, mood, tone, and emotional arc
5. Think about what would make this go viral or be genuinely compelling

Be opinionated. Push the idea to be better. Ask pointed questions.
Keep responses concise and visual — this is about what the camera sees, not prose.`;

export async function runDevelop(project: Project): Promise<Project> {
  ui.header("STAGE 1: DEVELOP YOUR CONCEPT");
  ui.info("Let's develop your concept into something extraordinary.");
  ui.info("You'll go back and forth with AI until the idea is sharp.\n");

  console.log(`  Concept: "${project.concept}"\n`);

  const messages: { role: "user" | "assistant"; content: string }[] = [];

  // Initial development prompt
  const initialPrompt = `Here's a concept for an AI-generated video/film:

"${project.concept}"

Give me your honest reaction. What's compelling here? What's weak? What's the strongest version of this idea?

Then give me a developed version with:
- LOGLINE: One sentence that captures the whole thing
- TONE: The feeling/mood
- STYLE: Visual style reference (cinematic, documentary, surreal, etc.)
- THE HOOK: Why would someone watch this?
- VISUAL MOMENTS: 3-5 key images/moments the audience MUST see

Be direct. Be opinionated.`;

  messages.push({ role: "user", content: initialPrompt });

  const response = await client.messages.create({
    model: "claude-sonnet-4-20250514",
    max_tokens: 2000,
    system: SYSTEM_PROMPT,
    messages,
  });

  const assistantReply = response.content[0].type === "text" ? response.content[0].text : "";
  messages.push({ role: "assistant", content: assistantReply });
  console.log(`\n${assistantReply}\n`);

  // Iterative development loop
  while (true) {
    const choice = await ui.choose("What do you want to do?", [
      "Give feedback / iterate on the concept",
      "This is good — lock it in and move to planning",
      "Start over with a different concept",
    ]);

    if (choice === 1) {
      // Lock it in — extract the final developed concept
      ui.subheader("Locking in the concept...");

      messages.push({
        role: "user",
        content: `Great, let's lock this in. Give me the final version in this exact format:

LOGLINE: [one sentence]
TONE: [mood/feeling]
STYLE: [visual style]
TARGET DURATION: [estimated total duration]
DEVELOPED CONCEPT: [2-3 paragraph description of the full concept, focusing on visual storytelling]`,
      });

      const finalResponse = await client.messages.create({
        model: "claude-sonnet-4-20250514",
        max_tokens: 1500,
        system: SYSTEM_PROMPT,
        messages,
      });

      const finalText = finalResponse.content[0].type === "text" ? finalResponse.content[0].text : "";
      console.log(`\n${finalText}\n`);

      // Parse out the structured fields
      const loglineMatch = finalText.match(/LOGLINE:\s*(.+)/i);
      const toneMatch = finalText.match(/TONE:\s*(.+)/i);
      const styleMatch = finalText.match(/STYLE:\s*(.+)/i);
      const durationMatch = finalText.match(/TARGET DURATION:\s*(.+)/i);
      const conceptMatch = finalText.match(/DEVELOPED CONCEPT:\s*([\s\S]+)/i);

      project.logline = loglineMatch?.[1]?.trim() || project.concept;
      project.tone = toneMatch?.[1]?.trim();
      project.style = styleMatch?.[1]?.trim();
      project.targetDuration = durationMatch?.[1]?.trim();
      project.developedConcept = conceptMatch?.[1]?.trim() || finalText;
      project.stage = "plan";

      await saveProject(project);
      ui.success("Concept locked in! Moving to planning stage.");
      return project;
    } else if (choice === 2) {
      // Start over
      const newConcept = await ui.ask("New concept:");
      project.concept = newConcept;
      messages.length = 0;
      messages.push({
        role: "user",
        content: `Here's a new concept for an AI-generated video/film:

"${newConcept}"

Give me your honest reaction. What's compelling here? What's weak? What's the strongest version of this idea?

Then give me a developed version with:
- LOGLINE: One sentence that captures the whole thing
- TONE: The feeling/mood
- STYLE: Visual style reference
- THE HOOK: Why would someone watch this?
- VISUAL MOMENTS: 3-5 key images/moments the audience MUST see

Be direct. Be opinionated.`,
      });

      const newResponse = await client.messages.create({
        model: "claude-sonnet-4-20250514",
        max_tokens: 2000,
        system: SYSTEM_PROMPT,
        messages,
      });

      const newReply = newResponse.content[0].type === "text" ? newResponse.content[0].text : "";
      messages.push({ role: "assistant", content: newReply });
      console.log(`\n${newReply}\n`);
    } else {
      // Iterate
      const feedback = await ui.ask("Your feedback:");
      messages.push({ role: "user", content: feedback });

      const iterResponse = await client.messages.create({
        model: "claude-sonnet-4-20250514",
        max_tokens: 2000,
        system: SYSTEM_PROMPT,
        messages,
      });

      const iterReply = iterResponse.content[0].type === "text" ? iterResponse.content[0].text : "";
      messages.push({ role: "assistant", content: iterReply });
      console.log(`\n${iterReply}\n`);
    }
  }
}
