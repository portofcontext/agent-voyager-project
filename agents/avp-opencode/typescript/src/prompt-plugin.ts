/** Runs inside the pinned OpenCode binary; uses its native system-prompt hook. */
export default async function promptPlugin(
  _context: unknown,
  options: { url: string; token: string },
) {
  const report = async (path: string, body: unknown) => {
    const response = await fetch(`${options.url}${path}`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${options.token}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) throw new Error("AVP system-prompt bridge unavailable");
    return response;
  };
  await report("/ready", {});
  return {
    "experimental.chat.system.transform": async (
      input: { sessionID?: string },
      output: { system: string[] },
    ) => {
      const response = await report("/system", {
        sessionID: input.sessionID,
        system: output.system,
      });
      const body = (await response.json()) as { system: string[] };
      output.system.splice(0, output.system.length, ...body.system);
    },
  };
}
