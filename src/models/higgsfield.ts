export interface HiggsFieldConfig {
  credentials: string;
}

interface GenerationResult {
  id: string;
  status: string;
  url?: string;
}

let config: HiggsFieldConfig | null = null;

export function configureHiggsfield(credentials: string): void {
  config = { credentials };
}

function getConfig(): HiggsFieldConfig {
  if (!config) {
    const creds = process.env.HF_CREDENTIALS;
    if (!creds) throw new Error("Higgsfield credentials not set. Set HF_CREDENTIALS env var.");
    config = { credentials: creds };
  }
  return config;
}

function authHeaders(): Record<string, string> {
  const { credentials } = getConfig();
  return {
    Authorization: `Key ${credentials}`,
    "Content-Type": "application/json",
    "User-Agent": "gem-cli/0.1.0",
  };
}

const BASE_URL = "https://api.higgsfield.ai";

export async function generateImage(prompt: string, aspectRatio: string = "16:9"): Promise<GenerationResult> {
  const response = await fetch(`${BASE_URL}/v1/text-to-image`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({
      model: "flux-pro/kontext/max/text-to-image",
      input: {
        prompt,
        aspect_ratio: aspectRatio,
        safety_tolerance: 2,
      },
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Image generation failed (${response.status}): ${body}`);
  }

  const data = await response.json() as any;
  const requestId = data.id || data.request_id;

  if (data.status === "completed" && data.output?.url) {
    return { id: requestId, status: "completed", url: data.output.url };
  }

  // Poll for completion
  return pollForResult(requestId);
}

export async function generateVideo(
  prompt: string,
  imageUrl: string,
  duration: number = 5
): Promise<GenerationResult> {
  const response = await fetch(`${BASE_URL}/v1/image2video/dop`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({
      model: "dop-turbo",
      input: {
        prompt,
        image_url: imageUrl,
        duration: Math.min(duration, 10),
      },
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Video generation failed (${response.status}): ${body}`);
  }

  const data = await response.json() as any;
  const requestId = data.id || data.request_id;

  if (data.status === "completed" && data.output?.url) {
    return { id: requestId, status: "completed", url: data.output.url };
  }

  return pollForResult(requestId);
}

async function pollForResult(requestId: string, maxAttempts: number = 120): Promise<GenerationResult> {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((resolve) => setTimeout(resolve, 5000));

    const response = await fetch(`${BASE_URL}/requests/${requestId}/status`, {
      headers: authHeaders(),
    });

    if (!response.ok) continue;

    const data = await response.json() as any;

    if (data.status === "completed") {
      const url = data.output?.url || data.result?.url || data.url;
      return { id: requestId, status: "completed", url };
    }

    if (data.status === "failed") {
      throw new Error(`Generation failed: ${data.error || "unknown error"}`);
    }

    if (data.status === "nsfw") {
      throw new Error("Generation blocked: content flagged as NSFW");
    }

    // Still in progress, continue polling
    process.stdout.write(".");
  }

  throw new Error("Generation timed out after 10 minutes");
}

export async function downloadFile(url: string, outputPath: string): Promise<void> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Download failed: ${response.status}`);
  const buffer = await response.arrayBuffer();
  await Bun.write(outputPath, buffer);
}
