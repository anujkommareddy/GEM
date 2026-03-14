import * as readline from "readline";

const BOLD = "\x1b[1m";
const DIM = "\x1b[2m";
const CYAN = "\x1b[36m";
const GREEN = "\x1b[32m";
const YELLOW = "\x1b[33m";
const RED = "\x1b[31m";
const MAGENTA = "\x1b[35m";
const RESET = "\x1b[0m";

export function header(text: string): void {
  console.log(`\n${BOLD}${CYAN}${"=".repeat(60)}${RESET}`);
  console.log(`${BOLD}${CYAN}  ${text}${RESET}`);
  console.log(`${CYAN}${"=".repeat(60)}${RESET}\n`);
}

export function subheader(text: string): void {
  console.log(`\n${BOLD}${MAGENTA}--- ${text} ---${RESET}\n`);
}

export function info(text: string): void {
  console.log(`${DIM}${text}${RESET}`);
}

export function success(text: string): void {
  console.log(`${GREEN}${text}${RESET}`);
}

export function warn(text: string): void {
  console.log(`${YELLOW}${text}${RESET}`);
}

export function error(text: string): void {
  console.log(`${RED}${text}${RESET}`);
}

export function stageLabel(stage: string): string {
  const labels: Record<string, string> = {
    develop: `${YELLOW}DEVELOP${RESET}`,
    plan: `${CYAN}PLAN${RESET}`,
    "look-dev": `${MAGENTA}LOOK DEV${RESET}`,
    "prompt-review": `${BOLD}PROMPT REVIEW${RESET}`,
    generate: `${GREEN}GENERATE${RESET}`,
    complete: `${GREEN}${BOLD}COMPLETE${RESET}`,
  };
  return labels[stage] || stage;
}

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});

export async function ask(prompt: string): Promise<string> {
  return new Promise((resolve) => {
    rl.question(`${BOLD}${prompt}${RESET} `, (answer) => {
      resolve(answer.trim());
    });
  });
}

export async function askMultiline(prompt: string): Promise<string> {
  console.log(`${BOLD}${prompt}${RESET} ${DIM}(empty line to finish)${RESET}`);
  const lines: string[] = [];
  return new Promise((resolve) => {
    const handler = (line: string) => {
      if (line === "") {
        rl.removeListener("line", handler);
        resolve(lines.join("\n"));
      } else {
        lines.push(line);
      }
    };
    rl.on("line", handler);
  });
}

export async function choose(prompt: string, options: string[]): Promise<number> {
  console.log(`\n${BOLD}${prompt}${RESET}`);
  options.forEach((opt, i) => {
    console.log(`  ${CYAN}${i + 1}.${RESET} ${opt}`);
  });
  while (true) {
    const answer = await ask(`Choice (1-${options.length}):`);
    const num = parseInt(answer);
    if (num >= 1 && num <= options.length) return num - 1;
    warn(`  Please enter a number between 1 and ${options.length}`);
  }
}

export async function confirm(prompt: string): Promise<boolean> {
  const answer = await ask(`${prompt} (y/n):`);
  return answer.toLowerCase().startsWith("y");
}

export function closeUI(): void {
  rl.close();
}

export function displayShot(sceneIdx: number, shotIdx: number, shot: { id: string; description: string; visual: string; camera: string; mood: string; duration: number }): void {
  console.log(`  ${DIM}Scene ${sceneIdx + 1}, Shot ${shotIdx + 1}${RESET} ${BOLD}[${shot.id}]${RESET}`);
  console.log(`    ${BOLD}Description:${RESET} ${shot.description}`);
  console.log(`    ${BOLD}Visual:${RESET} ${shot.visual}`);
  console.log(`    ${BOLD}Camera:${RESET} ${shot.camera}`);
  console.log(`    ${BOLD}Mood:${RESET} ${shot.mood}`);
  console.log(`    ${BOLD}Duration:${RESET} ${shot.duration}s`);
}
