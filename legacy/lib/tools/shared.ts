export function ok(payload: unknown) {
  return {
    content: [
      {
        type: "text" as const,
        text: JSON.stringify(payload, null, 2),
      },
    ],
  };
}

export function fail(toolName: string, err: unknown) {
  const message =
    err instanceof Error ? err.message : typeof err === "string" ? err : "Unknown error";

  return {
    isError: true,
    content: [
      {
        type: "text" as const,
        text: JSON.stringify({
          error: true,
          tool: toolName,
          message,
        }),
      },
    ],
  };
}
